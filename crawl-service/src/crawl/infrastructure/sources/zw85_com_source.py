"""Adapter 85zw.com (八五中文网) — template cổ điển div.l / listmain / #content."""
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class Zw85ComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="zw85_com",
                name="85zw.com (八五中文)",
                base_url="https://www.85zw.com",
                genre_item_selector="div.l ul li",
                genre_title_selector="span.s2 a",
                genre_latest_chapter_selector="span.s3 a",
                chapter_list_selector="div.listmain a",
                content_selector="#content",
                strip_lines_containing=["八五中文", "85zw"],
                novel_url_from_chapter=lambda u: u.rsplit("/", 1)[0] + "/",
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if url.endswith("/"):
            return f"{url}{page}.html"
        return f"{url.rstrip('/')}/{page}.html"
