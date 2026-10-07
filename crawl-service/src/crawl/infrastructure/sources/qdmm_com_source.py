"""Adapter qdmm.com / Qidian nữ (起点女生) — cùng anti-bot họ Qidian.

Dùng BaseBrowserSource; cookie session Yuewen (ywguid…) khuyến nghị.
"""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_browser_source import BaseBrowserSource
from crawl.infrastructure.sources.base_html_source import SourceConfig
from crawl.infrastructure.sources.tls_fetch import looks_like_cloudflare_challenge

_BOOK = re.compile(r"/book/(\d+)")
_CHAPTER = re.compile(r"/chapter/(\d+)/(\d+)")


class QdmmComSource(BaseBrowserSource):
    browser_wait_selector = "a[href*='/book/'], #viewer, .main-text-wrap"
    prefer_tls_first = False

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="qdmm_com",
                name="QDMM (qdmm.com · 起点女生 · cần cookie)",
                base_url="https://www.qdmm.com",
                content_locale="zh",
                accept_language="zh-CN,zh;q=0.9",
                genre_item_selector=".book-img-text li, .all-book-list li",
                genre_title_selector='a[href*="/book/"]',
                chapter_list_selector='a[href*="/chapter/"]',
                content_selector=".main-text-wrap, #viewer",
                novel_title_selector="h1, .book-info h1",
                strip_lines_containing=["起点", "qdmm", "qidian", "本章字数"],
                request_delay_sec=2.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if re.search(r"[?&]page=\d+", url):
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.qdmm.com/book/{m.group(1)}/"

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        html = str(soup)
        if len(html) < 2000 or ("seqid" in html and "book" not in html.lower()):
            raise ScrapeError(
                f"[{self.key}] Anti-bot QDMM/Qidian — dán cookie session "
                f"(ywguid…) rồi thử lại: {url}"
            )
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/book/"]'):
            href = a.get("href") or ""
            if not _BOOK.search(href):
                continue
            title = a.get_text(strip=True)
            if len(title) < 2:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/chapter/"]'):
            href = a.get("href") or ""
            if not _CHAPTER.search(href):
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
            raise ScrapeError(
                f"[{self.key}] Không thấy chương (cần cookie): {novel_url}"
            )
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        html = self._fetch_html(chapter_url, check_content_blockers=True)
        if looks_like_cloudflare_challenge(html):
            raise ScrapeError(f"[{self.key}] Cloudflare tại {chapter_url}")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(f"[{self.key}] Không parse được nội dung tại {chapter_url}")
        paras = [
            p.get_text("\n", strip=True)
            for p in node.select("p")
            if p.get_text(strip=True)
        ]
        text = "\n".join(paras) if paras else node.get_text("\n", strip=True)
        if len(text) < 40:
            raise ScrapeError(
                f"[{self.key}] Nội dung rỗng/VIP tại {chapter_url} — cần cookie có quyền đọc."
            )
        return text
