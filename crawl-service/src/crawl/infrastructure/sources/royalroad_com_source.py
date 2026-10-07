"""Adapter royalroad.com — web novel EN (Best Rated / Complete / …)."""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_FICTION = re.compile(r"/fiction/(\d+)(?:/[^/]*)?/?$", re.I)
_CHAPTER = re.compile(r"/fiction/(\d+)/[^/]+/chapter/(\d+)", re.I)


class RoyalroadComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="royalroad_com",
                name="Royal Road (royalroad.com)",
                base_url="https://www.royalroad.com",
                content_locale="en",
                accept_language="en-US,en;q=0.9",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/chapter/"]',
                content_selector=".chapter-content",
                novel_title_selector="h1",
                novel_author_selector="h4 a[href*='/profile/'], .portait-title a",
                novel_cover_selector=".cover-art-container img, .thumbnail img",
                strip_lines_containing=[
                    "royalroad.com",
                    "Royal Road",
                    "Advertisement",
                    "Support Royal Road",
                ],
                request_delay_sec=1.0,
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
        return f"https://www.royalroad.com/fiction/{m.group(1)}"

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select("h2.fiction-title a, .fiction-title a"):
            href = (a.get("href") or "").split("?")[0]
            m = re.search(r"/fiction/(\d+)", href)
            if not m:
                continue
            title = a.get_text(strip=True)
            if len(title) < 2:
                continue
            abs_url = f"https://www.royalroad.com/fiction/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được fiction tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        fiction_m = re.search(r"/fiction/(\d+)", novel_url)
        fiction_id = fiction_m.group(1) if fiction_m else ""
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('table#chapters a[href*="/chapter/"], #chapters a[href*="/chapter/"]'):
            href = a.get("href") or ""
            m = _CHAPTER.search(href)
            if not m or (fiction_id and m.group(1) != fiction_id):
                continue
            abs_url = href if href.startswith("http") else f"https://www.royalroad.com{href}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            title = a.get_text(strip=True) or f"Chapter {len(chapters) + 1}"
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không thấy chương tại {novel_url}")
        return chapters
