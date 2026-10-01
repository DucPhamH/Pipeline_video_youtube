"""Lỗi segment/job hiển thị cho người dùng — mã ngắn + thông điệp đã làm sạch.

Body lỗi của nhà cung cấp có thể chứa URL kèm `?key=...` (Gemini), header
Bearer hay nguyên key bị phản chiếu lại. Mọi chuỗi lỗi lưu DB đi qua
`format_error()`: `[<code>] <thông điệp đã che key, bỏ query, cắt ngắn>`.
UI map theo `<code>` (xem ERROR_CODES).
"""
from __future__ import annotations

import re

import httpx

from translate.application.key_rotator import looks_rate_limited

ERROR_CODES = (
    "rate_limited",
    "auth",
    "too_large",
    "truncated",
    "network",
    "refusal",
    "worker_crashed",
    "provider_error",
)

MAX_ERROR_CHARS = 300

_URL_QUERY_RE = re.compile(r"(https?://[^\s?#\"'<>]+)\?[^\s\"'<>]*")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[^\s\"',]+"),
    re.compile(r"(?i)\b((?:api[_-]?key|access[_-]?token|token|key|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{8,}"),
    re.compile(r"\bxai-[A-Za-z0-9]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    # Chuỗi dài liền mạch kiểu token (>=32 ký tự chữ+số) — che luôn cho chắc.
    re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b"),
)
_CODE_PREFIX_RE = re.compile(r"^\[(%s)\]\s*" % "|".join(ERROR_CODES))


def sanitize_message(text: str, *, limit: int = MAX_ERROR_CHARS) -> str:
    msg = _URL_QUERY_RE.sub(r"\1", str(text or ""))
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            msg = pattern.sub(lambda m: m.group(1) + "***", msg)
        else:
            msg = pattern.sub("***", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    if len(msg) > limit:
        msg = msg[: limit - 1].rstrip() + "…"
    return msg


def classify_error(exc: BaseException | str) -> str:
    if isinstance(exc, str):
        m = _CODE_PREFIX_RE.match(exc)
        if m:
            return m.group(1)
    code = getattr(exc, "error_code", None)
    if isinstance(code, str) and code in ERROR_CODES:
        return code
    msg = str(exc).lower()
    if "finish_reason=length" in msg or "cắt cụt" in msg:
        return "truncated"
    if any(
        needle in msg
        for needle in (
            "request too large",
            "reduce your message size",
            "reduce max_tokens",
            "context_length_exceeded",
            "maximum context length",
            " 413 ",
        )
    ) or msg.startswith("413 "):
        return "too_large"
    if looks_rate_limited(exc if isinstance(exc, BaseException) else Exception(msg)):
        return "rate_limited"
    status = None
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status = exc.response.status_code
    if status in (401, 403) or msg.startswith(("401 ", "403 ")) or any(
        needle in msg for needle in ("invalid_api_key", "invalid api key", "incorrect api key", "unauthorized")
    ):
        return "auth"
    if isinstance(exc, httpx.TransportError) or any(
        needle in msg for needle in ("timed out", "timeout", "connection refused", "connecterror")
    ):
        return "network"
    return "provider_error"


def format_error(exc: BaseException | str, *, code: str | None = None, prefix: str = "") -> str:
    """`[code] prefix message` — message đã làm sạch. Chuỗi đã có mã thì giữ mã."""
    chosen = code or classify_error(exc)
    raw = str(exc)
    raw = _CODE_PREFIX_RE.sub("", raw)
    if not raw.strip() and isinstance(exc, BaseException):
        raw = type(exc).__name__
    body = sanitize_message(f"{prefix}{raw}")
    return f"[{chosen}] {body}"
