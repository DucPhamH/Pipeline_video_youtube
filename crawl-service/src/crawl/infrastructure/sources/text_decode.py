"""Giải mã bytes HTML — ưu tiên encoding site đã biết, không thì charset-normalizer
(thư viện encoding detection chuẩn, requests/httpx cũng dùng)."""
from __future__ import annotations


def decode_html_bytes(body: bytes, preferred: str | None = None) -> str:
    if not body:
        return ""
    if preferred:
        try:
            return body.decode(preferred, errors="replace")
        except LookupError:
            pass
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return body.decode("utf-8", errors="replace")
    best = from_bytes(body).best()
    if best is not None:
        return str(best)
    return body.decode("utf-8", errors="replace")
