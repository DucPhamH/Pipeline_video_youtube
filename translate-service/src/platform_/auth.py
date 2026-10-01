"""Token dùng chung (FOLIO_API_TOKEN) — tùy chọn.

Bật khi env có giá trị: mọi route trừ health cần header `X-Folio-Token` hoặc
`Authorization: Bearer <token>` (GET tải file còn nhận `?token=`). Tắt khi env
rỗng: cho qua hết, chỉ cảnh báo lúc khởi động.
"""
from __future__ import annotations

import hmac
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from platform_.config import config

logger = logging.getLogger("platform.auth")

TOKEN_HEADER = "X-Folio-Token"
PUBLIC_PATHS = frozenset({"/api/health", "/api/translate/health"})


def configured_token() -> str:
    return (config.folio_api_token or "").strip()


def outgoing_headers() -> dict[str, str]:
    """Header gửi kèm khi gọi service khác (crawl callback)."""
    token = configured_token()
    return {TOKEN_HEADER: token} if token else {}


def _presented_token(request: Request) -> str:
    header = request.headers.get(TOKEN_HEADER)
    if header:
        return header.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if request.method == "GET":
        return (request.query_params.get("token") or "").strip()
    return ""


def is_authorized(request: Request) -> bool:
    token = configured_token()
    if not token:
        return True
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return True
    presented = _presented_token(request)
    return bool(presented) and hmac.compare_digest(presented.encode(), token.encode())


async def token_auth_middleware(request: Request, call_next):
    if not is_authorized(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


def warn_if_unprotected() -> None:
    if not configured_token():
        logger.warning(
            "FOLIO_API_TOKEN chưa đặt — API translate-service mở cho mọi request "
            "(chỉ chạy trong mạng tin cậy)."
        )
