"""Token dùng chung (FOLIO_API_TOKEN). Trống = cho qua hết."""
from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse

from platform_.config import config

HEADER = "X-Folio-Token"
_OPEN_PATHS = {"/api/health", "/health"}


def outgoing_headers() -> dict[str, str]:
    """Header gửi kèm khi gọi service khác."""
    return {HEADER: config.folio_api_token} if config.folio_api_token else {}


def _presented(request: Request) -> str:
    token = request.headers.get(HEADER, "").strip()
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    # <audio src> và link tải không gửi được header → cho phép ?token= với GET.
    if request.method in ("GET", "HEAD"):
        return request.query_params.get("token", "").strip()
    return ""


def is_allowed(request: Request) -> bool:
    expected = config.folio_api_token
    if not expected:
        return True
    if request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
        return True
    return hmac.compare_digest(_presented(request).encode("utf-8"), expected.encode("utf-8"))


async def require_token(request: Request, call_next):
    if not is_allowed(request):
        return JSONResponse({"detail": "Thiếu hoặc sai token"}, status_code=401)
    return await call_next(request)
