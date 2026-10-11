"""Adapter book.sfacg.com (SF轻小说) — free chapters tại /Novel/{id}/{vol}/{cid}/."""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVEL = re.compile(r"/Novel/(\d+)/?", re.I)
_FREE_CH = re.compile(r"/Novel/(\d+)/(\d+)/(\d+)/?", re.I)


class SfacgComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="sfacg_com",
                name="SFACG (book.sfacg.com · SF轻小说)",
                base_url="https://book.sfacg.com",
                content_locale="zh",
                accept_language="zh-CN,zh;q=0.9",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/Novel/"]',
                content_selector="#ChapterBody, .article-content",
                novel_title_selector="h1, .title h1",
                strip_lines_containing=["sfacg", "SF轻小说", "本章字数", "上一章", "下一章"],
                request_delay_sec=1.2,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if re.search(r"[?&]page=\d+", url, re.I):
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url, flags=re.I)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _FREE_CH.search(chapter_url) or _NOVEL.search(chapter_url)
        if not m:
            return None
        return f"https://book.sfacg.com/Novel/{m.group(1)}/"

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
        for a in soup.select('a[href*="/Novel/"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _NOVEL.search(href)
            if not m or _FREE_CH.search(href):
                continue
            title = a.get_text(strip=True)
            if len(title) < 2:
                continue
            abs_url = f"https://book.sfacg.com/Novel/{m.group(1)}/"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _NOVEL.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL không hợp lệ: {novel_url}")
        nid = m.group(1)
        index_url = f"https://book.sfacg.com/Novel/{nid}/MainIndex/"
        soup = self._get_soup(index_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/Novel/"]'):
            href = a.get("href") or ""
            cm = _FREE_CH.search(href)
            if not cm or cm.group(1) != nid:
                continue
            abs_url = href if href.startswith("http") else f"https://book.sfacg.com{href}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            title = a.get_text(strip=True)
            if title.upper().startswith("VIP"):
                continue
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title or f"第{len(chapters)+1}章", url=abs_url)
            )
        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không có chương free tại {index_url} (VIP-only?)"
            )
        return chapters
