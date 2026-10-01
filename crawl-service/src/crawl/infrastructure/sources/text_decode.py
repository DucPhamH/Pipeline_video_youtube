"""Giải mã bytes HTML — ưu tiên encoding site đã biết / charset trong header,
rồi `<meta charset>`, cuối cùng charset-normalizer (thư viện encoding
detection chuẩn, requests/httpx cũng dùng).

Lưu ý: KHÔNG dùng `httpx.Response.encoding` làm gợi ý — header thiếu charset
thì httpx trả mặc định "utf-8", trang GBK sẽ thành mojibake."""
from __future__ import annotations

import codecs
import re

# GBK/GB2312 là tập con của GB18030 — decode bằng GB18030 không mất ký tự hiếm
# (site hay khai "gbk" nhưng dùng ký tự ngoài bảng GBK).
_ENCODING_ALIASES = {
    "gbk": "gb18030",
    "gb2312": "gb18030",
    "gb_2312": "gb18030",
    "gb-2312": "gb18030",
    "x-gbk": "gb18030",
    "cp936": "gb18030",
}

_CT_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?\s*([\w.:-]+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(
    rb"<meta[^>]+charset\s*=\s*[\"']?\s*([\w.:-]+)", re.IGNORECASE
)


def normalize_encoding(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().strip("\"'").lower()
    if not key:
        return None
    key = _ENCODING_ALIASES.get(key, key)
    try:
        codecs.lookup(key)
    except LookupError:
        return None
    return key


def charset_from_content_type(content_type: str | None) -> str | None:
    """`text/html; charset=gbk` -> "gb18030"; không có charset -> None."""
    if not content_type:
        return None
    m = _CT_CHARSET_RE.search(content_type)
    return normalize_encoding(m.group(1)) if m else None


def sniff_meta_charset(body: bytes) -> str | None:
    """`<meta charset=…>` / `<meta http-equiv content="…charset=…">` trong 4KB đầu."""
    m = _META_CHARSET_RE.search(body[:4096])
    if not m:
        return None
    return normalize_encoding(m.group(1).decode("ascii", errors="ignore"))


def decode_html_bytes(body: bytes, preferred: str | None = None) -> str:
    """Decode STRICT theo charset khai báo (site cfg / header, rồi `<meta>`);
    sai thật (UnicodeDecodeError — site khai sai charset) mới đoán bằng
    charset-normalizer. Không đoán được thì quay lại charset khai báo với
    `errors="replace"` (vài ký tự hỏng còn hơn mojibake cả trang)."""
    if not body:
        return ""
    declared: list[str] = []
    for enc in (normalize_encoding(preferred), sniff_meta_charset(body)):
        if enc and enc not in declared:
            declared.append(enc)
    for enc in declared:
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        best = None
    else:
        best = from_bytes(body).best()
    if best is not None:
        return str(best)
    return body.decode(declared[0] if declared else "utf-8", errors="replace")
