"""Adapter Syosetu (なろう) — danh sách qua API công khai `api.syosetu.com`,
mục lục + nội dung chương vẫn trên ncode HTML (API không trả text chương).

Thể loại seed dùng URL API dạng:
  https://api.syosetu.com/novelapi/api/?out=json&lim=20&genre=201&order=hyoka
Phân trang: tham số `st` (1-based). Tài liệu: https://dev.syosetu.com/man/api/
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NCODE_HREF = re.compile(r"https?://ncode\.syosetu\.com/(n[0-9a-z]+)/?$", re.I)
_CHAPTER_HREF = re.compile(r"/(n[0-9a-z]+)/(\d+)/?$", re.I)
_NCODE_FROM_URL = re.compile(r"ncode\.syosetu\.com/(n[0-9a-z]+)", re.I)
_API_HOST = "api.syosetu.com"


class SyosetuComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="syosetu_com",
                name="Syosetu (小説家になろう · API)",
                base_url="https://yomou.syosetu.com",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="a.p-eplist__subtitle",
                content_selector=".p-novel__body",
                novel_title_selector="h1.p-novel__title, .p-novel__title",
                strip_lines_containing=[
                    "syosetu.com",
                    "小説家になろう",
                    "ブックマーク",
                    "応援",
                    "評価する",
                ],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if _API_HOST in url:
            return SyosetuComSource._api_url_for_page(url, page)
        cleaned = re.sub(r"([?&])p=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}p={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER_HREF.search(chapter_url)
        if m:
            return f"https://ncode.syosetu.com/{m.group(1).lower()}/"
        m2 = _NCODE_FROM_URL.search(chapter_url)
        if m2:
            return f"https://ncode.syosetu.com/{m2.group(1).lower()}/"
        return None

    @staticmethod
    def _api_url_for_page(url: str, page: int) -> str:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        lim = 20
        try:
            lim = max(1, min(500, int((qs.get("lim") or ["20"])[0])))
        except ValueError:
            lim = 20
        qs["out"] = ["json"]
        qs["lim"] = [str(lim)]
        qs["st"] = [str(1 + (page - 1) * lim)]
        flat = {k: v[0] for k, v in qs.items()}
        return urlunparse(parsed._replace(query=urlencode(flat)))

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if _API_HOST in genre_list_url:
            return self._list_from_narou_api(genre_list_url, page)
        return self._list_from_html_rank(genre_list_url, page)

    def _list_from_narou_api(self, genre_list_url: str, page: int) -> list[NovelRef]:
        url = self._api_url_for_page(genre_list_url, page)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> list[dict]:
            resp = self._client.get(
                url,
                headers={"Accept": "application/json", "Referer": self.cfg.base_url},
            )
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] Narou API HTTP {resp.status_code}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] Narou API JSON lỗi: {exc}") from exc
            if not isinstance(payload, list) or len(payload) < 1:
                raise ScrapeError(f"[{self.key}] Narou API payload lạ tại {url}")
            return payload

        payload = _fetch()
        import time

        time.sleep(self.cfg.request_delay_sec)

        results: list[NovelRef] = []
        for item in payload[1:]:
            if not isinstance(item, dict):
                continue
            ncode = str(item.get("ncode") or "").strip().lower()
            title = str(item.get("title") or "").strip()
            if not ncode or not title:
                continue
            results.append(
                NovelRef(
                    title=title,
                    url=f"https://ncode.syosetu.com/{ncode}/",
                    latest_chapter_title="",
                )
            )
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Narou API không trả truyện tại {url}")
        return results

    def _list_from_html_rank(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []

        soup = self._get_soup(url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            m = _NCODE_HREF.match(href)
            if not m or "novelview" in href:
                continue
            title = (a.get_text(strip=True) or "").strip()
            if not title or len(title) < 2:
                continue
            abs_url = f"https://ncode.syosetu.com/{m.group(1).lower()}/"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(
                f"[{self.key}] Không parse được truyện từ bảng xếp hạng tại {url}"
            )
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        if "ncode.syosetu.com" not in novel_url:
            raise ScrapeError(
                f"[{self.key}] URL mục lục phải thuộc ncode.syosetu.com: {novel_url}"
            )

        soup = self._get_soup(novel_url)
        ncode_m = _NCODE_FROM_URL.search(novel_url)
        ncode = ncode_m.group(1).lower() if ncode_m else ""

        chapters: list[ChapterRef] = []
        seen_idx: set[int] = set()
        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            m = _CHAPTER_HREF.search(href)
            if not m:
                continue
            if ncode and m.group(1).lower() != ncode:
                continue
            idx = int(m.group(2))
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
            title = (a.get_text(strip=True) or f"第{idx}話").strip()
            abs_url = href if href.startswith("http") else f"https://ncode.syosetu.com{href}"
            chapters.append(ChapterRef(index=idx, title=title, url=abs_url))

        if chapters:
            chapters.sort(key=lambda c: c.index)
            return chapters

        if soup.select_one(self.cfg.content_selector):
            title_node = soup.select_one(self.cfg.novel_title_selector)
            title = title_node.get_text(strip=True) if title_node else "本編"
            return [ChapterRef(index=1, title=title or "本編", url=novel_url.rstrip("/") + "/")]

        raise ScrapeError(
            f"[{self.key}] Không tìm thấy chương tại {novel_url} — site có thể đổi cấu trúc."
        )
