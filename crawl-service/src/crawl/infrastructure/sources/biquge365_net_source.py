"""Adapter RIÊNG cho biquge365.net — danh sách ul.wanben, mục lục đầy đủ
ở /newbook/{id}/ (không phải /book/{id}/), nội dung #txt. Đã verify mạng thật."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class Biquge365NetSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="biquge365_net",
                name="biquge365.net (新笔趣阁)",
                base_url="https://www.biquge365.net",
                genre_item_selector="ul.wanben li",
                genre_title_selector="h3.p2 a",
                chapter_list_selector='a[href*="/chapter/"]',
                content_selector="#txt",
                novel_title_selector="h1",
                strip_lines_containing=["笔趣阁", "biquge365", "一秒记住"],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        """Trang /book/{id}/ chỉ có vài chương mới — TOC đầy đủ ở /newbook/{id}/."""
        m = re.search(r"/(?:book|newbook)/(\d+)", novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] Không suy ra id truyện từ {novel_url}")
        toc_url = f"{self.cfg.base_url.rstrip('/')}/newbook/{m.group(1)}/"
        soup = self._get_soup(toc_url)
        anchors = soup.select(self.cfg.chapter_list_selector)
        if not anchors:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy chương với selector "
                f"'{self.cfg.chapter_list_selector}' tại {toc_url}"
            )
        seen: set[str] = set()
        chapters: list[ChapterRef] = []
        for a in anchors:
            href = a.get("href")
            if not href or href in seen:
                continue
            title = a.get_text(strip=True)
            if not title or title in ("开始阅读", "全部章节目录"):
                continue
            seen.add(href)
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=self._abs_url(href))
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Mục lục rỗng tại {toc_url}")
        # TOC site này trộn thứ tự (mới nhất trước / lệch phân đoạn) — sắp theo
        # số trong tiêu đề khi có, giữ ổn định với index gốc làm tie-break.
        def _sort_key(ch: ChapterRef) -> tuple[int, int]:
            m = re.search(r"(\d+)", ch.title)
            return (int(m.group(1)) if m else 10**9, ch.index)

        chapters.sort(key=_sort_key)
        return [
            ChapterRef(index=i, title=ch.title, url=ch.url)
            for i, ch in enumerate(chapters, start=1)
        ]

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str:
        """.../chapter/{id}/{chap}.html -> .../book/{id}/"""
        m = re.search(r"/chapter/(\d+)/", chapter_url)
        if not m:
            return chapter_url
        return f"https://www.biquge365.net/book/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """/sort/1_1/ -> /sort/1_{page}/"""
        return re.sub(r"/sort/(\d+)_\d+/", rf"/sort/\1_{page}/", url)
