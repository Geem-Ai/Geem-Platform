"""httpx Google Drive / OAuth client (Phase 9D).

No google-api-python-client — bounded retries, sanitized errors, never log tokens.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.connectors.sanitize import sanitize_error_message
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_RETRIES = 3
_DEFAULT_FIELDS = (
    "id,name,mimeType,modifiedTime,version,md5Checksum,size,trashed,"
    "webViewLink,parents,resourceKey,capabilities"
)


class GoogleDriveClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        access_token: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.access_token = access_token
        self._owned_client = http_client is None
        self._client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> GoogleDriveClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # --- OAuth ---

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, str] = {
            "code": code,
            "client_id": self.settings.google_drive_client_id.strip(),
            "client_secret": self.settings.google_drive_client_secret.strip(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        return self._token_request(data)

    def refresh_access_token(self, *, refresh_token: str) -> dict[str, Any]:
        data = {
            "refresh_token": refresh_token,
            "client_id": self.settings.google_drive_client_id.strip(),
            "client_secret": self.settings.google_drive_client_secret.strip(),
            "grant_type": "refresh_token",
        }
        return self._token_request(data)

    def get_userinfo(self, *, access_token: str | None = None) -> dict[str, Any]:
        token = access_token or self.access_token
        if not token:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Missing access token for userinfo.",
            )
        return self._request_json(
            "GET",
            OAUTH_USERINFO_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

    def get_about_user(self, *, access_token: str | None = None) -> dict[str, Any]:
        """Lightweight Drive about.get (user display name / email)."""
        return self._drive_json(
            "GET",
            "/about",
            params={"fields": "user(displayName,emailAddress,permissionId)"},
            access_token=access_token,
        )

    # --- Files ---

    def get_file_metadata(
        self,
        file_id: str,
        *,
        supports_all_drives: bool = True,
        fields: str | None = None,
        resource_key: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "fields": fields or _DEFAULT_FIELDS,
            "supportsAllDrives": str(supports_all_drives).lower(),
        }
        headers: dict[str, str] = {}
        if resource_key:
            headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        return self._drive_json(
            "GET",
            f"/files/{file_id}",
            params=params,
            headers=headers or None,
            access_token=access_token,
        )

    def download_blob(
        self,
        file_id: str,
        *,
        max_bytes: int,
        resource_key: str | None = None,
        access_token: str | None = None,
        supports_all_drives: bool = True,
    ) -> bytes:
        params = {
            "alt": "media",
            "supportsAllDrives": str(supports_all_drives).lower(),
        }
        headers: dict[str, str] = {}
        if resource_key:
            headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        return self._drive_bytes(
            "GET",
            f"/files/{file_id}",
            params=params,
            headers=headers or None,
            max_bytes=max_bytes,
            access_token=access_token,
        )

    def export_workspace_file(
        self,
        file_id: str,
        *,
        export_mime: str,
        max_bytes: int,
        resource_key: str | None = None,
        access_token: str | None = None,
    ) -> bytes:
        params = {"mimeType": export_mime}
        headers: dict[str, str] = {}
        if resource_key:
            headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        try:
            return self._drive_bytes(
                "GET",
                f"/files/{file_id}/export",
                params=params,
                headers=headers or None,
                max_bytes=max_bytes,
                access_token=access_token,
            )
        except AppError as exc:
            if exc.category == ErrorCategory.GOOGLE_DRIVE_FILE_TYPE_UNSUPPORTED:
                raise
            # Retry with text/plain fallback when markdown export fails.
            if export_mime != "text/plain":
                params = {"mimeType": "text/plain"}
                return self._drive_bytes(
                    "GET",
                    f"/files/{file_id}/export",
                    params=params,
                    headers=headers or None,
                    max_bytes=max_bytes,
                    access_token=access_token,
                )
            raise

    def list_files_page(
        self,
        *,
        page_size: int = 1,
        page_token: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageSize": page_size,
            "fields": "files(id),nextPageToken",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        return self._drive_json(
            "GET", "/files", params=params, access_token=access_token
        )

    # --- Changes / watch ---

    def get_start_page_token(
        self, *, access_token: str | None = None
    ) -> str:
        data = self._drive_json(
            "GET",
            "/changes/startPageToken",
            params={"supportsAllDrives": "true"},
            access_token=access_token,
        )
        token = data.get("startPageToken")
        if not token:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_SYNC_FAILED,
                "Drive did not return a start page token.",
            )
        return str(token)

    def list_changes(
        self,
        *,
        page_token: str,
        page_size: int = 100,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "pageToken": page_token,
            "pageSize": page_size,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": (
                "nextPageToken,newStartPageToken,"
                "changes(fileId,removed,changeType,file("
                "id,name,mimeType,modifiedTime,version,md5Checksum,size,trashed,"
                "webViewLink,resourceKey))"
            ),
        }
        return self._drive_json(
            "GET", "/changes", params=params, access_token=access_token
        )

    def create_changes_watch(
        self,
        *,
        page_token: str,
        channel_id: str,
        address: str,
        channel_token: str,
        expiration_ms: int | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": channel_id,
            "type": "web_hook",
            "address": address,
            "token": channel_token,
        }
        if expiration_ms is not None:
            body["expiration"] = str(expiration_ms)
        return self._drive_json(
            "POST",
            "/changes/watch",
            params={"pageToken": page_token, "supportsAllDrives": "true"},
            json_body=body,
            access_token=access_token,
        )

    def stop_channel(
        self,
        *,
        channel_id: str,
        resource_id: str,
        access_token: str | None = None,
    ) -> None:
        try:
            self._drive_json(
                "POST",
                "/channels/stop",
                json_body={"id": channel_id, "resourceId": resource_id},
                access_token=access_token,
            )
        except AppError:
            # Best-effort on disconnect.
            logger.info(
                "google_drive_stop_channel_failed",
                extra={"channel_id": channel_id},
            )

    # --- internals ---

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.post(
                OAUTH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException as exc:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Google OAuth token request timed out.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Google OAuth token request failed.",
                retryable=True,
            ) from exc
        return self._parse_token_response(response)

    def _parse_token_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = {}
        if response.status_code >= 400:
            err = str(payload.get("error") or "")
            desc = sanitize_error_message(str(payload.get("error_description") or err))
            if err == "invalid_grant" or response.status_code in {400, 401}:
                raise AppError(
                    ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                    desc or "Google OAuth grant is invalid or revoked.",
                )
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                desc or "Google OAuth token exchange failed.",
            )
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Google OAuth response missing access_token.",
            )
        return payload

    def _auth_headers(
        self, access_token: str | None, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        token = access_token or self.access_token
        if not token:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                "Missing Google Drive access token.",
            )
        headers = {"Authorization": f"Bearer {token}"}
        if extra:
            headers.update(extra)
        return headers

    def _drive_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{DRIVE_API_BASE}{path}"
        response = self._request_with_retries(
            method,
            url,
            params=params,
            headers=self._auth_headers(access_token, headers),
            json_body=json_body,
        )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
                "Invalid JSON from Google Drive API.",
            ) from exc
        if not isinstance(data, dict):
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
                "Unexpected Google Drive API response.",
            )
        return data

    def _drive_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_bytes: int,
        access_token: str | None = None,
    ) -> bytes:
        url = path if path.startswith("http") else f"{DRIVE_API_BASE}{path}"
        response = self._request_with_retries(
            method,
            url,
            params=params,
            headers=self._auth_headers(access_token, headers),
            stream=True,
        )
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    response.close()
                    raise AppError(
                        ErrorCategory.GOOGLE_DRIVE_EXPORT_TOO_LARGE,
                        "Google Drive file exceeds maximum upload size.",
                        details={"max_bytes": max_bytes},
                    )
                chunks.append(chunk)
        finally:
            response.close()
        return b"".join(chunks)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._request_with_retries(
            method, url, headers=headers, params=params
        )
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Invalid JSON from Google identity API.",
            ) from exc
        if not isinstance(data, dict):
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_AUTHORIZATION_FAILED,
                "Unexpected Google identity response.",
            )
        return data

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                request = self._client.build_request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
                response = self._client.send(request, stream=stream)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= _MAX_RETRIES:
                    raise AppError(
                        ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
                        "Google Drive request timed out.",
                        retryable=True,
                    ) from exc
                time.sleep(min(2**attempt, 8))
                continue
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= _MAX_RETRIES:
                    raise AppError(
                        ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
                        "Google Drive request failed.",
                        retryable=True,
                    ) from exc
                time.sleep(min(2**attempt, 8))
                continue

            if response.status_code in {429} or response.status_code >= 500:
                if stream:
                    response.read()
                if attempt >= _MAX_RETRIES:
                    self._raise_http_error(response)
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(
                    2**attempt, 8
                )
                response.close()
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                if stream:
                    response.read()
                self._raise_http_error(response)

            return response

        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
            "Google Drive request failed after retries.",
            retryable=True,
        ) from last_exc

    def _raise_http_error(self, response: httpx.Response) -> None:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = {}
        message = ""
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("status") or "")
                reason = ""
                errors = err.get("errors")
                if isinstance(errors, list) and errors:
                    reason = str(errors[0].get("reason") or "")
            else:
                message = str(payload.get("error_description") or payload.get("error") or "")
                reason = ""
        else:
            reason = ""
        safe = sanitize_error_message(message) or f"Google Drive HTTP {response.status_code}"
        status = response.status_code
        if status == 401 or reason in {"authError", "invalidCredentials"}:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                safe,
            )
        if status == 403:
            if reason in {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}:
                raise AppError(
                    ErrorCategory.GOOGLE_DRIVE_RATE_LIMITED,
                    safe,
                    retryable=True,
                )
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_FILE_ACCESS_DENIED,
                safe,
            )
        if status == 404:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_FILE_NOT_FOUND,
                safe,
            )
        if status == 429:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_RATE_LIMITED,
                safe,
                retryable=True,
            )
        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_DOWNLOAD_FAILED,
            safe,
            retryable=status >= 500,
        )


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    prompt: str = "consent",
    include_granted_scopes: bool = True,
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "state": state,
        "prompt": prompt,
    }
    if include_granted_scopes:
        params["include_granted_scopes"] = "true"
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method or "S256"
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
