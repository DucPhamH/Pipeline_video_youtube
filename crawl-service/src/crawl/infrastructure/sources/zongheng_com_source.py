"""Adapter RIÊNG cho zongheng.com (纵横中文网) — kế thừa `BaseHtmlSource`
nhưng KHÔNG dùng CSS-selector-trên-HTML-liệt-kê như đa số site khác, vì
site này là SPA (Nuxt/Vue) — HTML thô trả về từ httpx cho các trang liệt kê
thể loại (`/categories?...`, `/books?...`) hầu như rỗng dữ liệu thật (chỉ
có khung SPA, dữ liệu load qua XHR phía client). Đã dò mạng thật 17/9/2026
bằng DevTools (Performance API) tìm ra đúng API JSON công khai (KHÔNG cần
cookie/token) mà chính trang này gọi:

  - Danh sách thể loại: POST bookapi.zongheng.com/api/category/categoryPage
    {cateFineId} -> nhiều mảng truyện đã duyệt (xinShuList/jingPinList/...).
    8 cateFineId thật lấy từ field `categoryInfo.cateFineList` của chính
    response này (không tự bịa): 8101 玄幻奇幻, 8102 武侠仙侠, 8103 都市,
    8104 历史, 8105 科幻, 8106 奇闻异事, 8109 现实题材, -100 其他分类.
  - Mục lục chương: POST bookapi.zongheng.com/api/chapter/getChapterList
    {bookId} -> TOÀN BỘ chương (đã verify 1 truyện 3553 chương, không cần
    phân trang) kèm `price` (0 = free) và `chapterId`.
  - Trang đọc chương: https://read.zongheng.com/chapter/{bookId}/{chapterId}.html
    SSR HTML thường (không qua SPA), selector `div.content`. Đã verify:
    marker khoá thật của site là thuộc tính `data-prescription="1"` (chương
    mới đăng, ĐỘC QUYỀN app — nội dung bị cắt ngắn + chèn dòng rác kiểu
    "下下下/载载载/纵纵纵/横横横/小小小/说说说/看全文" ghép lại thành
    "下载纵横小说看全文" + khối quảng cáo tải app cuối bài), khác hẳn
    `price>0` (chương "trả phí" trong metadata NHƯNG vẫn đọc được đầy đủ,
    miễn phí, qua httpx thường — đã verify chương giá 4 đọc được trọn vẹn).
    KHÔNG gặp Cloudflare/captcha ở bất kỳ bước nào qua nhiều lần thử thật.

Vì luồng lấy dữ liệu hoàn toàn khác (JSON API, không phải CSS selector trên
HTML liệt kê), các method `list_genre_novels_page`/`list_chapters`/
`fetch_novel_title`/`fetch_chapter_content` đều override thẳng ở đây."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import check_fetched_html

_BOOK_LIST_KEYS = (
    "lunBoList",
    "xinShuList",
    "zhuanTiList",
    "reXiaoList",
    "jingPinList",
    "jingDianList",
    "shiDuList",
    "serialRecommendList",
    "qiangTuiList",
    "newBookRankList",
    "clickBookRankList",
    "recommendRankList",
    "signNewBookList",
)
_DETAIL_BOOKID_RE = re.compile(r"/detail/(\d+)")
_CHAPTER_URL_RE = re.compile(r"/chapter/(\d+)/(\d+)\.html")
# Dòng rác chèn vào nội dung chương độc quyền app, kiểu "下下下"/"载载载"
# (1 ký tự lặp lại nguyên dòng) — phát hiện theo QUY LUẬT, không hardcode
# từng chuỗi cụ thể (site có thể đổi câu quảng cáo bất kỳ lúc nào).
_REPEATED_CHAR_LINE_RE = re.compile(r"^(.)\1+$")


class ZonghengComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="zongheng_com",
                name="zongheng.com (纵横中文网)",
                base_url="https://www.zongheng.com",
                encoding="utf-8",
                content_selector="div.content",
                request_delay_sec=1.5,
            )
        )

    def _post_json(self, url: str, data: dict) -> dict:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict:
            resp = self._client.post(
                url,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": self.cfg.base_url,
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi POST {url}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] JSON không hợp lệ từ {url}: {exc}") from exc
            if payload.get("code") != 0:
                raise ScrapeError(
                    f"[{self.key}] API {url} trả code={payload.get('code')} "
                    f"message={payload.get('message')}"
                )
            return payload.get("result") or {}

        result = _fetch()
        import time

        time.sleep(self.cfg.request_delay_sec)
        return result

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """API `categoryPage` trả 1 snapshot đã duyệt (nhiều mảng nhỏ ghép
        lại ~90-99 truyện/thể loại), KHÔNG hỗ trợ phân trang thật (đã thử
        `pageNum` trên endpoint tương tự `updatelist`, kết quả không đổi)
        -> trang > 1 luôn trả rỗng, giống quy ước site không hỗ trợ dò thêm."""
        if page != 1:
            return []

        qs = parse_qs(urlparse(genre_list_url).query)
        cate_fine_id = (qs.get("cateFineId") or [None])[0]
        if not cate_fine_id:
            raise ScrapeError(
                f"[{self.key}] URL thể loại thiếu tham số cateFineId: {genre_list_url}"
            )

        result = self._post_json(
            "http://bookapi.zongheng.com/api/category/categoryPage",
            {"cateFineId": cate_fine_id},
        )

        seen: set[int] = set()
        novels: list[NovelRef] = []
        for key in _BOOK_LIST_KEYS:
            block = result.get(key)
            items = block.get("list") if isinstance(block, dict) else block
            if not items:
                continue
            for item in items:
                book_id = item.get("bookId")
                title = item.get("bookName") or item.get("title")
                if not book_id or not title or book_id in seen:
                    continue
                seen.add(book_id)
                novels.append(
                    NovelRef(
                        title=title,
                        url=f"{self.cfg.base_url}/detail/{book_id}",
                        latest_chapter_title="",
                    )
                )

        if not novels:
            raise ScrapeError(
                f"[{self.key}] API categoryPage không trả truyện nào cho "
                f"cateFineId={cate_fine_id} — site có thể đổi API."
            )
        return novels

    def fetch_novel_title(self, novel_url: str) -> str | None:
        soup = self._get_soup(novel_url)
        title_tag = soup.select_one("title")
        if title_tag is None:
            return None
        raw = title_tag.get_text(strip=True)
        # <title>鸿蒙霸体诀(鱼初见)最新章节全本在线阅读-纵横中文网官方正版</title>
        # -> lấy phần trước dấu "(" đầu tiên là tên truyện.
        name = raw.split("(")[0].strip()
        return name or None

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _DETAIL_BOOKID_RE.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] Không lấy được bookId từ {novel_url}")
        book_id = m.group(1)

        result = self._post_json(
            "http://bookapi.zongheng.com/api/chapter/getChapterList",
            {"bookId": book_id},
        )
        tomes = result.get("chapterList") or []
        chapters: list[ChapterRef] = []
        for tome in tomes:
            for c in tome.get("chapterViewList") or []:
                chapter_id = c.get("chapterId")
                name = c.get("chapterName")
                if not chapter_id or not name:
                    continue
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=name,
                        url=f"https://read.zongheng.com/chapter/{book_id}/{chapter_id}.html",
                    )
                )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không thấy chương nào tại {novel_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy nội dung với selector "
                f"'{self.cfg.content_selector}' tại {chapter_url}"
            )
        # Marker khoá THẬT của site (đã verify HTML thật 17/9/2026): chương
        # mới đăng độc quyền app có data-prescription="1" và bị cắt ngắn.
        if (node.get("data-prescription") or "").strip() == "1":
            raise ScrapeError(
                f"[{self.key}] Chương độc quyền app (data-prescription=1, nội dung bị "
                f"cắt ngắn kèm quảng cáo tải app) tại {chapter_url}"
            )
        for br in node.find_all("br"):
            br.replace_with("\n")
        lines = []
        for line in node.get_text("\n").splitlines():
            line = line.strip()
            if not line:
                continue
            # Lọc dòng rác kiểu "下下下"/"载载载" (1 ký tự lặp lại nguyên
            # dòng) chèn vào chương độc quyền app — phát hiện theo QUY LUẬT
            # cấu trúc, không hardcode câu quảng cáo cụ thể.
            if _REPEATED_CHAR_LINE_RE.match(line):
                continue
            lines.append(line)
        text = "\n".join(lines)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng sau khi lọc tại {chapter_url}")
        return text

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER_URL_RE.search(chapter_url)
        if not m:
            return None
        return f"https://www.zongheng.com/detail/{m.group(1)}"
