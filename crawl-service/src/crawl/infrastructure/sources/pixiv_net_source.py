"""Adapter pixiv.net novels — API JSON công khai `/ajax/...` (SPA, không
parse HTML list).

- Danh sách: GET /ajax/search/novels/{word}?word=...&p=N&mode=safe&s_mode=s_tag
- Series: GET /ajax/novel/series/{id} + /ajax/novel/series_content/{id}
- Chương đơn / nội dung: GET /ajax/novel/{id} → body.content (plaintext)
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_SERIES_URL = re.compile(r"/novel/series/(\d+)", re.I)
_NOVEL_SHOW = re.compile(r"(?:/novel/show\.php\?id=|/novel/(\d+))", re.I)
_NOVEL_ID_QS = re.compile(r"[?&]id=(\d+)", re.I)
_TAG_PATH = re.compile(r"/tags/([^/]+)/novels", re.I)
_RB_RE = re.compile(r"\[\[rb:([^\]>]+)(?:>[^\]]+)?\]\]")
_PIXIV_CMD_RE = re.compile(
    r"\[(?:pixivimage|uploadedimage|newpage|jumpuri|chapter)[^\]]*\]",
    re.I,
)


class PixivNetSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="pixiv_net",
                name="Pixiv Novels (pixiv.net)",
                base_url="https://www.pixiv.net",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="unused",
                content_selector="unused",
                novel_title_selector="unused",
                strip_lines_containing=["pixiv", "ピクシブ"],
                request_delay_sec=0.4,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _SERIES_URL.search(chapter_url)
        if m:
            return f"https://www.pixiv.net/novel/series/{m.group(1)}"
        m = _NOVEL_ID_QS.search(chapter_url) or re.search(r"/novel/(\d+)", chapter_url)
        if m:
            return f"https://www.pixiv.net/novel/show.php?id={m.group(1)}"
        return None

    @staticmethod
    def _search_word(genre_list_url: str) -> str:
        qs = parse_qs(urlparse(genre_list_url).query)
        if qs.get("word"):
            return unquote(qs["word"][0]).strip()
        m = _TAG_PATH.search(genre_list_url)
        if m:
            return unquote(m.group(1)).strip()
        return "ファンタジー"

    def _ajax(self, path: str, *, params: dict | None = None) -> dict:
        self._apply_user_session()
        url = path if path.startswith("http") else f"{self.cfg.base_url}{path}"

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch() -> dict:
            headers = {
                "Referer": "https://www.pixiv.net/",
                "Accept": "application/json",
            }
            if self.cfg.accept_language:
                headers["Accept-Language"] = self.cfg.accept_language
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            resp = self._client.get(url, headers=headers, params=params or {})
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} tại {url}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] JSON lỗi từ {url}: {exc}") from exc
            if payload.get("error"):
                raise ScrapeError(
                    f"[{self.key}] API lỗi tại {url}: {payload.get('message')}"
                )
            body = payload.get("body")
            if body is None:
                raise ScrapeError(f"[{self.key}] body rỗng từ {url}")
            return body if isinstance(body, dict) else {"_": body}

        try:
            data = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không gọi được {url} sau "
                f"{self.cfg.max_retries + 1} lần: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return data

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        word = self._search_word(genre_list_url)
        encoded = quote(word, safe="")
        body = self._ajax(
            f"/ajax/search/novels/{encoded}",
            params={
                "word": word,
                "order": "date_d",
                "mode": "safe",
                "s_mode": "s_tag",
                "p": page,
            },
        )
        novel_block = body.get("novel") if isinstance(body.get("novel"), dict) else body
        items = (novel_block or {}).get("data") or []
        results: list[NovelRef] = []
        seen: set[str] = set()
        for item in items:
            title = (item.get("title") or "").strip()
            series_id = item.get("seriesId")
            novel_id = item.get("id")
            if not title:
                continue
            if series_id:
                url = f"{self.cfg.base_url}/novel/series/{series_id}"
                key = f"s:{series_id}"
                display = (item.get("seriesTitle") or title).strip()
            elif novel_id:
                url = f"{self.cfg.base_url}/novel/show.php?id={novel_id}"
                key = f"n:{novel_id}"
                display = title
            else:
                continue
            if key in seen:
                continue
            seen.add(key)
            results.append(NovelRef(title=display, url=url, latest_chapter_title=title))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không có kết quả search '{word}'")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        sm = _SERIES_URL.search(novel_url)
        if sm:
            return self._list_series_chapters(sm.group(1))

        novel_id = self._novel_id_from_url(novel_url)
        if not novel_id:
            raise ScrapeError(f"[{self.key}] URL novel không hợp lệ: {novel_url}")
        body = self._ajax(f"/ajax/novel/{novel_id}")
        series = body.get("seriesNavData") or {}
        series_id = series.get("seriesId") if isinstance(series, dict) else None
        if series_id:
            return self._list_series_chapters(str(series_id))
        title = (body.get("title") or f"#{novel_id}").strip()
        return [
            ChapterRef(
                index=1,
                title=title,
                url=f"{self.cfg.base_url}/novel/show.php?id={novel_id}",
            )
        ]

    def _list_series_chapters(self, series_id: str) -> list[ChapterRef]:
        meta = self._ajax(f"/ajax/novel/series/{series_id}")
        total = int(meta.get("publishedContentCount") or meta.get("total") or 0)
        chapters: list[ChapterRef] = []
        last_order = 0
        guard = 0
        while guard < 80:
            guard += 1
            body = self._ajax(
                f"/ajax/novel/series_content/{series_id}",
                params={
                    "limit": 30,
                    "last_order": last_order,
                    "order_by": "asc",
                },
            )
            page = body.get("page") if isinstance(body.get("page"), dict) else {}
            items = page.get("seriesContents") or []
            if not items:
                break
            for item in items:
                nid = item.get("id")
                if not nid:
                    continue
                order = int((item.get("series") or {}).get("contentOrder") or len(chapters) + 1)
                title = (item.get("title") or f"#{nid}").strip()
                chapters.append(
                    ChapterRef(
                        index=order,
                        title=title,
                        url=f"{self.cfg.base_url}/novel/show.php?id={nid}",
                    )
                )
                last_order = max(last_order, order)
            if total and len(chapters) >= total:
                break
            if len(items) < 30:
                break
        chapters.sort(key=lambda c: c.index)
        chapters = [
            ChapterRef(index=i, title=ch.title, url=ch.url)
            for i, ch in enumerate(chapters, start=1)
        ]
        if not chapters:
            raise ScrapeError(f"[{self.key}] Series {series_id} không có chương")
        return chapters

    @staticmethod
    def _novel_id_from_url(url: str) -> str | None:
        m = _NOVEL_ID_QS.search(url)
        if m:
            return m.group(1)
        m = re.search(r"/novel/(\d+)/?$", url)
        return m.group(1) if m else None

    def fetch_novel_title(self, novel_url: str) -> str | None:
        sm = _SERIES_URL.search(novel_url)
        if sm:
            body = self._ajax(f"/ajax/novel/series/{sm.group(1)}")
            title = (body.get("title") or "").strip()
            return title or None
        novel_id = self._novel_id_from_url(novel_url)
        if not novel_id:
            return None
        body = self._ajax(f"/ajax/novel/{novel_id}")
        title = (body.get("title") or "").strip()
        return title or None

    def fetch_chapter_content(self, chapter_url: str) -> str:
        novel_id = self._novel_id_from_url(chapter_url)
        if not novel_id:
            raise ScrapeError(f"[{self.key}] URL chương không hợp lệ: {chapter_url}")
        body = self._ajax(f"/ajax/novel/{novel_id}")
        raw = body.get("content") or ""
        if not isinstance(raw, str) or not raw.strip():
            raise ScrapeError(f"[{self.key}] Nội dung rỗng novel {novel_id}")
        text = self._clean_pixiv_text(raw)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng sau khi lọc ({novel_id})")
        return text

    def _clean_pixiv_text(self, raw: str) -> str:
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        text = _RB_RE.sub(r"\1", text)
        text = _PIXIV_CMD_RE.sub("", text)
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        return "\n".join(lines)
