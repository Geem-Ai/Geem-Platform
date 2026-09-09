from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.common.rate_limit import check_auth_rate_limit
from app.common.workspace_resolver import WorkspaceResolutionHint
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.identity.dependencies import (
    client_ip,
    get_current_user,
    get_workspace_hint,
)
from app.identity.models import User
from app.identity.schemas import (
    AuthTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    MembershipOut,
    OkResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyEmailRequest,
    WorkspaceSummaryOut,
    membership_out,
    workspace_summary_out,
)
from app.identity.security import decode_access_token
from app.identity.service import AuthService, AuthTokens, RegisterResult
from app.workspaces.service import WorkspaceService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        max_age=settings.refresh_token_ttl_seconds,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/auth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _token_response(
    user: User, tokens: AuthTokens, response: Response, settings: Settings
) -> AuthTokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AuthTokenResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        user=UserOut.model_validate(user),
    )


def _register_response(
    result: RegisterResult, response: Response, settings: Settings
) -> RegisterResponse:
    if result.verification_required or result.tokens is None:
        return RegisterResponse(verification_required=True)
    _set_refresh_cookie(response, result.tokens.refresh_token, settings)
    return RegisterResponse(
        verification_required=False,
        access_token=result.tokens.access_token,
        expires_at=result.tokens.access_expires_at,
        user=UserOut.model_validate(result.user),
    )


def _rate_key(request: Request, email: str | None = None) -> str:
    ip = client_ip(request) or "unknown"
    if email:
        return f"{ip}:{email.lower()}"
    return ip


@router.post("/register", response_model=RegisterResponse)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RegisterResponse:
    check_auth_rate_limit("register", _rate_key(request, str(body.email)), settings=settings)
    # No email provider here: verification mail is delivered by the worker.
    svc = AuthService(db, settings)
    result = svc.register(
        email=str(body.email),
        password=body.password,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip(request),
    )
    return _register_response(result, response, settings)


@router.post("/login", response_model=AuthTokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    check_auth_rate_limit("login", _rate_key(request, str(body.email)), settings=settings)
    svc = AuthService(db, settings)
    user, tokens = svc.login(
        email=str(body.email),
        password=body.password,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip(request),
    )
    return _token_response(user, tokens, response, settings)


@router.post("/forgot-password", response_model=OkResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OkResponse:
    check_auth_rate_limit("forgot_password", _rate_key(request, str(body.email)), settings=settings)
    AuthService(db, settings).forgot_password(email=str(body.email))
    return OkResponse(ok=True)


@router.post("/reset-password", response_model=AuthTokenResponse)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    check_auth_rate_limit("reset_password", _rate_key(request), settings=settings)
    svc = AuthService(db, settings)
    user, tokens = svc.reset_password(
        token=body.token,
        password=body.password,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip(request),
    )
    return _token_response(user, tokens, response, settings)


@router.post("/verify-email", response_model=AuthTokenResponse)
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    check_auth_rate_limit("verify_email", _rate_key(request), settings=settings)
    svc = AuthService(db, settings)
    user, tokens = svc.verify_email(
        token=body.token,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip(request),
    )
    return _token_response(user, tokens, response, settings)


@router.post("/resend-verification", response_model=OkResponse)
def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OkResponse:
    check_auth_rate_limit(
        "resend_verification", _rate_key(request, str(body.email)), settings=settings
    )
    AuthService(db, settings).resend_verification(email=str(body.email))
    return OkResponse(ok=True)


@router.post("/change-password", response_model=OkResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OkResponse:
    check_auth_rate_limit("change_password", _rate_key(request, user.email), settings=settings)
    session = getattr(request.state, "auth_session", None)
    if session is None:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Authentication required.")
    AuthService(db, settings).change_password(
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        current_session_id=session.id,
    )
    return OkResponse(ok=True)


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    check_auth_rate_limit("refresh", _rate_key(request), settings=settings)
    raw = None
    if body and body.refresh_token:
        raw = body.refresh_token
    if not raw:
        raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise AppError(ErrorCategory.UNAUTHORIZED, "Refresh token required.")

    svc = AuthService(db, settings)
    user, tokens = svc.refresh(
        raw_refresh_token=raw,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip(request),
    )
    return _token_response(user, tokens, response, settings)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    raw = (body.refresh_token if body else None) or request.cookies.get(settings.refresh_cookie_name)
    session_id = None
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            payload = decode_access_token(auth.split(" ", 1)[1], settings=settings)
            session_id = uuid.UUID(str(payload["sid"]))
        except Exception:
            session_id = None

    AuthService(db, settings).logout(raw_refresh_token=raw, session_id=session_id)
    _clear_refresh_cookie(response, settings)
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    AuthService(db, settings).logout_all(user.id)
    _clear_refresh_cookie(response, settings)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user),
    hint: WorkspaceResolutionHint = Depends(get_workspace_hint),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Bootstrap payload for the Workspace SPA.

    Decision: ``GET /api/auth/me`` returns the user, all memberships/workspace
    summaries, and optionally the current workspace when Host / X-Workspace-*
    hints resolve and membership is verified. Avoids a request waterfall while
    keeping Identity as the entrypoint. ``GET /api/workspaces/current`` remains
    available for workspace-scoped clients that already have context.
    """
    ws_svc = WorkspaceService(db)
    pairs = ws_svc.list_for_user(user.id)
    summaries = [workspace_summary_out(w, m) for w, m in pairs]

    current: WorkspaceSummaryOut | None = None
    membership_out_row: MembershipOut | None = None
    try:
        if hint.workspace_id is not None:
            w, m = ws_svc.get_workspace_for_user(hint.workspace_id, user.id)
        elif hint.slug is not None:
            w, m = ws_svc.get_by_slug_for_user(hint.slug, user.id)
        else:
            w = m = None  # type: ignore[assignment]
        if w is not None and m is not None:
            current = workspace_summary_out(w, m)
            membership_out_row = membership_out(m)
    except AppError:
        current = None
        membership_out_row = None

    return MeResponse(
        user=UserOut.model_validate(user),
        workspaces=summaries,
        current_workspace=current,
        membership=membership_out_row,
    )
