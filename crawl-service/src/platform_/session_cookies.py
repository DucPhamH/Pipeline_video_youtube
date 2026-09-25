"""Cookie/session do NGƯỜI DÙNG dán vào (sau khi đăng nhập tay trên
trình duyệt) — dùng lại khi crawl site cần login / giữ phiên.

Không tự giải CAPTCHA, không tự đăng nhập hộ. Pattern giống
novel-downloader / lncrawl (user cung cấp cookie hoặc login sẵn).

Lưu trong bảng settings key-value: `crawl.session_cookie.<source_key>`.
"""
from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
from typing import Any

from sqlalchemy.orm import Session

from platform_.db import SessionLocal
from platform_.settings_store import get_setting, per_site_key, set_setting

SESSION_COOKIE_SETTING = "session_cookie"

# Cookie BẮT BUỘC theo site — `configured` chỉ true khi đủ các tên này
# (tránh badge "đã có" khi user dán thiếu z_c0/d_c0 trên Zhihu).
REQUIRED_SESSION_COOKIES: dict[str, tuple[str, ...]] = {
    "zhihu_com": ("z_c0", "d_c0"),
    "qidian_com": ("ywguid",),
}


def session_cookie_key(source_key: str) -> str:
    return per_site_key(SESSION_COOKIE_SETTING, source_key)


def required_cookie_names(source_key: str) -> list[str]:
    return list(REQUIRED_SESSION_COOKIES.get(source_key, ()))


def parse_cookie_header(raw: str | None) -> dict[str, str]:
    """Nhận chuỗi kiểu `a=1; b=2` (Cookie-Editor / DevTools copy) → dict.

    Dùng `http.cookies.SimpleCookie` (stdlib). Nếu chuỗi paste không đúng RFC,
    fallback tách `;` để vẫn nhận được cookie thực tế từ trình duyệt.
    """
    if not raw or not str(raw).strip():
        return {}
    text = str(raw).strip()
    jar = SimpleCookie()
    try:
        jar.load(text)
    except CookieError:
        jar = SimpleCookie()
    out = {k: m.value for k, m in jar.items()}
    if out:
        return out
    # Fallback: paste DevTools đôi khi không parse được bằng SimpleCookie.
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            out[name] = value.strip()
    return out


def cookie_header_from_dict(cookies: dict[str, str]) -> str:
    jar = SimpleCookie()
    for name, value in cookies.items():
        jar[name] = value
    # SimpleCookie output dạng `Set-Cookie:` từng dòng — gộp về Cookie header.
    return "; ".join(f"{k}={m.value}" for k, m in jar.items())


def load_cookie_header(source_key: str, db: Session | None = None) -> str:
    """Đọc cookie đã lưu cho 1 site. `db=None` → mở session ngắn."""
    owns = db is None
    if owns:
        db = SessionLocal()
    assert db is not None
    try:
        value = get_setting(db, session_cookie_key(source_key), default="")
        if value is None:
            return ""
        if isinstance(value, dict):
            return cookie_header_from_dict({str(k): str(v) for k, v in value.items()})
        return str(value).strip()
    finally:
        if owns:
            db.close()


def save_cookie_header(source_key: str, cookie_header: str, db: Session | None = None) -> None:
    owns = db is None
    if owns:
        db = SessionLocal()
    assert db is not None
    try:
        set_setting(db, session_cookie_key(source_key), cookie_header.strip())
    finally:
        if owns:
            db.close()


def session_status(source_key: str, db: Session | None = None) -> dict[str, Any]:
    raw = load_cookie_header(source_key, db=db)
    cookies = parse_cookie_header(raw)
    required = required_cookie_names(source_key)
    # So khớp không phân biệt hoa thường (một số browser đổi case).
    lower_map = {k.lower(): k for k in cookies}
    missing = [name for name in required if name.lower() not in lower_map]
    # Có paste gì đó nhưng thiếu key bắt buộc → chưa coi là "đã cấu hình đủ".
    if required:
        configured = bool(cookies) and not missing
    else:
        configured = bool(cookies)
    return {
        "source_key": source_key,
        "configured": configured,
        "cookie_names": sorted(cookies.keys()),
        "cookie_header": raw,
        "required_cookies": required,
        "missing_required_cookies": missing,
    }
