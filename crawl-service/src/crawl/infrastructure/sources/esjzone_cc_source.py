"""Adapter esjzone.cc (ESJ Zone) — light novel / 原創 tiếng Trung (Đài).

Danh sách theo tag/list HTML; chương trên forum thread; nội dung
`.forum-content`. Không Cloudflare từ VN (đã verify 22/9/2026).
"""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_DETAIL = re.compile(r"/detail/(\d+)\.html", re.I)
_FORUM_CH = re.compile(r"/forum/(\d+)/(\d+)\.html", re.I)


class EsjzoneCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="esjzone_cc",
                name="ESJ Zone (esjzone.cc)",
                base_url="https://www.esjzone.cc",
                content_locale="zh",
                accept_language="zh-TW,zh;q=0.9,en;q=0.5",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="#chapterList a[href*='/forum/']",
                content_selector=".forum-content",
                novel_title_selector="h1, .book-detail h2, .col-md-9 h2",
                novel_author_selector='.book-detail a[href*="/tags/"], .book-detail li',
                novel_cover_selector=".product-gallery img, .book-img img",
                strip_lines_containing=[
                    "esjzone",
                    "ESJ Zone",
                    "下一篇",
                    "上一篇",
                    "回目錄",
                    "目錄",
                ],
                request_delay_sec=1.2,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _FORUM_CH.search(chapter_url)
        if not m:
            return None
        return f"https://www.esjzone.cc/detail/{m.group(1)}.html"

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        # Tag/list hiện không phân trang ổn định (?page=2 trùng trang 1).
        if page != 1:
            return []
        soup = self._get_soup(genre_list_url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/detail/']"):
            href = (a.get("href") or "").strip()
            m = _DETAIL.search(href)
            if not m:
                continue
            title = (a.get_text(strip=True) or "").strip()
            if len(title) < 2:
                continue
            url = self._abs_url(href)
            if url in seen:
                continue
            seen.add(url)
            results.append(NovelRef(title=title, url=url, latest_chapter_title=""))
        if not results:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy truyện tại {genre_list_url}"
            )
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select(self.cfg.chapter_list_selector):
            href = a.get("href") or ""
            if not _FORUM_CH.search(href):
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            title = (a.get_text(strip=True) or "").strip() or f"Ch.{len(chapters) + 1}"
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không có chương tại {novel_url}")
        return chapters
