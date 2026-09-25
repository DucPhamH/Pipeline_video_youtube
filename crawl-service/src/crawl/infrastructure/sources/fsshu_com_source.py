"""Adapter RIÊNG cho fsshu.com — cấu trúc HTML gần giống bqgxs.com
(div.box.hot dl / book_list2 / article + chương chia trang), đã verify mạng thật."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class FsshuComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="fsshu_com",
                name="fsshu.com (笔趣阁)",
                base_url="http://www.fsshu.com",
                genre_item_selector="div.box.hot dl",
                genre_title_selector="dd h3 a",
                genre_latest_chapter_selector="dd.book_other a",
                chapter_list_selector="div.book_list2 a",
                content_selector="article",
                novel_title_selector="div.book_info h1, h1",
                strip_lines_containing=["笔趣阁", "fsshu.com", "www.fsshu.com"],
                paginated_content=True,
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str:
        return chapter_url.rsplit("/", 1)[0] + "/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if re.search(r"_\d+\.html$", url):
            return re.sub(r"_\d+\.html$", f"_{page}.html", url)
        if url.endswith("/"):
            return f"{url}{page}.html"
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}p={page}"
