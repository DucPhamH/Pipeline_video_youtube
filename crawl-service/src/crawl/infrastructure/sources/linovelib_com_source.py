"""Adapter linovelib.com (哔哩轻小说) — catalog `/novel/{id}/catalog`,
nội dung `#TextContent`. List dùng top rank (wenku/category thường CF).
Font-obfuscation phức tạp bỏ qua (chương thường vẫn đọc được). Tham khảo
novel-downloader plugins/sites/linovelib."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVEL = re.compile(r"/novel/(\d+)\.html")
_CHAPTER = re.compile(r"/novel/(\d+)/(\d+)\.html")


class LinovelibComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="linovelib_com",
                name="linovelib.com (哔哩轻小说)",
                base_url="https://www.linovelib.com",
                genre_item_selector=".rank_d_list",
                genre_title_selector='a[href*="/novel/"]',
                chapter_list_selector='a[href*="/novel/"]',
                content_selector="#TextContent",
                novel_title_selector="h1.book-name, h1",
                strip_lines_containing=["linovelib", "哔哩轻小说", "上一页", "下一页", "目录"],
                request_delay_sec=1.5,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        items = soup.select(self.cfg.genre_item_selector)
        results: list[NovelRef] = []
        seen: set[str] = set()
        if items:
            for item in items:
                link = item.select_one('a[href*="/novel/"]')
                if link is None or not link.get("href"):
                    continue
                href = link["href"]
                if not _NOVEL.search(href):
                    continue
                title = (
                    (item.get("title") or "").strip()
                    or (link.get("title") or "").strip()
                    or link.get_text(strip=True)
                )
                img = item.select_one("img[alt]")
                if img and img.get("alt"):
                    title = img["alt"].strip() or title
                if not title:
                    continue
                abs_url = self._abs_url(href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                results.append(
                    NovelRef(title=title, url=abs_url, latest_chapter_title="")
                )
        else:
            # fallback: mọi link novel trên trang
            for a in soup.select('a[href*="/novel/"]'):
                href = a.get("href") or ""
                if not _NOVEL.search(href):
                    continue
                title = (a.get_text(strip=True) or "").strip()
                if not title:
                    continue
                abs_url = self._abs_url(href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                results.append(
                    NovelRef(title=title, url=abs_url, latest_chapter_title="")
                )
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _NOVEL.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL truyện không hợp lệ: {novel_url}")
        catalog_url = f"https://www.linovelib.com/novel/{m.group(1)}/catalog"
        soup = self._get_soup(catalog_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href]'):
            href = a.get("href") or ""
            cm = _CHAPTER.search(href)
            if not cm or cm.group(1) != m.group(1):
                continue
            if "vol_" in href:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {catalog_url}")
        return chapters

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.linovelib.com/novel/{m.group(1)}.html"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """/top/monthvisit/1.html -> /top/monthvisit/{page}.html"""
        if page <= 1:
            return url
        if re.search(r"/\d+\.html$", url):
            return re.sub(r"/\d+\.html$", f"/{page}.html", url)
        return url
