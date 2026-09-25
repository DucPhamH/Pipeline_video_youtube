"""Adapter biqvgeu.cc (顶点小说 / biqugeu) — /class/{n}_1.html, listmain, #content."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class BiqvgeuCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="biqvgeu_cc",
                name="biqvgeu.cc (顶点小说)",
                base_url="https://www.biqvgeu.cc",
                encoding="gbk",
                genre_item_selector="div.l ul li",
                genre_title_selector="span.s2 a",
                genre_latest_chapter_selector="span.s3 a",
                chapter_list_selector="div.listmain a",
                content_selector="#content",
                strip_lines_containing=["顶点小说", "biqvgeu", "笔趣阁"],
                novel_url_from_chapter=lambda u: u.rsplit("/", 1)[0] + "/",
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if re.search(r"/class/\d+_\d+\.html", url):
            return re.sub(r"/class/(\d+)_\d+\.html", rf"/class/\1_{page}.html", url)
        if "page=" in url:
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
