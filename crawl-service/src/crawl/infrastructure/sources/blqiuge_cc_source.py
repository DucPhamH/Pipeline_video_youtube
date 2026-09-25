"""Adapter blqiuge.cc (笔趣阁) — HTML thuần, list /{slug}xiaoshuo/, mục lục
div.listmain, nội dung #content. Không phân trang thể loại thật (?page=N
trùng trang 1)."""
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class BlqiugeCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="blqiuge_cc",
                name="blqiuge.cc (笔趣阁)",
                base_url="https://www.blqiuge.cc",
                genre_item_selector="div.l ul li",
                genre_title_selector="span.s2 a",
                genre_latest_chapter_selector="span.s3 a",
                chapter_list_selector="div.listmain a",
                content_selector="#content",
                novel_title_selector=".book .info h2",
                novel_author_selector=".book .info .small span",
                novel_cover_selector=".book .info .cover img",
                strip_lines_containing=["笔趣阁", "blqiuge", "无弹窗"],
                novel_url_from_chapter=lambda u: u.rsplit("/", 1)[0] + "/",
            )
        )
