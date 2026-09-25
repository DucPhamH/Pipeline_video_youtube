"""Adapter dtruyen.com / dtruyen.net — CMS gần TruyenFull; cần CRAWL_PROXY_VN.

Selectors theo @duyquangnvx/webnovel-scraper (dtruyen config).
"""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_CHAPTER_PAGE = re.compile(r"/trang-(\d+)/?", re.I)


class DtruyenComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="dtruyen_com",
                name="DTruyen (dtruyen.com · cần proxy VN)",
                base_url="https://dtruyen.com",
                content_locale="vi",
                accept_language="vi,en;q=0.8",
                genre_item_selector=".list-truyen .row, .list-truyen .row[itemtype]",
                genre_title_selector="h3.truyen-title a, .truyen-title a",
                genre_latest_chapter_selector=".chapter-text, .author",
                chapter_list_selector="ul.list-chapter li a",
                content_selector="#chapter-c, .chapter-c",
                novel_title_selector="h1.title, h3.title",
                novel_author_selector='.info a[itemprop="author"]',
                novel_cover_selector='[itemprop="image"]',
                strip_lines_containing=["dtruyen", "quảng cáo", "bình luận"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = re.match(r"^(https?://[^/]+/[^/]+/)chuong-\d+", chapter_url, re.I)
        return m.group(1) if m else None

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        base = url.rstrip("/")
        if re.search(r"/trang-\d+/?$", base):
            return re.sub(r"/trang-\d+/?$", f"/trang-{page}/", base)
        return f"{base}/trang-{page}/"

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        base = novel_url.split("#")[0].rstrip("/") + "/"
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        max_page = 1
        page = 1
        while page <= max_page and page <= 40:
            url = base if page == 1 else f"{base}trang-{page}/"
            soup = self._get_soup(url)
            for a in soup.select(self.cfg.chapter_list_selector):
                href = a.get("href") or ""
                if not href:
                    continue
                abs_url = self._abs_url(href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=a.get_text(strip=True),
                        url=abs_url,
                    )
                )
            for a in soup.select(".pagination a[href], ul.pagination a[href]"):
                m = _CHAPTER_PAGE.search(a.get("href") or "")
                if m:
                    max_page = max(max_page, int(m.group(1)))
            page += 1
        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không có chương tại {novel_url} — cần CRAWL_PROXY_VN?"
            )
        return chapters
