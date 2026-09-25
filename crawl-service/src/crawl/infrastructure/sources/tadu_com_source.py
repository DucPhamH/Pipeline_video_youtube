"""Adapter tadu.com (塔读文学) — kế thừa BaseHtmlSource (tầng 1, httpx thuần —
đã verify KHÔNG có Cloudflare/WAF chặn trang HTML lẫn API JSON, 17/9/2026).

Đặc điểm RIÊNG của site: trang đọc chương (`/book/{bookId}/{chapterId}/`)
KHÔNG chứa sẵn nội dung trong HTML — chỉ có 1 input ẩn
`#bookPartResourceUrl` trỏ tới API JSON thật
`/getPartContentByCodeTable/{bookId}/{partId}` (partId = số thứ tự chương
trong mục lục, KHÁC với chapterId dùng trên URL trang đọc) trả về
`{"status":200,"data":{"content":"<p>...</p>..."}}`. Vì vậy override
`fetch_chapter_content` làm 2 bước: tải trang chương lấy resource URL, rồi
gọi thẳng API lấy JSON.

Đã thử tìm chương khoá VIP thật (site có tag lọc "VIP" ở /store và mục
"đầu tư ngân phiếu"/单章订阅 trên trang đọc) nhưng test thực tế trên 2
truyện khác nhau (kể cả truyện gắn tag "VIP", tới tận chương cuối) đều trả
đủ nội dung cho request ẩn danh — web tadu.com có vẻ đọc free hoàn toàn
(kiếm tiền qua quảng cáo/app), khác giả định ban đầu. Vẫn giữ
`check_fetched_html` (CF + marker VIP tiếng Trung dùng chung) làm lớp
phòng thủ cho trường hợp truyện khác thực sự khoá."""
import re

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import check_fetched_html

# Watermark quảng cáo bị chèn NGẪU NHIÊN mỗi lần gọi API — đã verify thật
# NHIỀU lần liên tiếp ra nhiều biến thể khác nhau (17/9/2026): "塔读小~。>
# 说—*.—免费*无广>告无*..." / "塔^读小说,欢迎下载-^" / "首发&：塔>-读小说" /
# thậm chí "塔读@" (gần như sạch). Điểm chung DUY NHẤT, ổn định: luôn có 2
# chữ "塔" và "读" (thương hiệu "塔读小说") đứng GẦN nhau (rác chèn xen kẽ
# nhưng khoảng cách nhỏ) — dùng regex fuzzy làm tín hiệu CHÍNH; cờ ký tự
# rác hiếm gặp trong văn xuôi bình thường (~^&@*<>-) làm lưới phòng thủ
# PHỤ cho dòng rác không chứa "塔读" (vd domain/URL rác khác).
_AD_BRAND_RE = re.compile(r"塔.{0,3}读")
_AD_JUNK_CHARS_RE = re.compile(r"[~^&@*<>\-]")

_BOOK_CHAPTER = re.compile(r"/book/(\d+)/(\d+)/?")


class TaduComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="tadu_com",
                name="tadu.com (塔读文学)",
                base_url="https://www.tadu.com",
                genre_item_selector="ul.bookList li",
                genre_title_selector="a.bookNm",
                genre_latest_chapter_selector="a.updateNew",
                chapter_list_selector="div.lfT a",
                novel_title_selector="a.bkNm",
                strip_lines_containing=["塔读小说APP", "塔读小说网", "塔读文学", "塔读-小说APP"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        """.../book/1034377/102154602/ -> .../book/1034377/ — quy luật ổn
        định, đã verify bằng HTML thật (17/9/2026)."""
        m = _BOOK_CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.tadu.com/book/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """Trang thể loại dạng .../store/{genreId}-a-0-15-a-20-p-{page}-{scope}
        — đã verify page=1 vs page=2 trả 2 danh sách truyện khác nhau thật
        (17/9/2026)."""
        if page <= 1:
            return url
        return re.sub(r"-p-\d+-", f"-p-{page}-", url)

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        resource_tag = soup.select_one("#bookPartResourceUrl")
        resource_href = (resource_tag.get("value") if resource_tag else "") or ""
        if not resource_href:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy resource URL nội dung (#bookPartResourceUrl) "
                f"tại {chapter_url} — site có thể đổi cấu trúc."
            )
        resource_url = self._abs_url(resource_href)
        data = self._get_content_json(resource_url, referer=chapter_url)
        if not isinstance(data, dict) or data.get("status") != 200:
            status = data.get("status") if isinstance(data, dict) else None
            raise ScrapeError(
                f"[{self.key}] API nội dung trả lỗi (status={status}) tại {resource_url}"
            )
        content_html = ((data.get("data") or {}).get("content") or "").strip()
        if not content_html:
            raise ScrapeError(
                f"[{self.key}] Nội dung rỗng tại {chapter_url} (có thể khoá VIP/cần đăng nhập)"
            )
        check_fetched_html(content_html, source_key=self.key, url=resource_url)

        text = self._paras_from_html(content_html)
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
            and not _AD_BRAND_RE.search(line)
            and len(_AD_JUNK_CHARS_RE.findall(line)) < 2
        ]
        if not lines:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng sau khi lọc tại {chapter_url}")
        return "\n".join(lines)

    def _get_content_json(self, url: str, *, referer: str) -> dict:
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict:
            headers = {"Referer": referer}
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            try:
                resp = self._client.get(url, headers=headers)
            except httpx.HTTPError:
                raise
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} tại {url}")
            try:
                return resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] Không parse được JSON tại {url}: {exc}") from exc

        try:
            return _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không tải được nội dung {url} sau {self.cfg.max_retries + 1} lần thử: {exc}"
            ) from exc

    @staticmethod
    def _paras_from_html(raw_html: str) -> str:
        soup = BeautifulSoup(raw_html, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        return soup.get_text("\n")
