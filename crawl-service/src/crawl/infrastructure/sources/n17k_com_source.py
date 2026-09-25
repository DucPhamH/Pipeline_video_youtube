"""Adapter 17k.com — vượt cookie challenge `acw_sc__v2` (reorder+xor) giống
novel-downloader plugins/sites/n17k. Mục lục `/list/{id}.html`, nội dung
`#readArea div.p`. Chương VIP trả lỗi rõ (cần cookie đăng nhập)."""
import base64
import random
import re
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_RE_ARG1 = re.compile(r"var\s+arg1\s*=\s*(['\"])\s*([0-9A-F]+)\s*\1", re.I)
_ORDER_IDX = [
    14, 34, 28, 23, 32, 15, 0, 37, 9, 8, 18, 30, 39, 26, 21, 22, 24, 12, 5, 10,
    38, 17, 19, 7, 13, 20, 31, 25, 1, 29, 6, 3, 16, 4, 2, 27, 33, 36, 11, 35,
]
_SEC = base64.b64decode(b"MAAXYACFYAYGFQFTMANpACeAA3U=")
_BOOK_ID = re.compile(r"/book/(\d+)\.html")
_CHAPTER = re.compile(r"/chapter/(\d+)/(\d+)\.html")


class N17kComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="n17k_com",
                name="17k.com (17K小说网)",
                base_url="https://www.17k.com",
                genre_item_selector="tr.bg0, tr.bg1",
                genre_title_selector="td.td3 a",
                chapter_list_selector="dl.Volume dd a",
                content_selector="#readArea div.p",
                novel_title_selector="h1 a, h1",
                strip_lines_containing=["17K", "本章完", "VIP章节"],
                request_delay_sec=1.5,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )
        self._challenge_cookies: dict[str, str] = {"GUID": self._create_guid()}

    def _get_soup(self, url: str) -> BeautifulSoup:
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> BeautifulSoup:
            headers = {"Referer": self.cfg.base_url}
            cookies = dict(self._challenge_cookies)
            if getattr(self, "_session_cookie_header", ""):
                # user session bổ sung (đăng nhập VIP)
                from platform_.session_cookies import parse_cookie_header

                cookies.update(parse_cookie_header(self._session_cookie_header))
            try:
                resp = self._client.get(url, headers=headers, cookies=cookies)
            except httpx.HTTPError:
                raise
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi tải {url}")
            text = resp.text
            match = _RE_ARG1.search(text)
            if match:
                arg1 = match.group(2).strip()
                reordered = "".join(arg1[i] for i in _ORDER_IDX)
                arg2 = bytes(
                    x ^ y for x, y in zip(bytes.fromhex(reordered), _SEC, strict=False)
                ).hex()
                self._challenge_cookies["acw_sc__v2"] = arg2
                cookies["acw_sc__v2"] = arg2
                resp = self._client.get(url, headers=headers, cookies=cookies)
                if resp.status_code != 200:
                    raise ScrapeError(
                        f"[{self.key}] HTTP {resp.status_code} sau challenge {url}"
                    )
                text = resp.text
                if _RE_ARG1.search(text):
                    raise ScrapeError(f"[{self.key}] Challenge cookie thất bại tại {url}")
            return BeautifulSoup(text, "lxml")

        try:
            soup = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không tải được {url} sau {self.cfg.max_retries + 1} lần: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return soup

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for row in soup.select(self.cfg.genre_item_selector):
            link = row.select_one(self.cfg.genre_title_selector)
            if link is None or not link.get("href"):
                continue
            href = link["href"]
            if not _BOOK_ID.search(href):
                continue
            title = link.get_text(strip=True)
            if not title or title == "xxxx":
                continue
            if href.startswith("http"):
                normalized = href
            elif href.startswith("//"):
                normalized = "https:" + href
            else:
                normalized = href
            abs_url = self._abs_url(normalized)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _BOOK_ID.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL truyện không hợp lệ: {novel_url}")
        catalog_url = f"https://www.17k.com/list/{m.group(1)}.html"
        soup = self._get_soup(catalog_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select(self.cfg.chapter_list_selector):
            href = a.get("href") or ""
            if not _CHAPTER.search(href):
                continue
            span = a.select_one("span")
            title = (span.get_text(strip=True) if span else a.get_text(strip=True))
            if not title:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {catalog_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url)
        html = str(soup)
        # Sửa 17/9/2026: điều kiện cũ `and soup.select_one(...) is None` khiến
        # 1 chương VIP có preview ngắn TRƯỚC banner "VIP章节" (selector VẪN
        # match, chỉ thiếu phần sau khoá) lọt qua — banner đó bị strip_lines
        # âm thầm xoá như noise, trả về đúng phần preview cụt làm nội dung
        # "thành công" (bug "silent success" kinh điển, mục 2 crawl-service.md).
        # "VIP章节" là cụm đủ đặc trưng để tin cậy một mình, không cần thêm
        # điều kiện selector rỗng.
        if "VIP章节" in html:
            raise ScrapeError(f"[{self.key}] Chương VIP — cần cookie đăng nhập: {chapter_url}")
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(f"[{self.key}] Không tìm thấy nội dung tại {chapter_url}")
        for br in node.find_all("br"):
            br.replace_with("\n")
        lines = [
            line.strip()
            for line in node.get_text("\n").splitlines()
            if line.strip() and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        text = "\n".join(lines)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng tại {chapter_url}")
        return text

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        return super()._abs_url(href)

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.17k.com/book/{m.group(1)}.html"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """.../all/book/2_21_0_0_0_0_0_0_1.html -> đổi số trang cuối."""
        if page <= 1:
            return url
        if re.search(r"_\d+\.html$", url):
            return re.sub(r"_(\d+)\.html$", f"_{page}.html", url)
        return url

    @staticmethod
    def _create_guid() -> str:
        template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
        return "".join(
            format(random.randint(0, 15), "x")
            if ch == "x"
            else format((random.randint(0, 15) & 0x3) | 0x8, "x")
            if ch == "y"
            else ch
            for ch in template
        )
