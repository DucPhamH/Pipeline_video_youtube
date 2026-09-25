"""Adapter bqg2.com — danh sách li/h2, chương /read/{id}/..., nội dung article."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class Bqg2ComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="bqg2_com",
                name="bqg2.com (笔趣阁2.0)",
                base_url="https://www.bqg2.com",
                genre_item_selector="li:has(h2)",
                genre_title_selector="h2 a, div.w100 > a",
                chapter_list_selector='a[href*="/read/"]',
                content_selector="article",
                strip_lines_containing=["笔趣阁", "bqg2"],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = re.search(r"/read/(\d+)/", chapter_url)
        if not m:
            return None
        return f"https://www.bqg2.com/book/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        # /sort/1/1/ -> /sort/1/{page}/
        return re.sub(r"/sort/(\d+)/\d+/", rf"/sort/\1/{page}/", url)
