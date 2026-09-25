"""Tầng 2 — Playwright Chromium headless + inject cookie user.

Dùng khi tầng 1/1b gặp CF “Just a moment” hoặc trang render JS. Mỗi OS
thread giữ Playwright riêng — sync API không được dùng chéo thread (job quét
/genre chạy threading.Thread nền).

⚠️ Sửa 17/9/2026 (rò rỉ tiến trình Chromium — xác nhận thật, không phải
nghi ngờ suông): mỗi job nền (`routers.py`) chạy trên 1 `threading.Thread`
MỚI, dùng ĐÚNG 1 LẦN rồi thread đó chết hẳn — cache theo `threading.local()`
ở `_ensure_browser()` vì vậy KHÔNG giúp tái dùng được gì giữa 2 lần "Quét
ngay" khác nhau (khác thread), mà trước đây cũng chưa hề gọi
`browser.close()`/`playwright.stop()` ở nhánh THÀNH CÔNG (chỉ có ở nhánh
launch lỗi) — mỗi lần 1 site cần tầng này (hiện chỉ `qidian_com`) được quét
là thêm 1 tiến trình Chromium con mồ côi, không bao giờ tự thoát. Đã thêm
`close_browser()`, gọi ở cuối MỖI hàm target chạy nền trong `routers.py`
(try/finally, chạy dù job lỗi) để đóng đúng browser của CHÍNH thread đó
trước khi thread kết thúc.
"""
from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlparse

from crawl.domain.ports import ScrapeError

_init_lock = threading.Lock()
_thread_state = threading.local()


def _ensure_browser() -> Any:
    browser = getattr(_thread_state, "browser", None)
    if browser is not None:
        return browser

    with _init_lock:
        browser = getattr(_thread_state, "browser", None)
        if browser is not None:
            return browser
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ScrapeError(
                "Thiếu playwright — pip install playwright && playwright install chromium"
            ) from exc
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            playwright.stop()
            raise ScrapeError(
                f"Không launch Chromium (chạy `playwright install chromium`): {exc}"
            ) from exc
        _thread_state.playwright = playwright
        _thread_state.browser = browser
        return browser


def close_browser() -> None:
    """Đóng browser + dừng Playwright của ĐÚNG thread hiện tại (nếu đã mở)
    — gọi ở cuối mỗi job nền, KHÔNG gọi giữa chừng lúc còn crawl dở (mục
    docstring module). No-op an toàn nếu thread này chưa từng mở browser
    (site không cần tầng 3, hoặc route không dùng browser)."""
    browser = getattr(_thread_state, "browser", None)
    playwright = getattr(_thread_state, "playwright", None)
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass
        _thread_state.browser = None
    if playwright is not None:
        try:
            playwright.stop()
        except Exception:
            pass
        _thread_state.playwright = None


def _parse_cookie_header(cookie_header: str, url: str) -> list[dict[str, Any]]:
    from platform_.session_cookies import parse_cookie_header

    host = urlparse(url).hostname or ""
    return [
        {
            "name": name,
            "value": value,
            "domain": host,
            "path": "/",
        }
        for name, value in parse_cookie_header(cookie_header).items()
    ]


def browser_get_html(
    url: str,
    *,
    cookie_header: str = "",
    wait_ms: int = 2500,
    timeout_ms: int = 60000,
    wait_selector: str | None = None,
    proxy: str | None = None,
    source_key: str | None = None,
) -> str:
    """Mở URL trong Chromium, trả HTML sau khi (tuỳ chọn) chờ selector."""
    browser = _ensure_browser()
    if proxy is None:
        from crawl.infrastructure.sources.proxy_pool import get_a_proxy

        proxy = get_a_proxy(source_key=source_key)

    context_kwargs: dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "locale": "zh-CN",
        "java_script_enabled": True,
    }
    if proxy:
        from crawl.infrastructure.sources.proxy_pool import playwright_proxy_config

        context_kwargs["proxy"] = playwright_proxy_config(proxy)

    context = browser.new_context(**context_kwargs)
    try:
        if cookie_header:
            cookies = _parse_cookie_header(cookie_header, url)
            if cookies:
                context.add_cookies(cookies)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # anti-bot Qidian thường inject script rồi reload — chờ thêm
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 25000))
        except Exception:
            pass
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 25000))
            except Exception:
                pass
        elif wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        # nếu vẫn trang challenge ngắn, đợi thêm 1 nhịp
        html = page.content()
        if len(html) < 5000 and ("seqid" in html or "buid" in html):
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            html = page.content()
        head = html[:4000].lower()
        if "just a moment" in head and "cloudflare" in head:
            raise ScrapeError(f"browser_fetch vẫn gặp Cloudflare tại {url}")
        return html
    except ScrapeError:
        raise
    except Exception as exc:
        raise ScrapeError(f"browser_fetch lỗi tại {url}: {exc}") from exc
    finally:
        context.close()
