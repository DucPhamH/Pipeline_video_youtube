"""Adapter munpia.com (문피아) — web novel Hàn Quốc.

Đã soi mạng thật (17/9/2026):
- Trang chủ/PC (`www.munpia.com`) là SPA React thuần, mọi trang (kể cả
  `/novel/detail/{id}`) chỉ trả về shell rỗng khi fetch bằng httpx thường.
  RIÊNG trang danh sách thể loại `/novel-free-list?...` LẠI server-render
  HTML đầy đủ (86KB, có `div.novel-list` từng dòng truyện) — dùng được qua
  httpx bình thường, không cần browser.
- Trang đọc chương PC (`/novel/viewer/{novelId}/{entryId}`) fetch nội dung
  qua `POST /api/v1/pc/novel-detail/{novelId}/entries/{entryId}/content`
  với payload ký ECDH (`publicKey/timestamp/salt/signature` — bắt được qua
  network thật của trình duyệt) RỒI vẽ chữ lên `<canvas>` (xác nhận qua
  DOM: `div[class*="_contentArea_"]` chỉ có 2 con `[CANVAS, DIV]`, text
  rỗng, ở CẢ 2 chế độ xem trang/cuộn) — không thể trích xuất qua selector
  dù dùng browser thật, cần OCR từng trang mới đọc được chữ -> KHÔNG dùng
  đường PC cho nội dung chương.
- Bản mobile web (`m.munpia.com`) đơn giản hơn hẳn: chương render thẳng ra
  DOM (`div.content article`, không có canvas) VÀ nội dung lấy qua
  `GET /api/v1/mobile/novel-detail/{novelId}/entries/{entryId}` — JSON
  thuần `result.entry.content`, không cần ký gì cả (khác hẳn API PC).
  => Adapter này dùng httpx thẳng tới `m.munpia.com` cho mục lục + nội
  dung chương (giống cách `novelpia_com_source.py` dùng API JSON), và
  `www.munpia.com/novel-free-list` (server-rendered) cho danh sách thể
  loại.
- Chương khoá trả JSON lỗi rõ ràng: `{"code":"A002_21014","message":"유료
  작품은 문피아 앱에서 열람 가능합니다."}` (HTTP 400) — nghĩa là "chương trả
  phí chỉ đọc được trong app Munpia", KHÔNG có cách nào mở khoá qua web dù
  đăng nhập -> site được xếp `access_kind` mặc định "free" (không cần
  site_access.py), vì phần đọc được (chương free) không cần cookie.
"""
from __future__ import annotations

import re
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_MOBILE_BASE = "https://m.munpia.com"
_DETAIL_URL_RE = re.compile(r"/novel/detail/(\d+)")
_VIEWER_URL_RE = re.compile(r"/novel/viewer/(\d+)/(\d+)")


class MunpiaComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="munpia_com",
                name="Munpia (문피아)",
                base_url="https://www.munpia.com",
                content_locale="ko",
                accept_language="ko,en;q=0.8",
                # danh sách thể loại parse riêng (list_genre_novels_page override) vì
                # tiêu đề & href nằm ở 2 thẻ khác nhau (p.novel-list__title bên trong
                # a.novel-list__body) — selector dưới đây chỉ để tài liệu hoá, không
                # dùng qua code dùng chung của BaseHtmlSource.
                genre_item_selector="a.novel-list__body",
                genre_title_selector="p.novel-list__title",
                chapter_list_selector="unused",
                content_selector="unused",
                novel_title_selector="unused",
                request_delay_sec=0.4,
                novel_url_from_chapter=self._derive_novel_url,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _VIEWER_URL_RE.search(chapter_url)
        if not m:
            return None
        return f"https://www.munpia.com/novel/detail/{m.group(1)}"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """`/novel-free-list?...&page=0` (trang 1) -> page=N-1 (site 0-based),
        verify bằng HTML thật (17/9/2026: page=0 và page=1 trả 2 trang khác nhau)."""
        return re.sub(r"page=\d+", f"page={page - 1}", url)

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        else:
            url = self._paginate_list_url(genre_list_url, page)
        soup = self._get_soup(url)
        # CHÚ Ý: chỉ có DUY NHẤT 1 `div.novel-list` bọc NGOÀI toàn bộ danh
        # sách — mỗi truyện là 1 `a.novel-list__body` NẰM NGANG HÀNG bên
        # trong (không phải mỗi truyện 1 div riêng) — verify bằng HTML thật
        # (17/9/2026: đếm `class="novel-list"` trong response chỉ ra đúng 1
        # lần dù trang có 10 truyện).
        items = soup.select("a.novel-list__body")
        if not items:
            if page == 1:
                raise ScrapeError(
                    f"[{self.key}] Không tìm thấy truyện nào với selector "
                    f"'a.novel-list__body' tại {url} — site có thể đổi cấu trúc."
                )
            return []

        results: list[NovelRef] = []
        for a in items:
            title_tag = a.select_one("p.novel-list__title")
            if title_tag is None or not a.get("href"):
                continue
            results.append(
                NovelRef(
                    title=title_tag.get_text(strip=True),
                    url=self._abs_url(a["href"]),
                    latest_chapter_title="",
                )
            )
        return results

    # ------------------------------------------------------------------
    # Mục lục + nội dung chương: JSON thuần từ m.munpia.com (không cần ký
    # ECDH như đường PC — verify bằng network thật 17/9/2026).
    # ------------------------------------------------------------------
    def _request_json(self, url: str, *, params: dict | None = None) -> dict:
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict:
            headers = {
                "Referer": _MOBILE_BASE + "/",
                "Accept": "application/json",
                "Accept-Language": self.cfg.accept_language or "ko,en;q=0.8",
            }
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            resp = self._client.get(url, headers=headers, params=params)
            try:
                data = resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] Response không phải JSON tại {url}") from exc
            if resp.status_code != 200:
                code = data.get("code") if isinstance(data, dict) else None
                msg = data.get("message") if isinstance(data, dict) else None
                if code == "A002_21014" or (msg and "유료" in msg):
                    raise ScrapeError(
                        f"[{self.key}] Chương trả phí — chỉ đọc được trong app Munpia "
                        f"(code={code}) tại {url}"
                    )
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} ({code}: {msg}) tại {url}")
            return data

        try:
            data = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không gọi được {url} sau {self.cfg.max_retries + 1} lần: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return data

    @staticmethod
    def _novel_id_from_url(novel_url: str) -> str:
        m = _DETAIL_URL_RE.search(novel_url)
        if not m:
            raise ScrapeError(f"URL novel không hợp lệ (thiếu /novel/detail/{{id}}): {novel_url}")
        return m.group(1)

    def fetch_novel_title(self, novel_url: str) -> str | None:
        novel_id = self._novel_id_from_url(novel_url)
        data = self._request_json(f"{_MOBILE_BASE}/api/v1/mobile/novel-detail/{novel_id}")
        title = (((data.get("result") or {}).get("novelInfo") or {}).get("title") or "").strip()
        return title or None

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        novel_id = self._novel_id_from_url(novel_url)
        chapters: list[ChapterRef] = []
        page = 1
        size = 200
        total = None
        while True:
            data = self._request_json(
                f"{_MOBILE_BASE}/api/v1/mobile/novel-detail/{novel_id}/chapters",
                params={"page": page, "size": size},
            )
            result = data.get("result") or {}
            total = result.get("total") or 0
            items = result.get("list") or []
            if not items:
                break
            for it in items:
                entry_id = it.get("id")
                if not entry_id:
                    continue
                title = (it.get("title") or "").strip() or f"Chapter {len(chapters) + 1}"
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=title,
                        url=f"https://www.munpia.com/novel/viewer/{novel_id}/{entry_id}",
                    )
                )
            if len(chapters) >= total:
                break
            page += 1

        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương nào cho novel {novel_id}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        m = _VIEWER_URL_RE.search(chapter_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL chương không hợp lệ: {chapter_url}")
        novel_id, entry_id = m.group(1), m.group(2)
        data = self._request_json(
            f"{_MOBILE_BASE}/api/v1/mobile/novel-detail/{novel_id}/entries/{entry_id}"
        )
        content = (((data.get("result") or {}).get("entry") or {}).get("content") or "").strip()
        if not content:
            raise ScrapeError(
                f"[{self.key}] Nội dung rỗng (entry {entry_id}) — có thể là chương trả phí."
            )
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        return "\n".join(lines)
