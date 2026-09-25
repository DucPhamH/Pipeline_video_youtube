"""Adapter quanben.io (全本小说网) — HTML list + JSONP full TOC.

Mục lục trang đầu chỉ hiện một phần; full list qua
`/index.php?c=book&a=list.jsonp` (encode `b` kiểu custom base62 của site).
"""
from __future__ import annotations

import json
import random
import re
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVEL = re.compile(r"/n/([a-z0-9]+)/?", re.I)
_CHAPTER = re.compile(r"/n/([a-z0-9]+)/(\d+)\.html", re.I)
_STATIC_CHARS = "PXhw7UT1B0a9kQDKZsjIASmOezxYG4CHo5Jyfg2b8FLpEvRr3WtVnlqMidu6cN"


def _quanben_encode(text: str) -> str:
    """Port JS `base64()` trên trang list — không phải base64 chuẩn."""
    out: list[str] = []
    for ch in text:
        num0 = _STATIC_CHARS.find(ch)
        code = ch if num0 == -1 else _STATIC_CHARS[(num0 + 3) % 62]
        out.append(
            _STATIC_CHARS[random.randint(0, 61)]
            + code
            + _STATIC_CHARS[random.randint(0, 61)]
        )
    return "".join(out)


class QuanbenIoSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="quanben_io",
                name="quanben.io (全本小说网)",
                base_url="https://www.quanben.io",
                content_locale="zh",
                accept_language="zh-CN,zh;q=0.9,zh-TW;q=0.8",
                genre_item_selector=".list2[itemtype], .list2",
                genre_title_selector="h3 a, a[itemprop='url']",
                chapter_list_selector="unused",
                content_selector="#content, .articlebody",
                novel_title_selector="h1, .box h3 span[itemprop='name'], .title",
                strip_lines_containing=["quanben", "全本小说", "上一章", "下一章", "目录"],
                request_delay_sec=0.8,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        # /c/xuanhuan.html -> /c/xuanhuan_2.html
        if page <= 1:
            return url
        if re.search(r"/c/[a-z]+_\d+\.html$", url):
            return re.sub(r"_(\d+)\.html$", f"_{page}.html", url)
        if re.search(r"/c/[a-z]+\.html$", url):
            return re.sub(r"\.html$", f"_{page}.html", url)
        return url

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.quanben.io/n/{m.group(1)}/"

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
        for item in soup.select(self.cfg.genre_item_selector):
            link = item.select_one(self.cfg.genre_title_selector)
            if link is None or not link.get("href"):
                continue
            href = link["href"]
            m = _NOVEL.search(href)
            if not m:
                continue
            title = (link.get_text(strip=True) or "").strip()
            if not title:
                continue
            abs_url = f"https://www.quanben.io/n/{m.group(1)}/"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _NOVEL.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL novel không hợp lệ: {novel_url}")
        pinyin = m.group(1)
        list_url = f"https://www.quanben.io/n/{pinyin}/list.html"
        soup = self._get_soup(list_url)
        html = str(soup)

        chapters_by_idx: dict[int, ChapterRef] = {}

        def _ingest(fragment: str) -> None:
            for a in BeautifulSoup(fragment, "lxml").select("a[href]"):
                href = a.get("href") or ""
                cm = _CHAPTER.search(href)
                if not cm or cm.group(1) != pinyin:
                    continue
                idx = int(cm.group(2))
                title = (a.get_text(strip=True) or f"第{idx}章").strip()
                chapters_by_idx[idx] = ChapterRef(
                    index=idx,
                    title=title,
                    url=f"https://www.quanben.io/n/{pinyin}/{idx}.html",
                )

        _ingest(html)

        book_m = re.search(r"load_more\(['\"]?(\d+)['\"]?\)", html)
        cb_m = re.search(r"var callback=['\"]([^'\"]+)['\"]", html)
        if book_m and cb_m:
            # Trang có `load_more()` nghĩa là CHẮC CHẮN còn chương chưa lấy
            # (trang 1 chỉ là 1 phần TOC) — lỗi JSONP ở đây phải raise, KHÔNG
            # được âm thầm coi phần đã có là "đủ" (bug thật phát hiện lúc
            # review 17/9/2026: 1 mạng chập chờn có thể khiến 1 truyện DÀI,
            # ĐANG RA lẫn vào "ngắn+hoàn thành" vì mục lục bị cắt cụt, sai
            # đúng vào bài học "silent success" ở mục 2 crawl-service.md).
            book_id = book_m.group(1)
            callback = cb_m.group(1)
            payload = self._fetch_jsonp_toc(book_id, callback, list_url)
            _ingest(payload)

        if not chapters_by_idx:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {list_url}")
        return [chapters_by_idx[i] for i in sorted(chapters_by_idx)]

    def _fetch_jsonp_toc(self, book_id: str, callback: str, referer: str) -> str:
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> str:
            headers = {
                "Referer": referer,
                "Accept-Language": self.cfg.accept_language or "zh-CN",
            }
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            resp = self._client.get(
                f"{self.cfg.base_url}/index.php",
                params={
                    "c": "book",
                    "a": "list.jsonp",
                    "callback": callback,
                    "book_id": book_id,
                    "b": _quanben_encode(callback),
                },
                headers=headers,
            )
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} list.jsonp")
            text = resp.text.strip()
            start = text.find("(")
            end = text.rfind(")")
            if start < 0 or end < 0:
                raise ScrapeError(f"[{self.key}] JSONP không hợp lệ: {text[:80]}")
            data = json.loads(text[start + 1 : end])
            content = data.get("content") if isinstance(data, dict) else None
            if not content:
                raise ScrapeError(f"[{self.key}] JSONP thiếu content")
            return content

        try:
            content = _fetch()
        except (httpx.HTTPError, ScrapeError, json.JSONDecodeError) as exc:
            raise ScrapeError(f"[{self.key}] Không tải full TOC book_id={book_id}: {exc}") from exc
        time.sleep(self.cfg.request_delay_sec)
        return content
