"""Adapter RIÊNG cho shubaow.net (书宝网) — biquge-clone tiếng Trung, thiên về
言情/耽美/百合 (ngôn tình/đam mỹ/bách hợp) thay vì huyền huyễn nam văn như
bqgxs/fsshu. Cấu trúc HTML khác hẳn 2 site đó (table.table thay vì
div.box.hot dl, chapter-item-link thay vì book_list2) — đã soi HTML THẬT
(17/9/2026): trang chủ, trang thể loại /list/{n}.html (phân trang
/list/{n}/{page}.html), trang chi tiết truyện /book/{id}.html (mục lục
a.chapter-item-link), trang chương /book/{id}/{chapterId}.html
(div.read-content-body, encoding GBK) — không VIP.

QUAN TRỌNG: site có Cloudflare theo TLS fingerprint — httpx thuần (tầng 1)
bị chặn 403 "Just a moment..." dù `curl` CLI thường lại lọt qua (verify
bằng cả httpx.get lẫn `curl` thật cùng lúc, 17/9/2026: httpx 403, curl 200
cùng URL cùng User-Agent — chỉ khác TLS fingerprint). `curl_cffi`
(impersonate=chrome136, `tls_fetch.py`) lọt qua sạch (200, không phải
challenge) nên dùng `BaseBrowserSource` với `tls_only=True` (không cần
Playwright)."""
import re

from crawl.infrastructure.sources.base_browser_source import BaseBrowserSource
from crawl.infrastructure.sources.base_html_source import SourceConfig


class ShubaowNetSource(BaseBrowserSource):
    tls_only = True

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="shubaow_net",
                name="shubaow.net (书宝网)",
                base_url="https://www.shubaow.net",
                encoding="gbk",
                genre_item_selector="table.table tbody tr",
                genre_title_selector="td:nth-of-type(1) a",
                genre_latest_chapter_selector="td:nth-of-type(2) a",
                chapter_list_selector="a.chapter-item-link",
                content_selector="div.read-content-body",
                novel_title_selector="h1.book-title-meta",
                strip_lines_containing=["书宝网", "shubaow.net", "www.shubaow.net"],
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str:
        """URL chương .../book/422/65192.html -> mục lục .../book/422.html
        (verify bằng HTML thật 17/9/2026)."""
        return re.sub(r"/(\d+)/\d+\.html$", r"/\1.html", chapter_url)

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """.../list/1.html (trang 1) -> .../list/1/{page}.html (verify bằng
        HTML thật: pagination thấy /list/1/2.html, /list/1/95.html...)."""
        m = re.match(r"^(.*/list/\d+)\.html$", url)
        if m:
            return f"{m.group(1)}/{page}.html"
        return url
