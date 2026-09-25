"""Adapter 8tsw.com (笔趣阁 / biquge.tv mirror) — #list a, #content."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class EightsTwComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="eights_tw_com",
                name="8tsw.com (笔趣阁)",
                base_url="https://www.8tsw.com",
                encoding="gbk",
                genre_item_selector="div.l ul li",
                genre_title_selector="span.s2 a",
                genre_latest_chapter_selector="span.s3 a",
                chapter_list_selector="#list a",
                content_selector="#content",
                strip_lines_containing=["笔趣阁", "8tsw", "biquge"],
                novel_url_from_chapter=lambda u: u.rsplit("/", 1)[0] + "/",
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if "page=" in url:
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
