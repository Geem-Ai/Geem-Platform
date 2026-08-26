"""mTLS-only bounded outbound operation API."""

from __future__ import annotations

import logging
import ssl
import time
from contextlib import asynccontextmanager

import anyio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.outbound_http import OutboundTargetBlocked

from .config import GatewaySettings
from .mcp_client import McpGatewayError, McpGatewayService
from .models import (
    McpOperationRequest,
    McpOperationResponse,
    OutboundOperationRequest,
    OutboundOperationResponse,
    TargetValidationRequest,
    TargetValidationResponse,
)
from .service import BoundedOutboundExecutor
from .transport import GatewayTransportError


logger = logging.getLogger("geem.egress_gateway")


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    config = settings or GatewaySettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not config.is_local:
            config.validate_runtime()
        yield
        await application.state.mcp_service.close_all()

    application = FastAPI(
        title="Geem Internal Egress Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.executor = BoundedOutboundExecutor.build(config)
    application.state.mcp_service = McpGatewayService(config)
    application.state.request_slots = anyio.Semaphore(
        config.max_concurrent_operations
    )

    # The SDK has useful wire-level debug logging for development, but some
    # upstream log messages contain session IDs or untrusted message objects.
    # The production gateway exposes only its own redacted operation log.
    # The SDK/HTTP layers may include untrusted event names, tool names, URLs,
    # or protocol bodies even in warning/error records. The gateway emits only
    # its own fixed-schema redacted operation record.
    for namespace in ("mcp", "mcp_types", "httpx2", "httpx", "httpcore"):
        dependency_logger = logging.getLogger(namespace)
        dependency_logger.handlers.clear()
        dependency_logger.addHandler(logging.NullHandler())
        dependency_logger.propagate = False
        dependency_logger.disabled = True

    @application.middleware("http")
    async def bounded_request_envelope(request: Request, call_next):
        if request.method != "POST" or request.url.path not in {
            "/v1/outbound",
            "/v1/mcp",
            "/v1/target-validation",
        }:
            return await call_next(request)
        # Start the caller-supplied MCP/preflight budget before capacity and
        # body parsing.  Route code subtracts this ingress work so a slow or
        # fragmented internal request cannot acquire a fresh timeout window.
        request.state.gateway_received_at = time.monotonic()
        try:
            application.state.request_slots.acquire_nowait()
        except anyio.WouldBlock:
            return _error_response(
                503,
                "gateway_capacity",
                "The egress gateway is at its bounded request capacity.",
                retryable=True,
            )
        try:
            raw_headers = request.scope.get("headers", ())
            if len(raw_headers) > config.max_headers or sum(
                len(name) + len(value) for name, value in raw_headers
            ) > config.max_header_bytes:
                return _error_response(
                    431,
                    "request_headers_too_large",
                    "The operation request headers exceed the configured limit.",
                )
            # Base64 can expand the neutral body by 4/3. Leave bounded room for
            # the URL, operation fields, and credential headers.
            envelope_limit = (
                ((config.max_request_bytes + 2) // 3) * 4
                + config.max_header_bytes
                + 16_384
            )
            content_length = request.headers.get("content-length")
            if content_length is not None:
                if not content_length.isdecimal():
                    return _error_response(
                        400,
                        "invalid_request",
                        "The operation request is invalid.",
                    )
                if int(content_length) > envelope_limit:
                    return _error_response(
                        413,
                        "request_too_large",
                        "The operation request exceeds the configured limit.",
                    )
            payload = bytearray()
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > envelope_limit:
                    return _error_response(
                        413,
                        "request_too_large",
                        "The operation request exceeds the configured limit.",
                    )
            if _json_depth_exceeds(payload, max_depth=64):
                return _error_response(
                    400,
                    "invalid_request",
                    "The operation request exceeds the JSON nesting limit.",
                )
            # Starlette consults this cached body for FastAPI's later parse.
            request._body = bytes(payload)  # type: ignore[attr-defined]
            return await call_next(request)
        finally:
            application.state.request_slots.release()

    @application.exception_handler(RequestValidationError)
    async def invalid_request_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's default validation body may echo a secret header/body input.
        return _error_response(400, "invalid_request", "The operation request is invalid.")

    @application.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        # The TLS listener itself requires a verified client certificate, so the
        # health route does not create an unauthenticated side channel.
        return {"status": "ok"}

    @application.post("/v1/outbound", response_model=OutboundOperationResponse)
    def outbound(request: OutboundOperationRequest) -> OutboundOperationResponse | JSONResponse:
        started = time.monotonic()
        try:
            response = application.state.executor.execute(request)
        except OutboundTargetBlocked as exc:
            _log_operation(
                request.operation_id,
                request.method,
                "blocked",
                started,
                code=exc.code,
            )
            return _error_response(403, "egress_target_blocked", str(exc))
        except GatewayTransportError as exc:
            _log_operation(
                request.operation_id,
                request.method,
                "failed",
                started,
                code=exc.code,
            )
            outcome_unknown = request.method == "POST" and exc.dispatch_started
            status_code = (
                409
                if outcome_unknown
                else (504 if exc.code == "operation_timeout" else 502)
            )
            return _error_response(
                status_code,
                "outbound_outcome_unknown" if outcome_unknown else exc.code,
                (
                    "The non-idempotent outbound operation may have been dispatched."
                    if outcome_unknown
                    else str(exc)
                ),
                retryable=False if outcome_unknown else exc.retryable,
                outcome_unknown=outcome_unknown,
            )
        except Exception:
            # Never serialize or log the exception: it may contain a URL,
            # credential-bearing header, response body, or transport detail.
            _log_operation(
                request.operation_id,
                request.method,
                "failed",
                started,
                code="internal_error",
            )
            return _error_response(
                500,
                "internal_error",
                "The outbound operation failed safely.",
                retryable=True,
            )
        _log_operation(
            request.operation_id,
            request.method,
            "completed",
            started,
            status_code=response.status_code,
            redirects=response.redirects_followed,
            origin_digest=response.final_origin_digest,
        )
        return response

    @application.post(
        "/v1/target-validation",
        response_model=TargetValidationResponse,
    )
    def validate_target(
        request: TargetValidationRequest,
        http_request: Request,
    ) -> TargetValidationResponse | JSONResponse:
        """Resolve-only policy preflight; never connect or accept credentials."""

        started = time.monotonic()
        try:
            remaining = _remaining_caller_budget(
                http_request,
                supplied_seconds=request.deadline_seconds,
                deadline_unix_ms=request.deadline_unix_ms,
                maximum_seconds=config.total_timeout_seconds,
            )
            origin_digest = application.state.executor.validate_target(
                request.target_url,
                deadline_seconds=remaining,
            )
        except OutboundTargetBlocked as exc:
            _log_operation(
                request.operation_id,
                "TARGET_VALIDATE",
                "blocked",
                started,
                code=exc.code,
            )
            return _error_response(403, "egress_target_blocked", str(exc))
        except GatewayTransportError as exc:
            _log_operation(
                request.operation_id,
                "TARGET_VALIDATE",
                "failed",
                started,
                code=exc.code,
            )
            return _error_response(
                504 if exc.code == "operation_timeout" else 502,
                exc.code,
                str(exc),
                retryable=exc.retryable,
            )
        except Exception:
            _log_operation(
                request.operation_id,
                "TARGET_VALIDATE",
                "failed",
                started,
                code="internal_error",
            )
            return _error_response(
                500,
                "internal_error",
                "The outbound target validation failed safely.",
                retryable=True,
            )
        _log_operation(
            request.operation_id,
            "TARGET_VALIDATE",
            "completed",
            started,
            origin_digest=origin_digest,
        )
        return TargetValidationResponse(
            operation_id=request.operation_id,
            origin_digest=origin_digest,
        )

    @application.post("/v1/mcp", response_model=McpOperationResponse)
    async def mcp_operation(
        request: McpOperationRequest,
        http_request: Request,
    ) -> McpOperationResponse | JSONResponse:
        started = time.monotonic()
        try:
            remaining = _remaining_caller_budget(
                http_request,
                supplied_seconds=request.deadline_seconds,
                deadline_unix_ms=request.deadline_unix_ms,
                maximum_seconds=config.total_timeout_seconds,
                mcp=True,
            )
            bounded_request = request.model_copy(
                update={"deadline_seconds": remaining}
            )
            response = await application.state.mcp_service.execute(bounded_request)
        except OutboundTargetBlocked as exc:
            _log_operation(
                request.operation_id,
                f"MCP:{request.operation}",
                "blocked",
                started,
                code=exc.code,
            )
            return _error_response(403, "egress_target_blocked", str(exc))
        except McpGatewayError as exc:
            _log_operation(
                request.operation_id,
                f"MCP:{request.operation}",
                "failed",
                started,
                code=exc.code,
                outcome_unknown=exc.outcome_unknown,
            )
            return _error_response(
                409 if exc.outcome_unknown else (503 if exc.retryable else 422),
                exc.code,
                str(exc),
                retryable=exc.retryable,
                outcome_unknown=exc.outcome_unknown,
            )
        except Exception:
            _log_operation(
                request.operation_id,
                f"MCP:{request.operation}",
                "failed",
                started,
                code="internal_error",
            )
            return _error_response(
                500,
                "internal_error",
                "The MCP operation failed safely.",
                retryable=True,
            )
        _log_operation(
            request.operation_id,
            f"MCP:{request.operation}",
            "completed",
            started,
            protocol=response.negotiated_protocol_version,
            session_mode=response.session_mode,
        )
        return response

    return application


def _remaining_caller_budget(
    request: Request,
    *,
    supplied_seconds: float | None,
    deadline_unix_ms: int | None = None,
    maximum_seconds: float,
    mcp: bool = False,
) -> float:
    received_at = float(
        getattr(request.state, "gateway_received_at", time.monotonic())
    )
    supplied = (
        float(maximum_seconds)
        if supplied_seconds is None
        else min(float(maximum_seconds), float(supplied_seconds))
    )
    duration_remaining = supplied - max(0.0, time.monotonic() - received_at)
    remaining = duration_remaining
    if deadline_unix_ms is not None:
        # The duration bounds future clock skew and gateway ingress. The epoch
        # cutoff additionally charges API->gateway connection/TLS transit,
        # which happened before ASGI could stamp `gateway_received_at`.
        epoch_remaining = (float(deadline_unix_ms) / 1_000.0) - time.time()
        remaining = min(duration_remaining, epoch_remaining)
    if remaining <= 0:
        if mcp:
            raise McpGatewayError(
                "mcp_operation_timeout",
                "The MCP operation exceeded its total deadline.",
                retryable=True,
            )
        raise GatewayTransportError(
            "operation_timeout",
            "The outbound target resolution exceeded its deadline.",
            retryable=True,
        )
    return remaining


def _json_depth_exceeds(payload: bytes | bytearray, *, max_depth: int) -> bool:
    """Bound nesting before Starlette allocates recursive JSON structures."""

    depth = 0
    in_string = False
    escaped = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in {0x5B, 0x7B}:  # [ {
            depth += 1
            if depth > max_depth:
                return True
        elif byte in {0x5D, 0x7D}:  # ] }
            depth = max(0, depth - 1)
    return False


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    outcome_unknown: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "outcome_unknown": outcome_unknown,
            }
        },
        headers={"Cache-Control": "no-store"},
    )


def _log_operation(
    operation_id: str,
    method: str,
    outcome: str,
    started: float,
    **safe_fields: object,
) -> None:
    logger.info(
        "egress_operation",
        extra={
            "operation_id": operation_id,
            "method": method,
            "outcome": outcome,
            "duration_ms": round((time.monotonic() - started) * 1_000, 2),
            **safe_fields,
        },
    )


app = create_app()


def run() -> None:
    settings = GatewaySettings.from_env()
    settings.validate_runtime()
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.bind_port,
        ssl_certfile=settings.server_cert_file,
        ssl_keyfile=settings.server_key_file,
        ssl_ca_certs=settings.client_ca_file,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
