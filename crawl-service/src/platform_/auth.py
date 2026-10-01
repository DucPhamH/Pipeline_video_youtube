"""Token dùng chung đơn giản (FOLIO_API_TOKEN) — không phải hệ thống user.

Đặt token thì mọi route trừ health/docs đòi `X-Folio-Token: <token>` hoặc
`Authorization: Bearer <token>`; GET (tải file export qua link) nhận thêm
`?token=<token>`. Không đặt = cho qua hết (tương thích ngược) + cảnh báo log."""
from __future__ import annotations

import hmac
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("auth")

PUBLIC_PATHS = frozenset(
    {"/api/health", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
)


def _configured_token() -> str:
    from platform_.config import config

    return (config.folio_api_token or "").strip()


def request_token(request: Request) -> str:
    header = (request.headers.get("x-folio-token") or "").strip()
    if header:
        return header
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if request.method == "GET":
        return (request.query_params.get("token") or "").strip()
    return ""


def is_authorized(request: Request, token: str | None = None) -> bool:
    expected = _configured_token() if token is None else token
    if not expected:
        return True
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return True
    got = request_token(request)
    return bool(got) and hmac.compare_digest(got.encode(), expected.encode())


async def token_auth_middleware(request: Request, call_next):
    if not is_authorized(request):
        return JSONResponse({"detail": "Thiếu hoặc sai API token (X-Folio-Token)"}, status_code=401)
    return await call_next(request)


def warn_if_open() -> None:
    if not _configured_token():
        logger.warning(
            "FOLIO_API_TOKEN chưa đặt — API crawl-service KHÔNG yêu cầu xác thực. "
            "Đặt FOLIO_API_TOKEN nếu service lộ ra ngoài localhost."
        )
