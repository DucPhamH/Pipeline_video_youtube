"""Adapter bxg123.cc (笔仙阁) — encoding GBK, cùng họ powanjuan."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class Bxg123CcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="bxg123_cc",
                name="bxg123.cc (笔仙阁)",
                base_url="https://bxg123.cc",
                encoding="gbk",
                genre_item_selector="li div.title",
                genre_title_selector="strong a, a",
                chapter_list_selector=".catalog a",
                content_selector="div.content",
                strip_lines_containing=["笔仙阁", "bxg123", "作者：", "简介："],
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if re.search(r"index_\d+\.html$", url):
            return re.sub(r"index_\d+\.html$", f"index_{page}.html", url)
        if url.endswith("/"):
            return f"{url}index_{page}.html"
        return f"{url.rstrip('/')}/index_{page}.html"
