"""Proxy pool — tham khảo lncrawl (proxy trong settings app + env fallback).

Thứ tự chọn (giống lncrawl: UI/config trước, env sau):

1. Setting UI từng site — `crawl.http_proxy.<source_key>`
2. Setting UI theo vùng — `crawl.proxy.vn` / `.jp` / …
3. Env vùng — `CRAWL_PROXY_VN` / `_JP` / …
4. Pool chung — `crawl.proxy` (UI) → `CRAWL_HTTP_PROXY` / file / `ALL_PROXY`…

URL hợp lệ: `http://…`, `https://…`, `socks5://…`, `socks5h://…` (DNS qua proxy).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from crawl.infrastructure.sources.site_regions import site_region

_lock = threading.Lock()
_round_robin = 0
_file_urls: list[str] | None = None

_REGION_SETTING_KEY = {
    "vietnam": "crawl.proxy.vn",
    "japan": "crawl.proxy.jp",
    "korea": "crawl.proxy.kr",
    "taiwan": "crawl.proxy.tw",
    "china": "crawl.proxy.cn",
}

_REGION_ENV = {
    "vietnam": ("CRAWL_PROXY_VN",),
    "japan": ("CRAWL_PROXY_JP",),
    "korea": ("CRAWL_PROXY_KR",),
    "taiwan": ("CRAWL_PROXY_TW",),
    "china": ("CRAWL_PROXY_CN",),
}


def _normalize(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw or raw.startswith("#"):
        return None
    if "://" not in raw:
        # lncrawl: dòng không scheme → gắn http://
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.hostname:
        return None
    return raw


def _split_csv(value: str) -> list[str]:
    out: list[str] = []
    for part in value.replace(";", ",").split(","):
        n = _normalize(part)
        if n:
            out.append(n)
    return out


def _load_proxy_file(path: str) -> list[str]:
    p = Path(path).expanduser()
    if not p.is_file():
        return []
    urls: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        n = _normalize(line)
        if n:
            urls.append(n)
    return urls


def _read_setting(key: str) -> str:
    """Đọc 1 key settings DB — fail mềm khi chưa có DB (unit test thuần)."""
    try:
        from platform_.db import SessionLocal
        from platform_.settings_store import get_setting
    except Exception:
        return ""
    db = SessionLocal()
    try:
        value = get_setting(db, key, default="")
        if value is None:
            return ""
        return str(value).strip()
    except Exception:
        return ""
    finally:
        db.close()


def ui_source_proxy(source_key: str) -> str | None:
    """Proxy gắn trên UI cài đặt site (`crawl.http_proxy.<key>`)."""
    from platform_.settings_store import per_site_key

    return _normalize(_read_setting(per_site_key("http_proxy", source_key)))


def ui_region_proxy(region: str | None) -> str | None:
    if not region:
        return None
    key = _REGION_SETTING_KEY.get(region)
    if not key:
        return None
    return _normalize(_read_setting(key))


def ui_global_proxy() -> str | None:
    """Proxy chung trên Settings (`crawl.proxy`) — CSV được, lấy phần đầu."""
    parts = _split_csv(_read_setting("crawl.proxy"))
    return parts[0] if parts else None


def _global_pool() -> list[str]:
    """Danh sách proxy chung (UI global + env, không theo vùng)."""
    global _file_urls
    urls: list[str] = []

    ui = _read_setting("crawl.proxy")
    if ui:
        urls.extend(_split_csv(ui))

    crawl = (os.getenv("CRAWL_HTTP_PROXY") or os.getenv("CRAWL_PROXY") or "").strip()
    if crawl:
        urls.extend(_split_csv(crawl))

    file_path = (os.getenv("CRAWL_PROXY_FILE") or "").strip()
    if file_path:
        with _lock:
            if _file_urls is None:
                _file_urls = _load_proxy_file(file_path)
            urls.extend(_file_urls)

    if urls:
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    for key in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = (os.getenv(key) or "").strip()
        if val:
            n = _normalize(val)
            return [n] if n else []
    return []


def region_proxy(region: str | None) -> str | None:
    """Proxy theo vùng: UI Settings trước, rồi env."""
    ui = ui_region_proxy(region)
    if ui:
        return ui
    if not region:
        return None
    for key in _REGION_ENV.get(region, ()):
        val = (os.getenv(key) or "").strip()
        if val:
            parts = _split_csv(val)
            return parts[0] if parts else None
    return None


def get_a_proxy(*, source_key: str | None = None) -> str | None:
    """Chọn 1 proxy URL cho request (giống lncrawl `get_a_proxy`).

    Ưu tiên: UI từng site → UI/env vùng → round-robin pool chung → None.
    """
    if source_key:
        per_site = ui_source_proxy(source_key)
        if per_site:
            return per_site
        regional = region_proxy(site_region(source_key))
        if regional:
            return regional

    pool = _global_pool()
    if not pool:
        return None

    global _round_robin
    with _lock:
        url = pool[_round_robin % len(pool)]
        _round_robin += 1
        return url


def httpx_proxy_mounts(proxy_url: str) -> str:
    """httpx 0.27 + socksio: chỉ nhận socks5:// (không phải socks5h://)."""
    if proxy_url.startswith("socks5h://"):
        return "socks5://" + proxy_url.removeprefix("socks5h://")
    return proxy_url


def playwright_proxy_config(proxy_url: str) -> dict[str, str]:
    """Đổi URL proxy → dict Playwright `proxy={server, username?, password?}`."""
    if proxy_url.startswith("socks5h://"):
        proxy_url = "socks5://" + proxy_url.removeprefix("socks5h://")
    parsed = urlparse(proxy_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or ""
    port = parsed.port
    server = f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"
    cfg: dict[str, str] = {"server": server}
    if parsed.username:
        cfg["username"] = unquote(parsed.username)
    if parsed.password:
        cfg["password"] = unquote(parsed.password)
    return cfg


def reset_proxy_cache() -> None:
    """Test helper — nạp lại file proxy ở lần gọi kế."""
    global _file_urls, _round_robin
    with _lock:
        _file_urls = None
        _round_robin = 0
