"""Adapter zhihu.com — 盐选专栏 (market/paid_column) + 章节 section.

Thiết kế (MVP trong Crawl):

1. **Luồng chính**: Thêm truyện bằng URL cột
   ``https://www.zhihu.com/market/paid_column/<id>``
   (hoặc 1 section → tự suy ra cột).
2. **Auth**: cookie phiên UI bắt buộc — cần ``z_c0`` (đăng nhập) + ``d_c0``
   (ký ``x-zse-96``). Không có hội viên/đã mua → nội dung trống / paywall.
3. **Chữ ký**: ``zhihu_sign.generate_zhihu_sign`` (MediaCrawler / salt-downloader).
4. **Quét thể loại**: Zhihu 盐选 không có nav genre kiểu biquge — seed
   ``other`` trỏ market; list chỉ lấy link paid_column trên trang (nếu có).
   Khuyến nghị dùng Thêm URL, không phụ thuộc quét genre.

Không hỗ trợ (MVP): story.zhihu.com/manuscript (chỉ APP), 视频, 想法.
Đổi ``story…/manuscript/paid_column/ID`` → ``www…/market/paid_column/ID``.
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import check_fetched_html
from crawl.infrastructure.sources.zhihu_sign import XZSE_93_VERSION, generate_zhihu_sign
from platform_.session_cookies import parse_cookie_header

_COLUMN_RE = re.compile(
    r"https?://(?:www\.)?zhihu\.com/market/paid_column/(\d+)/?(?:section/(\d+))?/?",
    re.I,
)
_STORY_MS_RE = re.compile(
    r"https?://story\.zhihu\.com/manuscript/paid_column/(\d+)(?:/(\d+))?",
    re.I,
)
_CONTENT_SELECTORS = (
    "div.RichText",
    "div.Post-RichTextContainer",
    "div.RichContent-inner",
    "article",
    "div.Post-RichText",
)


class ZhihuComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="zhihu_com",
                name="知乎盐选 (zhihu.com · cần cookie)",
                base_url="https://www.zhihu.com",
                content_locale="zh",
                accept_language="zh-CN,zh;q=0.9,en;q=0.5",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="a[href*='/section/']",
                content_selector="div.RichText",
                novel_title_selector='meta[property="og:title"], h1.Post-Title, h1',
                request_delay_sec=1.5,
                max_retries=2,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    # ------------------------------------------------------------------ auth / fetch
    def _cookie_dict(self) -> dict[str, str]:
        self._apply_user_session()
        return parse_cookie_header(getattr(self, "_session_cookie_header", "") or "")

    def _require_session(self) -> dict[str, str]:
        cookies = self._cookie_dict()
        if not cookies.get("z_c0"):
            raise ScrapeError(
                f"[{self.key}] Thiếu cookie z_c0 — đăng nhập Zhihu trên trình duyệt, "
                "copy Cookie header (cần cả z_c0 và d_c0) vào Phiên đăng nhập site này."
            )
        if not cookies.get("d_c0"):
            raise ScrapeError(
                f"[{self.key}] Thiếu cookie d_c0 (cần để ký x-zse-96). "
                "Mở www.zhihu.com đã login → F5 → copy lại toàn bộ Cookie header."
            )
        return cookies

    def _normalize_url(self, url: str) -> str:
        m = _STORY_MS_RE.search(url)
        if m:
            col, sec = m.group(1), m.group(2)
            if sec:
                return f"https://www.zhihu.com/market/paid_column/{col}/section/{sec}"
            return f"https://www.zhihu.com/market/paid_column/{col}"
        return url

    def _signed_headers(self, url: str, cookies: dict[str, str]) -> dict[str, str]:
        headers = {
            "Referer": "https://www.zhihu.com/",
            "Accept-Language": self.cfg.accept_language or "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        # Cookie header từ session UI (giữ nguyên thứ tự user dán)
        raw = getattr(self, "_session_cookie_header", "") or ""
        if raw:
            headers["Cookie"] = raw
        sign = generate_zhihu_sign(url, cookies)
        if sign:
            headers["x-zse-96"] = sign["x-zse-96"]
            headers["x-zst-81"] = sign["x-zst-81"]
            headers["x-zse-93"] = XZSE_93_VERSION
        return headers

    def _get_soup(self, url: str, *, check_content_blockers: bool = False) -> BeautifulSoup:
        url = self._normalize_url(url)
        cookies = self._require_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> BeautifulSoup:
            headers = self._signed_headers(url, cookies)
            resp = self._client.get(url, headers=headers)
            if resp.status_code in (401, 403):
                raise ScrapeError(
                    f"[{self.key}] HTTP {resp.status_code} — cookie hết hạn / chưa đủ quyền "
                    f"盐选 tại {url}"
                )
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi tải {url}")
            html = resp.text
            if check_content_blockers:
                check_fetched_html(html, source_key=self.key, url=url)
            low = html[:4000].lower()
            if "请先登录" in html or "登录知乎" in html[:2000]:
                raise ScrapeError(
                    f"[{self.key}] Trang yêu cầu đăng nhập — cập nhật cookie z_c0: {url}"
                )
            if "just a moment" in low or "cloudflare" in low:
                raise ScrapeError(
                    f"[{self.key}] Bị Cloudflare/verify — thử lại sau hoặc dùng proxy CN: {url}"
                )
            return BeautifulSoup(html, "lxml")

        try:
            soup = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không tải được {url} sau {self.cfg.max_retries + 1} lần: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return soup

    # ------------------------------------------------------------------ SourcePort
    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """盐选 không có genre ổn định — chỉ gom link paid_column trên trang seed.

        Trang > 1 → []. Khuyến nghị: Thêm truyện bằng URL cột.
        """
        if page != 1:
            return []
        soup = self._get_soup(genre_list_url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/market/paid_column/']"):
            href = (a.get("href") or "").strip()
            if "/section/" in href:
                continue
            m = _COLUMN_RE.search(urljoin(self.cfg.base_url, href))
            if not m:
                continue
            col_url = f"https://www.zhihu.com/market/paid_column/{m.group(1)}"
            if col_url in seen:
                continue
            title = (a.get_text(strip=True) or a.get("title") or "").strip()
            if len(title) < 2:
                continue
            seen.add(col_url)
            results.append(NovelRef(title=title, url=col_url, latest_chapter_title=""))
        if not results:
            raise ScrapeError(
                f"[{self.key}] Không thấy cột 盐选 trên {genre_list_url}. "
                "Zhihu không quét thể loại như biquge — hãy dùng "
                "「Thêm truyện bằng URL」 với link "
                "https://www.zhihu.com/market/paid_column/<id> "
                "(cần cookie + quyền đọc)."
            )
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        novel_url = self._normalize_url(novel_url)
        # Nếu user dán section → lấy cột rồi list
        m = _COLUMN_RE.search(novel_url)
        if m and m.group(2):
            novel_url = f"https://www.zhihu.com/market/paid_column/{m.group(1)}"
        if "/market/paid_column/" not in novel_url:
            raise ScrapeError(
                f"[{self.key}] URL phải là cột 盐选 "
                f"/market/paid_column/<id> (không phải APP story.zhihu.com): {novel_url}"
            )
        soup = self._get_soup(novel_url)
        col_path = urlparse(novel_url).path.rstrip("/")
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/section/']"):
            href = (a.get("href") or "").strip()
            abs_url = self._abs_url(href)
            parsed = urlparse(abs_url)
            if not parsed.path.startswith(col_path + "/"):
                continue
            if abs_url in seen:
                continue
            seen.add(abs_url)
            title = (
                a.get_text(strip=True)
                or (a.get("title") or "")
                or f"第{len(chapters) + 1}章"
            ).strip()
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không parse được mục lục section tại {novel_url} — "
                "cookie/quyền 盐选? hoặc trang SPA chưa hydrate (thử lại / cập nhật cookie)."
            )
        return chapters

    def fetch_novel_title(self, novel_url: str) -> str | None:
        novel_url = self._normalize_url(novel_url)
        m = _COLUMN_RE.search(novel_url)
        if m and m.group(2):
            novel_url = f"https://www.zhihu.com/market/paid_column/{m.group(1)}"
        try:
            soup = self._get_soup(novel_url)
        except ScrapeError:
            return None
        og = soup.select_one('meta[property="og:title"]')
        if og and og.get("content"):
            return og["content"].strip()
        for sel in ("h1.Post-Title", "h1"):
            node = soup.select_one(sel)
            if node:
                t = node.get_text(strip=True)
                if t:
                    return t
        title = soup.select_one("title")
        return title.get_text(strip=True) if title else None

    def fetch_chapter_content(self, chapter_url: str) -> str:
        chapter_url = self._normalize_url(chapter_url)
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = None
        for sel in _CONTENT_SELECTORS:
            node = soup.select_one(sel)
            if node is not None:
                break
        if node is None:
            text_probe = soup.get_text(" ", strip=True)[:500]
            if "开通" in text_probe or "会员" in text_probe or "购买" in text_probe:
                raise ScrapeError(
                    f"[{self.key}] Nội dung khoá (cần 盐选会员/đã mua): {chapter_url}"
                )
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy khối RichText tại {chapter_url}"
            )
        for tag in node.select("script, style, noscript, svg, iframe, button"):
            tag.decompose()
        lines = [
            ln.strip()
            for ln in node.get_text("\n", strip=True).splitlines()
            if ln.strip()
        ]
        body = "\n".join(lines)
        if len(body) < 40:
            raise ScrapeError(
                f"[{self.key}] Nội dung quá ngắn (paywall/SPA?): {chapter_url}"
            )
        # Bỏ dòng quảng cáo membership thô
        filtered = [
            ln
            for ln in lines
            if "盐选会员" not in ln and "开通会员" not in ln and "zhihu.com" not in ln.lower()
        ]
        return "\n".join(filtered) if len("\n".join(filtered)) >= 40 else body

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _STORY_MS_RE.search(chapter_url)
        if m:
            return f"https://www.zhihu.com/market/paid_column/{m.group(1)}"
        m2 = _COLUMN_RE.search(chapter_url)
        if m2:
            return f"https://www.zhihu.com/market/paid_column/{m2.group(1)}"
        return None
