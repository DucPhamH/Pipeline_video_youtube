"""Adapter RIÊNG cho bgq99.cc (顶点小说网) — template biquge cổ điển,
đã verify HTTP thật: danh sách /xuanhuan/?page=N, mục lục div.listmain,
nội dung #content."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class Bgq99CcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="bgq99_cc",
                name="bgq99.cc (顶点小说)",
                base_url="https://www.bgq99.cc",
                genre_item_selector="div.l ul li",
                genre_title_selector="span.s2 a",
                genre_latest_chapter_selector="span.s3 a",
                chapter_list_selector="div.listmain a",
                content_selector="#content",
                novel_title_selector="h1",
                novel_author_selector="#info p",
                novel_cover_selector="#fmimg img, div.cover img",
                strip_lines_containing=["顶点小说", "bgq99", "笔趣阁"],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str:
        """.../book/{id}/{chap}.html -> .../book/{id}/"""
        return chapter_url.rsplit("/", 1)[0] + "/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if "page=" in url:
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
