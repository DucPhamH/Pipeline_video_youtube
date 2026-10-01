"""Tầng 1 (SourcePort bằng httpx thuần) — hạ tầng DÙNG CHUNG cho site kiểu
'biquge-clone' (retry/backoff, phân trang danh sách, parse HTML theo CSS
selector). Mỗi site có adapter RIÊNG (`bqgxs_com_source.py`...) kế thừa
`BaseHtmlSource`, tự khai `SourceConfig` của mình trong `__init__`. Site cần
hành vi khác biệt hẳn (không chỉ đổi selector/URL) thì override thẳng
method ở đúng adapter đó, không đụng file dùng chung này.

Site nào tầng này luôn fail (JS-challenge thật, chặn bot mạnh) mới cần viết
adapter tầng 2 dùng browser thật (xem crawl-service.md mục 4 & 8)."""
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.urls import chapter_url_key
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.content_pipeline import (
    ChallengeError,
    NonRetryableScrapeError,
    RateLimitedError,
    check_fetched_html,
)
from crawl.infrastructure.sources.fetch_guard import (
    assert_public_url,
    url_belongs_to_source,
)
from crawl.infrastructure.sources.proxy_pool import get_a_proxy, httpx_proxy_mounts
from crawl.infrastructure.sources.text_decode import charset_from_content_type, decode_html_bytes
from crawl.infrastructure.sources.tls_fetch import looks_like_cloudflare_challenge

# HTTP không nên retry: tài nguyên không tồn tại / bị cấm — thử lại chỉ tốn
# thời gian (mỗi lần có backoff) và dễ bị chặn thêm.
_NON_RETRYABLE_STATUS = frozenset({401, 403, 404, 410, 451})
_MAX_RETRY_AFTER_SEC = 120.0
# Tổng thời gian chờ theo Retry-After trong 1 lần `_get_soup` (mọi lần thử
# cộng lại) — site trả Retry-After lớn liên tục không được giữ thread mãi.
_MAX_TOTAL_RETRY_AFTER_SEC = 180.0


def _parse_retry_after(resp: httpx.Response) -> float | None:
    """Header Retry-After: số giây hoặc HTTP-date."""
    raw = (resp.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    import datetime as dt

    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, NonRetryableScrapeError):
        return False
    return isinstance(exc, (httpx.HTTPError, ScrapeError))


def dedupe_chapter_anchors(items: list[tuple[str, str]]) -> list[ChapterRef]:
    """[(title, abs_url)] -> ChapterRef đánh số lại 1..N, bỏ URL trùng.

    TOC kiểu biquge lặp khối "最新章节" (vài chương mới nhất) ở ĐẦU trang
    trước danh sách đầy đủ — CHỈ khối trùng đứng đầu (mỗi mục đều xuất hiện
    lại phía sau) mới bỏ bản đầu, giữ bản sau. Trùng ở chỗ khác (site lặp
    link "chương trước/sau", khối "最新" cuối trang…) thì giữ lần ĐẦU — đúng
    vị trí đọc thật."""
    keys = [chapter_url_key(url) for _title, url in items]
    last_pos: dict[str, int] = {}
    for pos, key in enumerate(keys):
        last_pos[key] = pos
    lead = 0
    while lead < len(items) and last_pos[keys[lead]] > lead:
        lead += 1
    seen: set[str] = set()
    kept: list[tuple[str, str]] = []
    for pos, item in enumerate(items):
        if pos < lead:
            continue  # bản trùng ở khối đầu — bản sau (đúng thứ tự) được giữ
        if keys[pos] in seen:
            continue
        seen.add(keys[pos])
        kept.append(item)
    return [ChapterRef(index=i, title=t, url=u) for i, (t, u) in enumerate(kept, start=1)]


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass
class SourceConfig:
    key: str
    name: str
    base_url: str
    encoding: str | None = None
    genre_item_selector: str = "li"          # 1 dòng truyện trong trang thể loại
    genre_title_selector: str = "a"           # thẻ <a> tiêu đề bên trong 1 dòng
    genre_latest_chapter_selector: str = ""   # selector chương mới nhất (rỗng = bỏ qua)
    chapter_list_selector: str = "#list a"
    content_selector: str = "#content"
    novel_title_selector: str = "h1"
    novel_author_selector: str = ""  # rỗng = bỏ qua; vd ".info a", "#info p"
    novel_cover_selector: str = ""  # img bìa — lấy src
    strip_lines_containing: list[str] = field(default_factory=list)
    request_delay_sec: float = 1.0
    max_retries: int = 2
    backoff_base_sec: float = 2.0
    # 1 chương bị chia nhiều trang (vd bqgxs.com: 275597.html, 275597_2.html,
    # ...) — bật cờ này để tự nối các trang lại thành 1 chương hoàn chỉnh.
    paginated_content: bool = False
    page_marker_re: str = r"第\s*[\(（](\d+)\s*/\s*(\d+)\s*[\)）]\s*页"
    # Suy ra URL mục lục từ URL 1 chương — CHỈ set cho site nào URL chương có
    # quy luật rõ ràng (vd bqgxs.com: .../131/131542/275597.html -> bỏ phần
    # cuối là ra .../131/131542/). Để None nếu site không có quy luật đáng
    # tin (vd một số site dùng 2 hệ id khác nhau giữa mục lục/chương — xem
    # domain/ports.py SourcePort.derive_novel_url).
    novel_url_from_chapter: Callable[[str], str] | None = None
    # Suy ra URL "trang N" của 1 danh sách (thể loại/xếp hạng/search) từ URL
    # trang 1 — dùng khi trang 1 không đủ truyện ĐẠT tiêu chí ngắn+hoàn
    # thành (vd bảng xếp hạng "hot" toàn truyện dài, tỉ lệ loại rất cao) và
    # cần dò tiếp (CrawlGenreUseCase, mục 7c). None = site không hỗ trợ
    # (hoặc chưa biết quy luật) -> chỉ xét đúng trang 1, không dò thêm.
    paginate_list_url: Callable[[str, int], str] | None = None
    # Ngôn ngữ nội dung chính — dùng validate + marker hoàn thành (mặc định zh).
    content_locale: str = "zh"
    accept_language: str | None = None
    # Host mirror/domain phụ của site (vd "xbiquge.so") — URL người dùng dán
    # và cookie phiên chỉ chấp nhận host thuộc base_url hoặc các mirror này.
    mirror_hosts: list[str] = field(default_factory=list)


class BaseHtmlSource:
    """Implement SourcePort (Protocol) qua kế thừa — mỗi site tạo 1 class
    con RIÊNG (vd `BiqugeProSource(BaseHtmlSource)`), truyền `SourceConfig`
    của site đó vào `super().__init__()`. Method dùng chung (retry/backoff,
    phân trang, parse HTML) nằm ở đây; site nào cần khác biệt override
    thẳng method tương ứng ở class con."""

    is_test = False  # site thật (khác DemoLocalSource) -> hiện ở trang "Danh sách site"

    # Giây giữa 2 lần đọc lại setting proxy (mỗi lần đọc = vài query DB).
    _PROXY_REFRESH_SEC = 15.0

    def __init__(self, cfg: SourceConfig):
        self.cfg = cfg
        self.key = cfg.key
        self.name = cfg.name
        # Proxy KHÔNG chốt 1 lần lúc import registry — người dùng đổi proxy
        # trên UI thì request sau phải đi proxy mới. Mỗi proxy URL giữ 1
        # httpx.Client riêng (giữ cookie jar khi round-robin qua lại).
        self._clients: dict[str, httpx.Client] = {}
        self._client_last_used: dict[str, float] = {}
        self._clients_lock = threading.Lock()
        self._proxy_checked_at = 0.0
        self._current_proxy = ""
        self._refresh_proxy(force=True)

    # Client của proxy cũ (không còn là proxy hiện tại) idle quá lâu thì đóng.
    _CLIENT_IDLE_CLOSE_SEC = 300.0

    def _guard_request(self, request: httpx.Request) -> None:
        """Event hook httpx — chạy cho MỌI request kể cả từng bước redirect:
        chặn host private (SSRF) và bỏ Cookie phiên nếu host không thuộc site."""
        url = str(request.url)
        assert_public_url(url)
        if "cookie" in request.headers and not url_belongs_to_source(url, self):
            del request.headers["cookie"]

    def _build_client(self, proxy: str) -> httpx.Client:
        kwargs: dict = {
            "headers": DEFAULT_HEADERS,
            "timeout": 20,
            "follow_redirects": True,
            "event_hooks": {"request": [self._guard_request]},
        }
        if not proxy:
            return httpx.Client(**kwargs)
        # httpx: ưu tiên `proxy=` (0.28+); 0.27 vẫn nhận `proxies=`.
        try:
            return httpx.Client(proxy=httpx_proxy_mounts(proxy), **kwargs)
        except TypeError:
            return httpx.Client(proxies=httpx_proxy_mounts(proxy), **kwargs)

    def _refresh_proxy(self, *, force: bool = False) -> str:
        now = time.monotonic()
        if force or now - self._proxy_checked_at >= self._PROXY_REFRESH_SEC:
            self._proxy_checked_at = now
            try:
                self._current_proxy = get_a_proxy(source_key=self.cfg.key) or ""
            except Exception:
                pass  # giữ proxy cũ nếu đọc setting lỗi
        return self._current_proxy

    @property
    def _proxy_url(self) -> str:
        return self._refresh_proxy()

    @property
    def _client(self) -> httpx.Client:
        proxy = self._refresh_proxy()
        now = time.monotonic()
        stale: list[httpx.Client] = []
        with self._clients_lock:
            client = self._clients.get(proxy)
            if client is None:
                client = self._build_client(proxy)
                self._clients[proxy] = client
                # Proxy đổi -> client proxy cũ không còn dùng: đóng khi đã idle
                # đủ lâu (thread khác có thể vẫn đang dùng nó cho request dở).
                for other, last in list(self._client_last_used.items()):
                    if other != proxy and now - last >= self._CLIENT_IDLE_CLOSE_SEC:
                        old = self._clients.pop(other, None)
                        self._client_last_used.pop(other, None)
                        if old is not None:
                            stale.append(old)
            self._client_last_used[proxy] = now
        for old in stale:
            try:
                old.close()
            except Exception:
                pass
        return client

    def close_clients(self) -> None:
        with self._clients_lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._client_last_used.clear()
        for c in clients:
            try:
                c.close()
            except Exception:
                pass

    def _apply_user_session(self) -> None:
        """Gắn cookie người dùng đã lưu (đăng nhập tay) vào mọi request —
        site cần phiên / chống bot nhẹ thường chỉ cần bước này."""
        try:
            from platform_.session_cookies import load_cookie_header
        except Exception:
            self._session_cookie_header = ""
            return
        self._session_cookie_header = load_cookie_header(self.key)

    def _get_soup(self, url: str, *, check_content_blockers: bool = False) -> BeautifulSoup:
        """Retry có jitter qua tenacity (giống lncrawl) — chỉ retry lỗi mạng /
        HTTP khác 200. Delay lịch sự SAU khi tải thành công, không nằm trong
        vòng retry (tránh nhân đôi chờ khi fail).

        `check_content_blockers`: chỉ bật khi fetch nội dung chương — phát hiện
        CF/VIP sớm. Mục lục/danh sách vẫn kiểm trang Cloudflare/challenge
        (không kiểm marker VIP — dễ false positive)."""
        from platform_.run_cancel import interruptible_sleep

        assert_public_url(url)
        self._apply_user_session()
        retry_after_budget = {"left": _MAX_TOTAL_RETRY_AFTER_SEC}

        def _wait(retry_state) -> float:
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                wait = min(max(retry_after, 1.0), _MAX_RETRY_AFTER_SEC, retry_after_budget["left"])
                retry_after_budget["left"] = max(0.0, retry_after_budget["left"] - wait)
                return wait
            return _backoff(retry_state)

        _backoff = wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=_wait,
            retry=retry_if_exception(_is_retryable),
            sleep=interruptible_sleep,
        )
        def _fetch() -> BeautifulSoup:
            headers = {"Referer": self.cfg.base_url}
            if self.cfg.accept_language:
                headers["Accept-Language"] = self.cfg.accept_language
            if getattr(self, "_session_cookie_header", "") and url_belongs_to_source(url, self):
                headers["Cookie"] = self._session_cookie_header
            try:
                resp = self._client.get(url, headers=headers)
            except httpx.HTTPError:
                raise
            if resp.status_code != 200:
                msg = f"[{self.key}] HTTP {resp.status_code} khi tải {url}"
                if resp.status_code == 429:
                    raise RateLimitedError(msg, retry_after=_parse_retry_after(resp))
                if resp.status_code in _NON_RETRYABLE_STATUS:
                    raise NonRetryableScrapeError(msg)
                raise ScrapeError(msg)
            html = decode_html_bytes(
                resp.content,
                preferred=self.cfg.encoding or charset_from_content_type(resp.headers.get("content-type")),
            )
            if check_content_blockers:
                check_fetched_html(html, source_key=self.key, url=url)
            elif looks_like_cloudflare_challenge(html):
                raise ChallengeError(f"[{self.key}] Cloudflare/challenge tại {url}")
            return BeautifulSoup(html, "lxml")

        try:
            soup = _fetch()
        except NonRetryableScrapeError as exc:
            # Giữ đúng class (VIP/404…) — không ghi "sau N lần thử" vì không retry.
            raise type(exc)(f"[{self.key}] Không tải được {url}: {exc}") from exc
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không tải được {url} sau {self.cfg.max_retries + 1} lần thử: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return soup

    def _abs_url(self, href: str) -> str:
        return urljoin(self.cfg.base_url.rstrip("/") + "/", href)

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        """Top N truyện đầu TRANG 1 — dùng cho dry-run/preview (chỉ cần xem
        nhanh, không cần dò thêm trang). Job quét thật dùng
        `list_genre_novels_page` (có thể dò nhiều trang) thay cho hàm này."""
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """TOÀN BỘ truyện ở đúng 1 trang cụ thể (không cắt bớt) — trang 1 là
        `genre_list_url` nguyên bản, trang >1 suy ra qua
        `SourceConfig.paginate_list_url` (None -> trang đó không tồn tại,
        trả rỗng thay vì lỗi, để caller hiểu là "hết truyện để xét")."""
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []

        soup = self._get_soup(url)
        items = soup.select(self.cfg.genre_item_selector)
        if not items:
            if page == 1:
                raise ScrapeError(
                    f"[{self.key}] Không tìm thấy truyện nào với selector "
                    f"'{self.cfg.genre_item_selector}' tại {url} — site có thể đổi cấu trúc."
                )
            return []  # trang sau rỗng -> đã hết danh sách, không phải lỗi

        results = []
        for item in items:
            title_tag = item.select_one(self.cfg.genre_title_selector)
            if title_tag is None or not title_tag.get("href"):
                continue
            latest = ""
            if self.cfg.genre_latest_chapter_selector:
                latest_tag = item.select_one(self.cfg.genre_latest_chapter_selector)
                latest = latest_tag.get_text(strip=True) if latest_tag else ""
            results.append(
                NovelRef(
                    title=title_tag.get_text(strip=True),
                    url=self._abs_url(title_tag["href"]),
                    latest_chapter_title=latest,
                )
            )
        return results

    def derive_novel_url(self, chapter_url: str) -> str | None:
        if self.cfg.novel_url_from_chapter is None:
            return None
        try:
            return self.cfg.novel_url_from_chapter(chapter_url)
        except Exception:
            return None

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        anchors = soup.select(self.cfg.chapter_list_selector)
        if not anchors:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy chương nào với selector "
                f"'{self.cfg.chapter_list_selector}' tại {novel_url} — site có thể đổi cấu trúc."
            )
        return dedupe_chapter_anchors(
            [(a.get_text(strip=True), self._abs_url(a["href"])) for a in anchors if a.get("href")]
        )

    def fetch_novel_title(self, novel_url: str) -> str | None:
        soup = self._get_soup(novel_url)
        node = soup.select_one(self.cfg.novel_title_selector)
        if node is None:
            return None
        title = node.get_text(strip=True)
        return title or None

    def fetch_novel_author(self, novel_url: str) -> str | None:
        if not self.cfg.novel_author_selector:
            return None
        soup = self._get_soup(novel_url)
        node = soup.select_one(self.cfg.novel_author_selector)
        if node is None:
            return None
        text = node.get_text(strip=True)
        for prefix in ("作者：", "作者:", "作家：", "作家:", "Author:", "作者"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text or None

    def fetch_novel_cover_url(self, novel_url: str) -> str | None:
        if not self.cfg.novel_cover_selector:
            return None
        soup = self._get_soup(novel_url)
        node = soup.select_one(self.cfg.novel_cover_selector)
        if node is None:
            return None
        src = node.get("src") or node.get("data-src") or ""
        if not src:
            return None
        return self._abs_url(src)

    def _extract_raw_page_text(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy nội dung với selector "
                f"'{self.cfg.content_selector}' tại {chapter_url}"
            )
        for br in node.find_all("br"):
            br.replace_with("\n")
        return node.get_text("\n")

    def _paginated_url(self, base_url: str, page: int) -> str:
        """vd '.../275597.html' -> '.../275597_3.html' (quy ước phổ biến ở
        các site kiểu bqgxs.com khi 1 chương bị chia nhiều trang)."""
        if page == 1:
            return base_url
        return re.sub(r"\.html$", f"_{page}.html", base_url)

    def fetch_chapter_content(self, chapter_url: str) -> str:
        raw_text = self._extract_raw_page_text(chapter_url)
        page_texts = [raw_text]

        if self.cfg.paginated_content:
            match = re.search(self.cfg.page_marker_re, raw_text)
            if match:
                total_pages = int(match.group(2))
                for page in range(2, total_pages + 1):
                    page_url = self._paginated_url(chapter_url, page)
                    page_texts.append(self._extract_raw_page_text(page_url))

        combined = "\n".join(page_texts)
        combined = re.sub(self.cfg.page_marker_re, "", combined)  # bỏ marker "第(N/M)页"

        lines = [
            line.strip()
            for line in combined.splitlines()
            if line.strip() and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        text = "\n".join(lines)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng sau khi lọc tại {chapter_url}")
        return text
