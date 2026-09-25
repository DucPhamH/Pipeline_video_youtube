"""Adapter RIÊNG cho powanjuan.cc (破万卷) — encoding GBK, danh sách theo
thư mục thể loại (/wxxz/, /ghxy/...), mục lục .catalog, nội dung div.content.
Đã verify mạng thật."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class PowanjuanCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="powanjuan_cc",
                name="powanjuan.cc (破万卷)",
                base_url="https://www.powanjuan.cc",
                encoding="gbk",
                genre_item_selector="li div.title",
                genre_title_selector="strong a, a",
                chapter_list_selector=".catalog a",
                content_selector="div.content",
                novel_title_selector="h1",
                strip_lines_containing=["破万卷", "powanjuan", "作者：", "简介："],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        """/view/{cat}-{id}-{n}.html — không suy ra ổn định từ mọi dạng → None."""
        return None

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """/wxxz/ -> /wxxz/index_2.html ; /wxxz/index_3.html -> index_{page}."""
        if page <= 1:
            return url
        if re.search(r"index_\d+\.html$", url):
            return re.sub(r"index_\d+\.html$", f"index_{page}.html", url)
        if url.endswith("/"):
            return f"{url}index_{page}.html"
        return f"{url.rstrip('/')}/index_{page}.html"
