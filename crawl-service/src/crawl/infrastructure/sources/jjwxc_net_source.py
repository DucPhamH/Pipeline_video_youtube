"""Adapter RIÊNG cho jjwxc.net (晋江文学城) — kế thừa `BaseHtmlSource`.

Danh sách thể loại: HTML `bookbase.php?lx=…` (100 truyện/trang).
Mục lục + nội dung chương: ưu tiên Android API công khai
`https://app-cdn.jjwxc.net/androidapi/chapterList|chapterContent`
(đã verify 22/9/2026); fallback HTML nếu API lỗi.
"""
import html as html_lib
import re
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVELID_RE = re.compile(r"novelid=(\d+)", re.I)
_CHAPTERID_RE = re.compile(r"chapterid=(\d+)", re.I)
_API_BASE = "https://app-cdn.jjwxc.net/androidapi"


class JjwxcNetSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="jjwxc_net",
                name="jjwxc.net (晋江文学城 · API chương)",
                base_url="https://www.jjwxc.net",
                encoding="gb18030",
                genre_item_selector="div.box2_content li",
                genre_title_selector="p a[title]",
                chapter_list_selector='tr[itemprop="chapter"] a[itemprop="url"]',
                content_selector="#paragraph_comment_content",
                novel_title_selector='h1[itemprop="name"]',
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
                content_locale="zh",
                request_delay_sec=1.0,
            )
        )

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []

        soup = self._get_soup(url)
        items = soup.select(self.cfg.genre_item_selector)
        if not items:
            if page == 1:
                raise ScrapeError(
                    f"[{self.key}] Không tìm thấy truyện nào với selector "
                    f"'{self.cfg.genre_item_selector}' tại {url}"
                )
            return []

        results: list[NovelRef] = []
        for item in items:
            title_tag = item.select_one(self.cfg.genre_title_selector)
            if title_tag is None or not title_tag.get("href"):
                continue
            raw_title = (title_tag.get("title") or title_tag.get_text(strip=True)).strip()
            title = raw_title.strip("《》").strip()
            if not title:
                continue
            results.append(
                NovelRef(
                    title=title,
                    url=self._abs_url(title_tag["href"]),
                    latest_chapter_title="",
                )
            )
        return results

    def _novel_id_from_url(self, url: str) -> str | None:
        m = _NOVELID_RE.search(url)
        return m.group(1) if m else None

    def _api_get_json(self, path: str, params: dict) -> dict | list:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict | list:
            resp = self._client.get(
                f"{_API_BASE}/{path}",
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0 JJWXC-Android",
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": self.cfg.base_url,
                },
            )
            if resp.status_code != 200:
                raise ScrapeError(
                    f"[{self.key}] Android API HTTP {resp.status_code} {path}"
                )
            try:
                return resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] Android API JSON lỗi: {exc}") from exc

        payload = _fetch()
        time.sleep(self.cfg.request_delay_sec)
        return payload

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        novel_id = self._novel_id_from_url(novel_url)
        if novel_id:
            try:
                return self._list_chapters_api(novel_id)
            except ScrapeError:
                pass
        return super().list_chapters(novel_url)

    def _list_chapters_api(self, novel_id: str) -> list[ChapterRef]:
        payload = self._api_get_json("chapterList", {"novelId": novel_id})
        if not isinstance(payload, dict):
            raise ScrapeError(f"[{self.key}] chapterList payload lạ")
        rows = payload.get("chapterlist") or payload.get("chapterList") or []
        if not rows:
            raise ScrapeError(f"[{self.key}] chapterList rỗng novelId={novel_id}")
        chapters: list[ChapterRef] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("chapterid") or row.get("chapterId") or "").strip()
            if not cid:
                continue
            if str(row.get("chaptertype") or "0") == "1":
                continue
            title = str(row.get("chaptername") or row.get("chapterName") or f"第{cid}章")
            if str(row.get("islock") or "0") not in ("0", "false", ""):
                title = f"[VIP] {title}"
            chapters.append(
                ChapterRef(
                    index=len(chapters) + 1,
                    title=title.strip(),
                    url=(
                        f"https://www.jjwxc.net/onebook.php?"
                        f"novelid={novel_id}&chapterid={cid}"
                    ),
                )
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không parse được chương API novelId={novel_id}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        novel_id = self._novel_id_from_url(chapter_url)
        ch_m = _CHAPTERID_RE.search(chapter_url)
        if novel_id and ch_m:
            try:
                text = self._fetch_chapter_api(novel_id, ch_m.group(1))
                if text and len(text) >= 40:
                    return text
            except ScrapeError:
                pass
        return super().fetch_chapter_content(chapter_url)

    def _fetch_chapter_api(self, novel_id: str, chapter_id: str) -> str:
        payload = self._api_get_json(
            "chapterContent", {"novelId": novel_id, "chapterId": chapter_id}
        )
        if not isinstance(payload, dict):
            raise ScrapeError(f"[{self.key}] chapterContent payload lạ")
        if payload.get("code") and str(payload.get("code")) not in ("0", "200"):
            raise ScrapeError(
                f"[{self.key}] chapterContent code={payload.get('code')} "
                f"{payload.get('message')}"
            )
        raw = payload.get("content") or ""
        if not raw:
            raise ScrapeError(
                f"[{self.key}] Chương trống / VIP (API) novelId={novel_id} chapterId={chapter_id}"
            )
        unescaped = html_lib.unescape(str(raw))
        soup = BeautifulSoup(unescaped, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text("\n")
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip()
            and not any(bad in ln for bad in self.cfg.strip_lines_containing)
        ]
        body = "\n".join(lines)
        if len(body) < 40:
            raise ScrapeError(
                f"[{self.key}] Nội dung API quá ngắn (có thể VIP) "
                f"novelId={novel_id} chapterId={chapter_id}"
            )
        return body

    def _extract_raw_page_text(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            title_tag = soup.select_one("title")
            title_text = title_tag.get_text(strip=True) if title_tag else ""
            if "登入" in title_text or "登录" in title_text or "login" in title_text.lower():
                raise ScrapeError(
                    f"[{self.key}] Chương VIP cần đăng nhập/đã mua (site redirect sang "
                    f"trang đăng nhập '{title_text}') tại {chapter_url}"
                )
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy nội dung với selector "
                f"'{self.cfg.content_selector}' tại {chapter_url}"
            )
        for br in node.find_all("br"):
            br.replace_with("\n")
        return node.get_text("\n")

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _NOVELID_RE.search(chapter_url)
        if not m:
            return None
        return f"https://www.jjwxc.net/onebook.php?novelid={m.group(1)}"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if "page=" in url:
            return re.sub(r"page=\d+", f"page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
