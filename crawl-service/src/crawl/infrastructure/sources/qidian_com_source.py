"""Adapter qidian.com (起点) — tầng 2 Playwright (anti-bot JS).
Free chapter: parse SSR chapterInfo. VIP encrypted: Node decrypt + cookie ywguid.
Không bypass thanh toán — thiếu cookie/quyền → ScrapeError.
"""
from __future__ import annotations

import json
import re
from html import unescape

from bs4 import BeautifulSoup

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_browser_source import BaseBrowserSource
from crawl.infrastructure.sources.base_html_source import SourceConfig
from crawl.infrastructure.sources.content_pipeline import qidian_decrypt_vip
from crawl.infrastructure.sources.tls_fetch import looks_like_cloudflare_challenge
from platform_.session_cookies import load_cookie_header, parse_cookie_header

_BOOK = re.compile(r"/book/(\d+)")
_CHAPTER = re.compile(r"/chapter/(\d+)/(\d+)")


class QidianComSource(BaseBrowserSource):
    browser_wait_selector = "a[href*='/book/'], #viewer, .main-text-wrap"
    prefer_tls_first = False  # Qidian anti-bot JS — browser trước

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="qidian_com",
                name="qidian.com (起点中文网)",
                base_url="https://www.qidian.com",
                genre_item_selector=".book-img-text li, .all-book-list li",
                genre_title_selector='a[href*="/book/"]',
                chapter_list_selector='a[href*="/chapter/"]',
                content_selector=".main-text-wrap, #viewer",
                novel_title_selector="h1, .book-info h1",
                strip_lines_containing=["起点", "qidian", "本章字数"],
                request_delay_sec=2.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
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
        html = str(soup)
        if len(html) < 5000 and ("seqid" in html or "var buid" in html):
            raise ScrapeError(
                f"[{self.key}] Anti-bot Qidian chưa qua — dán cookie session "
                f"từ trình duyệt đã đăng nhập (ywguid...), rồi thử lại: {url}"
            )
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/book/"]'):
            href = a.get("href") or ""
            if not _BOOK.search(href):
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 2:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/chapter/"]'):
            href = a.get("href") or ""
            if not _CHAPTER.search(href):
                continue
            title = a.get_text(strip=True)
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
            raise ScrapeError(
                f"[{self.key}] Không thấy chương (cần cookie / trang catalogue): {novel_url}"
            )
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        html = self._fetch_html(chapter_url, check_content_blockers=True)
        if looks_like_cloudflare_challenge(html):
            raise ScrapeError(f"[{self.key}] Cloudflare tại {chapter_url}")

        info = self._extract_chapter_info(html)
        if info:
            return self._content_from_ssr(info, chapter_url)

        # fallback DOM
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(f"[{self.key}] Không parse được nội dung tại {chapter_url}")
        text = self._paras_from_html(str(node))
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng tại {chapter_url}")
        return text

    def _content_from_ssr(self, info: dict, chapter_url: str) -> str:
        vip_status = int(info.get("vipStatus") or 0)
        is_buy = int(info.get("isBuy") or 0)
        if vip_status == 1 and is_buy == 0:
            raise ScrapeError(
                f"[{self.key}] VIP chưa mua — dán cookie account đã mua chương: {chapter_url}"
            )

        raw_html = info.get("content") or ""
        cid = str(info.get("chapterId") or "")
        fkp = info.get("fkp") or ""
        fens = int(info.get("fencionStatus") or info.get("fensStatus") or 0)

        need_decrypt = vip_status == 1 and fens != 0
        if need_decrypt:
            cookies = parse_cookie_header(load_cookie_header(self.key))
            fuid = cookies.get("ywguid") or cookies.get("ywGuid") or ""
            if not fuid:
                raise ScrapeError(
                    f"[{self.key}] VIP decrypt cần cookie ywguid — dán session Qidian"
                )
            raw_html = qidian_decrypt_vip(raw_html, cid, fkp, fuid)

        text = self._paras_from_html(raw_html)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung SSR rỗng tại {chapter_url}")
        return text

    @staticmethod
    def _extract_chapter_info(html: str) -> dict | None:
        m = re.search(
            r'"chapterInfo"\s*:\s*(\{.+?\})\s*,\s*"chapterNavInfo"',
            html,
            re.DOTALL,
        )
        if not m:
            return None
        raw = m.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                # đôi khi escape trong script string
                return json.loads(raw.replace("\n", "\\n"))
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _paras_from_html(raw_html: str) -> str:
        if not raw_html:
            return ""
        if "<p>" in raw_html or "<P>" in raw_html:
            parts = re.split(r"</?p[^>]*>", raw_html, flags=re.I)
            paras = [unescape(BeautifulSoup(p, "lxml").get_text()).strip() for p in parts]
            lines = [p for p in paras if p]
            return "\n".join(lines)
        soup = BeautifulSoup(raw_html, "lxml")
        return "\n".join(
            line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
        )

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        return super()._abs_url(href)

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.qidian.com/book/{m.group(1)}/"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if "page=" in url:
            return re.sub(r"page=\d+", f"page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
