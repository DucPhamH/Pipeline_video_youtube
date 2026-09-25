"""Adapter ttkan.co / tw.ttkan.co (天天看小說) — mirror Đài Loan phổ biến.

- Danh sách: /novel/class/{slug}(?page=N)
- Mục lục: API /api/nq/amp_novel_chapters?language=tw&novel_id=...
- Nội dung: /novel/pagea/{novel_id}_{chapter_id}.html (.content)
"""
from __future__ import annotations

import json
import re
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVEL_ID = re.compile(r"/novel/chapters/([a-z0-9\-]+)", re.I)
_PAGEA = re.compile(r"/novel/pagea/([a-z0-9\-]+)_(\d+)\.html", re.I)


class TtkanCoSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="ttkan_co",
                name="ttkan.co (天天看小說)",
                base_url="https://www.ttkan.co",
                content_locale="zh",
                accept_language="zh-TW,zh;q=0.9,en;q=0.8",
                genre_item_selector=".novel_cell",
                genre_title_selector="h3 a, a[href*='/novel/chapters/']",
                chapter_list_selector="unused",
                content_selector=".content",
                novel_title_selector="h1, .novel_info h1, .chapters_title",
                strip_lines_containing=["ttkan", "天天看", "上一章", "下一章", "加入書架"],
                request_delay_sec=0.8,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        cleaned = re.sub(r"([?&])page=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}page={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _PAGEA.search(chapter_url)
        if not m:
            return None
        return f"https://www.ttkan.co/novel/chapters/{m.group(1)}"

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
        for cell in soup.select(self.cfg.genre_item_selector):
            link = cell.select_one("h3 a[href*='/novel/chapters/'], a[href*='/novel/chapters/']")
            if link is None or not link.get("href"):
                continue
            href = link["href"]
            m = _NOVEL_ID.search(href)
            if not m:
                continue
            title = (link.get_text(strip=True) or link.get("aria-label") or "").strip()
            if not title:
                continue
            abs_url = f"https://www.ttkan.co/novel/chapters/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _NOVEL_ID.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL novel không hợp lệ: {novel_url}")
        novel_id = m.group(1)

        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict:
            headers = {
                "Referer": novel_url if novel_url.startswith("http") else self.cfg.base_url,
                "Accept": "application/json",
                "Accept-Language": self.cfg.accept_language or "zh-TW",
            }
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            resp = self._client.get(
                f"{self.cfg.base_url}/api/nq/amp_novel_chapters",
                params={"language": "tw", "novel_id": novel_id},
                headers=headers,
            )
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi lấy mục lục {novel_id}")
            try:
                return resp.json()
            except json.JSONDecodeError as exc:
                raise ScrapeError(f"[{self.key}] JSON mục lục không hợp lệ") from exc

        try:
            data = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không lấy được mục lục {novel_id}: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)

        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            raise ScrapeError(f"[{self.key}] Mục lục rỗng cho {novel_id}")

        chapters: list[ChapterRef] = []
        for item in items:
            chap_id = item.get("chapter_id")
            name = (item.get("chapter_name") or "").strip() or f"第{chap_id}章"
            if chap_id is None:
                continue
            chapters.append(
                ChapterRef(
                    index=int(chap_id),
                    title=name,
                    url=f"{self.cfg.base_url}/novel/pagea/{novel_id}_{int(chap_id)}.html",
                )
            )
        chapters.sort(key=lambda c: c.index)
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        # page_direct redirect về wa01.com — gọi thẳng pagea cho ổn định
        m = _PAGEA.search(chapter_url)
        if m:
            chapter_url = f"{self.cfg.base_url}/novel/pagea/{m.group(1)}_{m.group(2)}.html"
        elif "page_direct" in chapter_url:
            qs = re.search(r"novel_id=([^&]+).*?page=(\d+)", chapter_url)
            if qs:
                chapter_url = (
                    f"{self.cfg.base_url}/novel/pagea/{qs.group(1)}_{qs.group(2)}.html"
                )

        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy nội dung với selector "
                f"'{self.cfg.content_selector}' tại {chapter_url}"
            )
        for br in node.find_all("br"):
            br.replace_with("\n")
        lines = [
            line.strip()
            for line in node.get_text("\n").splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        text = "\n".join(lines)
        if not text or "暫時無法載入" in text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng/lỗi tại {chapter_url}")
        return text
