"""Tầng 1 (SourcePort bằng httpx thuần) — hạ tầng DÙNG CHUNG cho site kiểu
'biquge-clone' (retry/backoff, phân trang danh sách, parse HTML theo CSS
selector). Mỗi site có adapter RIÊNG (`bqgxs_com_source.py`...) kế thừa
`BaseHtmlSource`, tự khai `SourceConfig` của mình trong `__init__`. Site cần
hành vi khác biệt hẳn (không chỉ đổi selector/URL) thì override thẳng
method ở đúng adapter đó, không đụng file dùng chung này.

Site nào tầng này luôn fail (JS-challenge thật, chặn bot mạnh) mới cần viết
adapter tầng 2 dùng browser thật (xem crawl-service.md mục 4 & 8)."""
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.content_pipeline import check_fetched_html
from crawl.infrastructure.sources.proxy_pool import get_a_proxy, httpx_proxy_mounts
from crawl.infrastructure.sources.text_decode import decode_html_bytes

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


class BaseHtmlSource:
    """Implement SourcePort (Protocol) qua kế thừa — mỗi site tạo 1 class
    con RIÊNG (vd `BiqugeProSource(BaseHtmlSource)`), truyền `SourceConfig`
    của site đó vào `super().__init__()`. Method dùng chung (retry/backoff,
    phân trang, parse HTML) nằm ở đây; site nào cần khác biệt override
    thẳng method tương ứng ở class con."""

    is_test = False  # site thật (khác DemoLocalSource) -> hiện ở trang "Danh sách site"

    def __init__(self, cfg: SourceConfig):
        self.cfg = cfg
        self.key = cfg.key
        self.name = cfg.name
        proxy = get_a_proxy(source_key=cfg.key)
        if proxy:
            # httpx: ưu tiên `proxy=` (0.28+); 0.27 vẫn nhận `proxies=`.
            try:
                self._client = httpx.Client(
                    headers=DEFAULT_HEADERS,
                    timeout=20,
                    follow_redirects=True,
                    proxy=httpx_proxy_mounts(proxy),
                )
            except TypeError:
                self._client = httpx.Client(
                    headers=DEFAULT_HEADERS,
                    timeout=20,
                    follow_redirects=True,
                    proxies=httpx_proxy_mounts(proxy),
                )
        else:
            self._client = httpx.Client(
                headers=DEFAULT_HEADERS,
                timeout=20,
                follow_redirects=True,
            )
        self._proxy_url = proxy or ""

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
        CF/VIP sớm; tắt khi quét mục lục/danh sách để tránh false positive."""
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> BeautifulSoup:
            headers = {"Referer": self.cfg.base_url}
            if self.cfg.accept_language:
                headers["Accept-Language"] = self.cfg.accept_language
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            try:
                resp = self._client.get(url, headers=headers)
            except httpx.HTTPError:
                raise
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi tải {url}")
            encoding = self.cfg.encoding or resp.encoding or None
            html = decode_html_bytes(resp.content, preferred=encoding)
            if check_content_blockers:
                check_fetched_html(html, source_key=self.key, url=url)
            return BeautifulSoup(html, "lxml")

        try:
            soup = _fetch()
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
        return [
            ChapterRef(index=i, title=a.get_text(strip=True), url=self._abs_url(a["href"]))
            for i, a in enumerate(anchors, start=1)
            if a.get("href")
        ]

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
