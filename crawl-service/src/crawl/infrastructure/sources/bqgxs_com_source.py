"""Adapter RIÊNG cho bqgxs.com — kế thừa `BaseHtmlSource`. Site này có 3
dạng URL "danh sách" khác nhau (thể loại/xếp hạng/search) và hỗ trợ suy ra
mục lục từ URL 1 chương — cả 2 đặc điểm RIÊNG của site này khai báo ngay ở
đây, không lẫn với adapter site khác (sửa 17/9/2026)."""
import re

from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class BqgxsComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="bqgxs_com",
                name="bqgxs.com",
                base_url="https://www.bqgxs.com",
                # Đã soi HTML THẬT (15/9/2026 + 16/9/2026), hoạt động đầy đủ
                # (danh sách, chi tiết, nội dung chương đều verify được bằng
                # mạng thật). KHÔNG có mục "Kinh dị" riêng trong nav -> dùng
                # trang /search.php?q=<từ khoá> làm "trang thể loại" cho
                # riêng Kinh dị. 8 thể loại còn lại (nav thật:
                # 玄幻/武侠/都市/历史/网游/科幻/言情/其他) có trang riêng
                # /list1/../list8/, CÙNG khuôn dạng dl/dt/dd với trang search
                # nên dùng chung 1 selector.
                genre_item_selector="div.box.hot dl",
                genre_title_selector="dd h3 a",
                genre_latest_chapter_selector="dd.book_other a",
                chapter_list_selector="div.book_list2 a",
                content_selector="article",
                novel_title_selector="div.book_info h1, h1",
                novel_author_selector="div.book_info span, div.book_info p",
                novel_cover_selector="div.book_info img, div.bookimg img",
                strip_lines_containing=["笔趣阁小说网", "www.bqgxs.com"],
                paginated_content=True,  # chương dài bị chia nhiều trang: xxx.html, xxx_2.html...
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str:
        """URL chương dạng .../131/131542/275597.html -> mục lục là
        .../131/131542/ (bỏ segment cuối) — quy luật ổn định, đã verify
        bằng HTML thật (15/9/2026)."""
        return chapter_url.rsplit("/", 1)[0] + "/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """3 dạng URL "danh sách" khác nhau trên site này, đều đã verify
        bằng HTML thật: trang xếp hạng `/top/all_0_1.html` phân trang bằng
        cách đổi số cuối (`_1.html` -> `_2.html`), trang thể loại `/listN/`
        phân trang bằng cách thêm `{page}.html` sau dấu `/` (`/list1/` ->
        `/list1/2.html`, 16/9/2026), trang search `/search.php?q=...`
        phân trang bằng `&p=N`."""
        if re.search(r"_\d+\.html$", url):
            return re.sub(r"_\d+\.html$", f"_{page}.html", url)
        if url.endswith("/"):
            return f"{url}{page}.html"
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}p={page}"
