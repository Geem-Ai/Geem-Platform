"""Microsoft Graph / Entra OAuth client for OneDrive (Phase 9E).

Focused httpx client — no large Graph SDK. Bounded retries, Retry-After,
sanitized errors; never log bearer tokens or preauthenticated download URLs.
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

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_RETRIES = 3
_ITEM_SELECT = (
    "id,name,size,file,folder,deleted,eTag,cTag,lastModifiedDateTime,"
    "webUrl,parentReference,fileSystemInfo"
)


class MicrosoftOneDriveClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        access_token: str | None = None,
        http_client: httpx.Client | None = None,
        tenant: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.access_token = access_token
        self.tenant = (tenant or self.settings.microsoft_onedrive_tenant or "organizations").strip()
        self._owned_client = http_client is None
        self._client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> MicrosoftOneDriveClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def authority_base(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}"

    @property
    def authorize_url(self) -> str:
        return f"{self.authority_base}/oauth2/v2.0/authorize"

    @property
    def token_url(self) -> str:
        return f"{self.authority_base}/oauth2/v2.0/token"

    # --- OAuth ---

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, str] = {
            "client_id": self.settings.microsoft_onedrive_client_id.strip(),
            "client_secret": self.settings.microsoft_onedrive_client_secret.strip(),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        if scope:
            data["scope"] = scope
        return self._token_request(data)

    def refresh_access_token(
        self,
        *,
        refresh_token: str,
        scope: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, str] = {
            "client_id": self.settings.microsoft_onedrive_client_id.strip(),
            "client_secret": self.settings.microsoft_onedrive_client_secret.strip(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        if scope:
            data["scope"] = scope
        return self._token_request(data)

    def acquire_resource_token(
        self,
        *,
        refresh_token: str,
        resource: str,
    ) -> dict[str, Any]:
        """Mint a short-lived token for File Picker v8 SharePoint (work/school).

        ODSP hosts expect ``{resource}/.default`` (MSAL samples). Fall back to
        MyFiles.Read / Files.Read for tenants that expose those.
        """
        resource = (resource or "").rstrip("/")
        if not resource.startswith("https://"):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Picker resource must be an https URL.",
            )
        scopes = (
            f"{resource}/.default",
            f"{resource}/MyFiles.Read offline_access",
            f"{resource}/Files.Read offline_access",
        )
        last_error: AppError | None = None
        for scope in scopes:
            try:
                return self.refresh_access_token(
                    refresh_token=refresh_token, scope=scope
                )
            except AppError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
            "Microsoft authorization failed.",
        )

    def acquire_personal_picker_token(
        self,
        *,
        refresh_token: str,
    ) -> dict[str, Any]:
        """Mint OneDrive.ReadOnly token for personal MSA File Picker v8."""
        from app.connectors.providers.microsoft_onedrive.scopes import (
            PERSONAL_PICKER_SCOPE,
        )

        scopes = (
            f"{PERSONAL_PICKER_SCOPE} offline_access",
            PERSONAL_PICKER_SCOPE,
        )
        last_error: AppError | None = None
        saw_invalid_scope = False
        for scope in scopes:
            try:
                return self.refresh_access_token(
                    refresh_token=refresh_token, scope=scope
                )
            except AppError as exc:
                last_error = exc
                details = getattr(exc, "details", None) or {}
                oauth_err = str(details.get("oauth_error") or "")
                if oauth_err == "invalid_scope":
                    saw_invalid_scope = True
                continue
        if saw_invalid_scope:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "Reconnect Microsoft OneDrive to grant personal File Picker access.",
                details={"oauth_error": "invalid_scope"},
            ) from last_error
        if last_error is not None:
            raise last_error
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
            "Microsoft authorization failed.",
        )

    # --- Graph identity / drive ---

    def get_me(self, *, access_token: str | None = None) -> dict[str, Any]:
        return self._graph_json(
            "GET",
            "/me",
            params={"$select": "id,displayName,userPrincipalName,mail"},
            access_token=access_token,
        )

    def get_drive(self, *, access_token: str | None = None) -> dict[str, Any]:
        return self._graph_json(
            "GET",
            "/me/drive",
            params={
                "$select": "id,driveType,webUrl,owner,name",
            },
            access_token=access_token,
        )

    def get_item(
        self,
        *,
        drive_id: str,
        item_id: str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        return self._graph_json(
            "GET",
            f"/drives/{drive_id}/items/{item_id}",
            params={"$select": _ITEM_SELECT},
            access_token=access_token,
        )

    def download_content(
        self,
        *,
        drive_id: str,
        item_id: str,
        max_bytes: int,
        access_token: str | None = None,
    ) -> bytes:
        return self._graph_bytes(
            "GET",
            f"/drives/{drive_id}/items/{item_id}/content",
            max_bytes=max_bytes,
            access_token=access_token,
            follow_redirects=True,
        )

    def convert_content_to_pdf(
        self,
        *,
        drive_id: str,
        item_id: str,
        max_bytes: int,
        access_token: str | None = None,
    ) -> bytes:
        return self._graph_bytes(
            "GET",
            f"/drives/{drive_id}/items/{item_id}/content",
            params={"format": "pdf"},
            max_bytes=max_bytes,
            access_token=access_token,
            follow_redirects=True,
        )

    def delta(
        self,
        *,
        drive_id: str,
        delta_link: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        if delta_link:
            # Opaque provider URL — treat as secret; do not log.
            return self._graph_json(
                "GET",
                delta_link,
                absolute_url=True,
                access_token=access_token,
            )
        return self._graph_json(
            "GET",
            f"/drives/{drive_id}/root/delta",
            params={"$select": _ITEM_SELECT},
            access_token=access_token,
        )

    def create_subscription(
        self,
        *,
        resource: str,
        notification_url: str,
        client_state: str,
        expiration_datetime: str,
        change_type: str = "updated",
        access_token: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration_datetime,
            "clientState": client_state,
        }
        return self._graph_json(
            "POST",
            "/subscriptions",
            json_body=body,
            access_token=access_token,
        )

    def renew_subscription(
        self,
        *,
        subscription_id: str,
        expiration_datetime: str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        return self._graph_json(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            json_body={"expirationDateTime": expiration_datetime},
            access_token=access_token,
        )

    def delete_subscription(
        self,
        *,
        subscription_id: str,
        access_token: str | None = None,
    ) -> None:
        try:
            self._graph_json(
                "DELETE",
                f"/subscriptions/{subscription_id}",
                access_token=access_token,
                allow_empty=True,
            )
        except AppError as exc:
            if exc.category in {
                ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND,
                ErrorCategory.MICROSOFT_ONEDRIVE_ACCESS_DENIED,
            }:
                logger.info(
                    "microsoft_onedrive_subscription_already_gone",
                    extra={"subscription_id": subscription_id[:8] + "…"},
                )
                return
            raise

    # --- HTTP helpers ---

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        try:
            resp = self._client.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException as exc:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
                "Microsoft token endpoint timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
                "Microsoft token endpoint request failed.",
            ) from exc

        if resp.status_code >= 400:
            raise self._map_token_error(resp)
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
                "Invalid token response from Microsoft.",
            ) from exc
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
                "Microsoft token response missing access_token.",
            )
        return payload

    def _graph_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        access_token: str | None = None,
        absolute_url: bool = False,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        url = path if absolute_url else f"{GRAPH_BASE}{path}"
        token = access_token or self.access_token
        if not token:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "Missing Microsoft access token.",
            )
        headers = {"Authorization": f"Bearer {token}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        resp = self._request_with_retries(
            method, url, headers=headers, params=params, json_body=json_body
        )
        if resp.status_code == 204 or (allow_empty and not resp.content):
            return {}
        if resp.status_code >= 400:
            raise self._map_graph_error(resp)
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
                "Invalid Microsoft Graph JSON response.",
            ) from exc
        if not isinstance(payload, dict):
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
                "Unexpected Microsoft Graph response shape.",
            )
        return payload

    def _graph_bytes(
        self,
        method: str,
        path: str,
        *,
        max_bytes: int,
        params: dict[str, Any] | None = None,
        access_token: str | None = None,
        follow_redirects: bool = True,
    ) -> bytes:
        url = f"{GRAPH_BASE}{path}"
        token = access_token or self.access_token
        if not token:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "Missing Microsoft access token.",
            )
        headers = {"Authorization": f"Bearer {token}"}
        # Do not follow redirects automatically with auth header — Graph may
        # hand a preauthenticated URL that must not receive the bearer token.
        resp = self._request_with_retries(
            method,
            url,
            headers=headers,
            params=params,
            follow_redirects=False,
        )
        if resp.status_code in {301, 302, 303, 307, 308}:
            location = resp.headers.get("location")
            if not location or not follow_redirects:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DOWNLOAD_FAILED,
                    "Microsoft Graph content redirect missing location.",
                )
            # Preauthenticated URL — no Authorization header; treat as secret.
            try:
                dl = self._client.request(
                    "GET",
                    location,
                    follow_redirects=True,
                    timeout=_DEFAULT_TIMEOUT,
                )
            except httpx.HTTPError as exc:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DOWNLOAD_FAILED,
                    "OneDrive content download failed.",
                ) from exc
            if dl.status_code >= 400:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_DOWNLOAD_FAILED,
                    "OneDrive content download failed.",
                )
            data = dl.content
        elif resp.status_code >= 400:
            raise self._map_graph_error(resp, download=True)
        else:
            data = resp.content

        if len(data) > max_bytes:
            raise AppError(
                ErrorCategory.UPLOAD_TOO_LARGE,
                "OneDrive file exceeds maximum upload size.",
                details={"max_bytes": max_bytes, "size": len(data)},
            )
        return data

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    follow_redirects=follow_redirects,
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                time.sleep(min(2**attempt, 8))
                continue
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(min(2**attempt, 8))
                continue

            if resp.status_code in {429, 503, 504}:
                retry_after = resp.headers.get("Retry-After")
                delay = 2**attempt
                if retry_after:
                    try:
                        delay = max(delay, int(retry_after))
                    except ValueError:
                        pass
                if attempt + 1 >= _MAX_RETRIES:
                    raise AppError(
                        ErrorCategory.MICROSOFT_ONEDRIVE_RATE_LIMITED,
                        "Microsoft Graph rate limited the request.",
                    )
                time.sleep(min(delay, 30))
                continue
            if 500 <= resp.status_code < 600 and attempt + 1 < _MAX_RETRIES:
                time.sleep(min(2**attempt, 8))
                continue
            return resp

        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
            "Microsoft Graph request failed after retries.",
        ) from last_exc

    def _map_token_error(self, resp: httpx.Response) -> AppError:
        code = ""
        description = ""
        try:
            body = resp.json()
            code = str(body.get("error") or "")
            description = str(body.get("error_description") or "")
        except Exception:  # noqa: BLE001
            body = {}
        # Never log tokens; oauth error codes + AADSTS ids are safe diagnostics.
        logger.warning(
            "microsoft_onedrive_token_error",
            extra={
                "oauth_error": code or None,
                "status": resp.status_code,
                "aadsts": (
                    description.split(":", 1)[0].strip()
                    if description.startswith("AADSTS")
                    else None
                ),
            },
        )
        if code in {
            "invalid_grant",
            "interaction_required",
            "consent_required",
        }:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "Microsoft authorization must be renewed.",
                details={"oauth_error": code},
            )
        return AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
            "Microsoft authorization failed.",
            details={"oauth_error": code or None, "status": resp.status_code},
        )

    def _map_graph_error(
        self, resp: httpx.Response, *, download: bool = False
    ) -> AppError:
        code = ""
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                code = str(err.get("code") or "")
        except Exception:  # noqa: BLE001
            pass

        if resp.status_code == 410 or code.lower() in {
            "resyncrequired",
            "resyncrequiredexception",
        }:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_DELTA_RESYNC_REQUIRED,
                "Microsoft Graph delta requires a full resync.",
                details={"graph_code": code or None},
            )
        if resp.status_code == 404 or code.lower() in {
            "itemnotfound",
            "resourcenotfound",
            "notfound",
        }:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND,
                "OneDrive item was not found.",
                details={"graph_code": code or None},
            )
        if resp.status_code in {401, 403} or code.lower() in {
            "accessdenied",
            "unauthenticated",
            "unauthorized",
            "invalidauthenticationtoken",
        }:
            if code.lower() in {
                "invalidauthenticationtoken",
                "unauthenticated",
                "unauthorized",
            }:
                return AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                    "Microsoft authorization must be renewed.",
                    details={"graph_code": code or None},
                )
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_ACCESS_DENIED,
                "OneDrive item is no longer accessible.",
                details={"graph_code": code or None},
            )
        if resp.status_code == 429:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_RATE_LIMITED,
                "Microsoft Graph rate limited the request.",
            )
        if download:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_DOWNLOAD_FAILED,
                "OneDrive content download failed.",
                details={"graph_code": code or None, "status": resp.status_code},
            )
        # Conversion failures often surface as 400/406 with specific codes.
        if code.lower() in {
            "notsupported",
            "notallowed",
            "invalidrequest",
            "noservice",
        }:
            return AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_CONVERSION_FAILED,
                "OneDrive file conversion failed.",
                details={"graph_code": code or None},
            )
        logger.info(
            "microsoft_onedrive_graph_error status=%s code=%s detail=%s",
            resp.status_code,
            code or None,
            sanitize_error_message(resp.text[:200] if resp.text else ""),
        )
        return AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
            "Microsoft Graph request failed.",
            details={"graph_code": code or None, "status": resp.status_code},
        )


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str] | tuple[str, ...],
    tenant: str,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    prompt: str | None = "select_account",
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(scopes),
        "state": state,
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method or "S256"
    if prompt:
        params["prompt"] = prompt
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    return f"{base}?{urlencode(params)}"
