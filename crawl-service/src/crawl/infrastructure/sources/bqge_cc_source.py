"""Adapter bqge.cc — div.category-div, chương /read/{id}/..., nội dung article."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class BqgeCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="bqge_cc",
                name="bqge.cc (新笔趣阁)",
                base_url="https://www.bqge.cc",
                genre_item_selector="div.category-div",
                genre_title_selector="div.commend-title a, h3",
                chapter_list_selector='a[href*="/read/"]',
                content_selector="article",
                strip_lines_containing=["笔趣阁", "bqge", "一秒记住"],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = re.search(r"/read/(\d+)/", chapter_url)
        if not m:
            return None
        return f"https://www.bqge.cc/book/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        # /sort/xuanhuan/1/ -> /sort/xuanhuan/{page}/
        return re.sub(r"/sort/([a-z]+)/\d+/", rf"/sort/\1/{page}/", url)
