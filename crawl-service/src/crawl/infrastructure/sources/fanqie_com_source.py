"""Adapter fanqienovel.com (番茄小说) — list/TOC qua API công khai.

Nội dung reader dùng font obfuscation (PUA) — text `.muye-reader-content` được
giải bằng bảng `_PUA_CHARSET` (`decode_pua`); VIP/API full thường rỗng.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_BOOK_ID = re.compile(r"(?:/page/|bookId=|book_id=)(\d{10,})")
_ITEM_ID = re.compile(r"/reader/(\d{10,})")

# Font reader (bytetos awesome-font/c/dc027189e0ba4cd): mã PUA U+E3E8+i vẽ ra
# glyph của _PUA_CHARSET[i]. "?" = mã không có glyph trong font — giữ nguyên.
# Đã đối chiếu từng glyph của font với bảng này (7/10/2026).
_PUA_START = 0xE3E8
_PUA_CHARSET = (
    "D在主特家军然表场4要只v和?6别还g现儿岁??此象月3出战工相o男直失世F都平文什VO将真T那当?会立些u是十张学气大爱两"
    "命全后东性通被1它乐接而感车山公了常以何可话先pi叫轻M士w着变尔快l个说少色里安花远7难师放t报认面道S?克地度I好机U民"
    "写把万同水新没书电吃像斯5为y白几日教看但第加候作上拉住有法r事应位利你声身国问马女他Y比父xAHNsX边美对所金活回意到z"
    "从j知又内因点Q三定8Rb正或夫向德听更?得告并本q过记L让打f人就者去原满体做经K走如孩cG给使物?最笑部?员等受k行一条"
    "果动光门头见往自解成处天能于名其发总母的死手入路进心来h时力多开已许d至由很界n小与Z想代么分生口再妈望次西风种带J?实情才"
    "这?E我神格长觉间年眼无不亲关结0友信下却重己老2音字m呢明之前高PB目太e9起稜她也W用方子英每理便四数期中C外样a海们任"
)
_PUA_TABLE = {_PUA_START + i: c for i, c in enumerate(_PUA_CHARSET) if c != "?"}


def decode_pua(text: str) -> str:
    return text.translate(_PUA_TABLE)


class FanqieComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="fanqie_com",
                name="Fanqie (fanqienovel.com · 番茄 · font obfuscation)",
                base_url="https://fanqienovel.com",
                content_locale="zh",
                accept_language="zh-CN,zh;q=0.9",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="unused",
                content_selector=".muye-reader-content, .reader-content",
                novel_title_selector="h1",
                strip_lines_containing=["番茄", "fanqie", "本章字数"],
                request_delay_sec=1.2,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if "book_list" in url or "page_index" in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            qs["page_index"] = [str(max(0, page - 1))]
            flat = {k: v[0] for k, v in qs.items()}
            return urlunparse(parsed._replace(query=urlencode(flat)))
        if re.search(r"/page_(\d+)", url):
            return re.sub(r"/page_\d+", f"/page_{page}", url)
        return url

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        # reader URL không chứa book — caller nên dán /page/{book_id}
        return None

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if "book_list" in genre_list_url or "api/" in genre_list_url:
            return self._list_from_api(genre_list_url, page)
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/page/"]'):
            href = a.get("href") or ""
            m = _BOOK_ID.search(href)
            if not m:
                continue
            title = a.get_text(strip=True)
            if len(title) < 2:
                continue
            abs_url = f"https://fanqienovel.com/page/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được sách tại {url}")
        return results

    def _list_from_api(self, genre_list_url: str, page: int) -> list[NovelRef]:
        url = self._paginate_list_url(genre_list_url, page)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _get() -> dict:
            r = self._client.get(
                url,
                headers={"Referer": self.cfg.base_url + "/", "Accept": "application/json"},
            )
            r.raise_for_status()
            return r.json()

        data = _get()
        books = (data.get("data") or {}).get("book_list") or []
        results: list[NovelRef] = []
        for b in books:
            bid = str(b.get("book_id") or "")
            if not bid:
                continue
            title = decode_pua(str(b.get("book_name") or "").strip()) or f"book-{bid}"
            results.append(
                NovelRef(
                    title=title,
                    url=f"https://fanqienovel.com/page/{bid}",
                    latest_chapter_title="",
                )
            )
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] API library rỗng: {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _BOOK_ID.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] Cần URL /page/{{book_id}}: {novel_url}")
        bid = m.group(1)
        api = f"https://fanqienovel.com/api/reader/directory/detail?bookId={bid}"

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _get() -> dict:
            r = self._client.get(
                api,
                headers={"Referer": f"https://fanqienovel.com/page/{bid}", "Accept": "application/json"},
            )
            r.raise_for_status()
            return r.json()

        data = (_get().get("data") or {})
        item_ids = data.get("allItemIds") or []
        # ưu tiên tên chương từ volume list nếu có
        titles: dict[str, str] = {}
        for vol in data.get("chapterListWithVolume") or []:
            for ch in vol if isinstance(vol, list) else (vol.get("chapterList") or vol.get("chapter_list") or []):
                if isinstance(ch, dict):
                    iid = str(ch.get("itemId") or ch.get("item_id") or ch.get("id") or "")
                    t = decode_pua(str(ch.get("title") or ch.get("chapter_name") or "").strip())
                    if iid and t:
                        titles[iid] = t

        chapters: list[ChapterRef] = []
        for iid in item_ids:
            iid_s = str(iid)
            chapters.append(
                ChapterRef(
                    index=len(chapters) + 1,
                    title=titles.get(iid_s) or f"第{len(chapters) + 1}章",
                    url=f"https://fanqienovel.com/reader/{iid_s}",
                )
            )
        if not chapters:
            # fallback: parse /page HTML
            soup = self._get_soup(f"https://fanqienovel.com/page/{bid}")
            seen: set[str] = set()
            for a in soup.select('a[href*="/reader/"]'):
                href = a.get("href") or ""
                im = _ITEM_ID.search(href)
                if not im or im.group(1) in seen:
                    continue
                seen.add(im.group(1))
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=a.get_text(strip=True) or f"第{len(chapters)+1}章",
                        url=f"https://fanqienovel.com/reader/{im.group(1)}",
                    )
                )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không có mục lục cho book {bid}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Thiếu reader content tại {chapter_url} "
                "(có thể bị chặn / cần cookie)."
            )
        text = decode_pua(node.get_text("\n", strip=True))
        # PUA còn sót nhiều sau giải mã = site đã đổi font/bảng mã.
        pua = sum(1 for ch in text if 0xE000 <= ord(ch) <= 0xF8FF)
        if pua > max(40, len(text) // 3):
            raise ScrapeError(
                f"[{self.key}] Nội dung bị font-obfuscation tại {chapter_url} — "
                "font có thể đã đổi, cần cập nhật _PUA_CHARSET."
            )
        if len(text) < 40:
            raise ScrapeError(f"[{self.key}] Nội dung quá ngắn tại {chapter_url}")
        return text
