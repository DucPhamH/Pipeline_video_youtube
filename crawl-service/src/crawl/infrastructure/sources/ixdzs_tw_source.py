"""Adapter ixdzs.tw (愛下電子書) — mirror Đài Loan, template /read/{id}/p{N}.html."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_READ_NOVEL = re.compile(r"/read/(\d+)/?$")
_READ_CHAPTER = re.compile(r"/read/(\d+)/p(\d+)\.html", re.I)
_CHAPTER_COUNT = re.compile(r"共\s*(\d+)\s*章")


class IxdzsTwSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="ixdzs_tw",
                name="ixdzs.tw (愛下電子書)",
                base_url="https://ixdzs.tw",
                content_locale="zh",
                accept_language="zh-TW,zh;q=0.9,en;q=0.8",
                genre_item_selector=".u-list li.burl",
                genre_title_selector="h3.bname a, .bname a",
                genre_latest_chapter_selector=".l-chapter a, .chapter a",
                chapter_list_selector="unused",
                content_selector=".page-content",
                novel_title_selector="h1, .book-title, .bookname h1",
                strip_lines_containing=["ixdzs", "愛下電子書", "上一章", "下一章", "目錄"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _READ_CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://ixdzs.tw/read/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        cleaned = re.sub(r"([?&])page=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}page={page}"

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _READ_NOVEL.search(novel_url.rstrip("/") + "/") or _READ_CHAPTER.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL truyện không hợp lệ: {novel_url}")
        book_id = m.group(1)
        index_url = f"https://ixdzs.tw/read/{book_id}/"

        soup = self._get_soup(index_url)
        html = str(soup)
        count_m = _CHAPTER_COUNT.search(html)
        if count_m:
            total = int(count_m.group(1))
            return [
                ChapterRef(
                    index=i,
                    title=f"第{i}章",
                    url=f"https://ixdzs.tw/read/{book_id}/p{i}.html",
                )
                for i in range(1, total + 1)
            ]

        chapters: list[ChapterRef] = []
        seen: set[int] = set()
        for a in soup.select('a[href*="/p"]'):
            href = a.get("href") or ""
            cm = _READ_CHAPTER.search(href)
            if not cm or cm.group(1) != book_id:
                continue
            idx = int(cm.group(2))
            if idx in seen:
                continue
            seen.add(idx)
            title = (a.get_text(strip=True) or f"第{idx}章").strip()
            chapters.append(
                ChapterRef(
                    index=idx,
                    title=title,
                    url=f"https://ixdzs.tw/read/{book_id}/p{idx}.html",
                )
            )
        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy chương tại {index_url} — site có thể đổi cấu trúc."
            )
        chapters.sort(key=lambda c: c.index)
        return chapters
