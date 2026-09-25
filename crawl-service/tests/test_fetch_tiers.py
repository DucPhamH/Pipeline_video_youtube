"""Unit tests hạ tầng tầng 1b/2 — không cần mạng."""
import threading

from crawl.infrastructure.sources.challenge_fetch import (
    create_guid,
    merge_challenge_cookies,
    solve_acw_sc_v2,
)
from crawl.infrastructure.sources.content_pipeline import assert_not_vip_locked, check_fetched_html
from crawl.infrastructure.sources.tls_fetch import looks_like_cloudflare_challenge
from crawl.domain.ports import ScrapeError
import pytest


def test_solve_acw_sc_v2_roundtrip_shape():
    # arg1 length must match ORDER (40 hex chars = 20 bytes)
    arg1 = "A" * 40
    html = f"<html><script>var arg1='{arg1}';</script></html>"
    solved = solve_acw_sc_v2(html)
    assert solved is not None
    assert len(solved) == 40
    assert all(c in "0123456789abcdef" for c in solved)


def test_merge_challenge_sets_guid_and_cookie():
    html = "<html><script>var arg1='" + ("B" * 40) + "';</script></html>"
    cookies = merge_challenge_cookies({}, html)
    assert "GUID" in cookies
    assert "acw_sc__v2" in cookies
    assert len(create_guid()) == 36


def test_cloudflare_detect():
    assert looks_like_cloudflare_challenge("Just a moment... cloudflare")
    assert looks_like_cloudflare_challenge(
        "Access denied | www.wenku8.net used Cloudflare to restrict access"
    )
    assert not looks_like_cloudflare_challenge("<html><body>小说正文</body></html>")
    # wenku8 gắn script challenge-platform trên trang catalog bình thường
    assert not looks_like_cloudflare_challenge(
        "<html><head><script>/cdn-cgi/challenge-platform/scripts/jsd/main.js"
        "</script></head><body><td class='ccss'><a>ch1</a></td></body></html>"
    )


def test_vip_lock_raises():
    with pytest.raises(ScrapeError, match="VIP"):
        assert_not_vip_locked("您还没有订阅本章节", source_key="x", url="http://x")


def test_check_fetched_html_cloudflare():
    with pytest.raises(ScrapeError, match="Cloudflare"):
        check_fetched_html("Just a moment... cloudflare", source_key="x", url="http://x")


def test_browser_fetch_keeps_playwright_per_thread(monkeypatch):
    """Job quét chạy thread nền — mỗi thread phải có browser state riêng.

    Sửa 17/9/2026 (test flaky thật đã xác nhận, chỉ lộ ra khi chạy CẢ bộ
    test — máy bận hơn khiến 2 thread `t1`/`t2` dễ chạy KHÔNG chồng lấp
    nhau: `t1` (worker rất ngắn, chỉ vài lệnh no-op) có thể chạy xong và
    tiến trình hệ điều hành thu hồi hẳn TID của nó TRƯỚC KHI `t2` được lập
    lịch chạy — hệ điều hành hoàn toàn có quyền TÁI SỬ DỤNG đúng số TID đó
    cho `t2`, khiến `threading.get_ident()` trả về CÙNG 1 số cho 2 thread
    Python thật sự khác nhau. Đây không phải bug thật ở `browser_fetch.py`
    (mục đích của nó — mỗi `threading.local()` slot riêng theo thread —
    vẫn đúng), chỉ là dùng sai công cụ đo: đổi sang `id(threading.
    current_thread())` (định danh đối tượng Thread Python, ổn định suốt
    khi biến `t1`/`t2` còn giữ tham chiếu tới nó, không bị hệ điều hành tái
    sử dụng như TID)."""
    from crawl.infrastructure.sources import browser_fetch as bf

    created: list[int] = []

    class FakeBrowser:
        def new_context(self, **_kwargs):
            return FakeContext()

    class FakeContext:
        def add_cookies(self, _cookies):
            return None

        def new_page(self):
            return FakePage()

        def close(self):
            return None

    class FakePage:
        def goto(self, *_a, **_k):
            return None

        def wait_for_load_state(self, *_a, **_k):
            return None

        def wait_for_selector(self, *_a, **_k):
            return None

        def wait_for_timeout(self, *_a, **_k):
            return None

        def content(self):
            return "<html><body>ok</body></html>"

    class FakeChromium:
        def launch(self, **_k):
            created.append(id(threading.current_thread()))
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            return None

    def fake_sync_playwright(*_args, **_kwargs):
        class Ctx:
            def start(self):
                return FakePlaywright()

        return Ctx()

    monkeypatch.setattr(bf, "_thread_state", threading.local())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright",
        type("m", (), {"sync_api": type("s", (), {"sync_playwright": fake_sync_playwright})()})(),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        type("s", (), {"sync_playwright": fake_sync_playwright})(),
    )

    ids: list[int] = []

    def worker():
        bf.browser_get_html("https://example.com/")
        ids.append(id(threading.current_thread()))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(created) == 2
    assert len(set(created)) == 2
    assert len(set(ids)) == 2


def test_close_browser_stops_playwright_and_allows_relaunch(monkeypatch):
    """Sửa 17/9/2026 (rò rỉ tiến trình Chromium — mục docstring
    browser_fetch.py): `close_browser()` phải gọi ĐÚNG `browser.close()` +
    `playwright.stop()` của thread hiện tại, và xoá sạch state để lần fetch
    SAU (cùng thread) launch lại instance MỚI thay vì tưởng nhầm vẫn còn
    browser cũ (đã đóng) mà dùng lại."""
    from crawl.infrastructure.sources import browser_fetch as bf

    closed: list[str] = []
    launched = 0

    class FakeBrowser:
        def close(self):
            closed.append("browser")

    class FakePlaywright:
        def stop(self):
            closed.append("playwright")

    class FakeChromium:
        def launch(self, **_k):
            nonlocal launched
            launched += 1
            return FakeBrowser()

    class FakeSyncPlaywrightCtx:
        def start(self):
            pw = FakePlaywright()
            pw.chromium = FakeChromium()
            return pw

    monkeypatch.setattr(bf, "_thread_state", threading.local())
    # Không gọi _ensure_browser thật (cần playwright cài thật) — set thẳng
    # state mô phỏng ĐÚNG effect của nó, vì test này chỉ quan tâm
    # close_browser() dọn đúng state đã có hay không.
    ctx = FakeSyncPlaywrightCtx()
    bf._thread_state.playwright = ctx.start()
    bf._thread_state.browser = bf._thread_state.playwright.chromium.launch()

    assert launched == 1
    bf.close_browser()
    assert closed == ["browser", "playwright"]
    assert getattr(bf._thread_state, "browser", None) is None
    assert getattr(bf._thread_state, "playwright", None) is None

    # Gọi lần 2 khi đã đóng rồi -> no-op an toàn, không raise.
    bf.close_browser()

    # Launch lại (mô phỏng job nền tiếp theo, cùng thread) -> instance MỚI.
    bf._thread_state.playwright = ctx.start()
    bf._thread_state.browser = bf._thread_state.playwright.chromium.launch()
    assert launched == 2
