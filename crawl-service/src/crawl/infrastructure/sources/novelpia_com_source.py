"""Adapter novelpia.com — web novel Hàn Quốc qua API /proc (SPA, không parse HTML list).

- Danh sách: GET /proc/novelsearch_v2/?search_text=...
- Mục lục: POST /proc/episode_list
- Nội dung: GET /proc/viewer_data/{episode_no}
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_NOVEL_URL = re.compile(r"/novel/(\d+)", re.I)
_VIEWER_URL = re.compile(r"/viewer/(\d+)", re.I)


class NovelpiaComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="novelpia_com",
                name="Novelpia (노벨피아)",
                base_url="https://novelpia.com",
                content_locale="ko",
                accept_language="ko,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector="unused",
                content_selector="unused",
                novel_title_selector="unused",
                strip_lines_containing=["novelpia", "노벨피아", "로그인", "구독", "PLUS"],
                request_delay_sec=0.35,
                paginate_list_url=None,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        # viewer URL không mang novel_no — caller nên dùng novel.url đã lưu
        return None

    @staticmethod
    def _search_text_from_list_url(genre_list_url: str) -> str:
        qs = parse_qs(urlparse(genre_list_url).query)
        values = qs.get("search_text") or qs.get("q") or []
        if values and values[0].strip():
            return values[0].strip()
        # fallback: path cuối
        path = urlparse(genre_list_url).path.rstrip("/").split("/")[-1]
        return path or "판타지"

    def _request_json(self, method: str, url: str, **kwargs) -> dict | list | str:
        self._apply_user_session()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries + 1),
            wait=wait_exponential(multiplier=self.cfg.backoff_base_sec, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ScrapeError)),
        )
        def _fetch():
            headers = {
                "Referer": self.cfg.base_url + "/",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
            if self.cfg.accept_language:
                headers["Accept-Language"] = self.cfg.accept_language
            if getattr(self, "_session_cookie_header", ""):
                headers["Cookie"] = self._session_cookie_header
            resp = self._client.request(method, url, headers=headers, **kwargs)
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} khi gọi {url}")
            text = resp.text.strip()
            if not text:
                raise ScrapeError(f"[{self.key}] Response rỗng từ {url}")
            try:
                return resp.json()
            except json.JSONDecodeError:
                # một số endpoint trả HTML fragment — trả raw
                return text

        try:
            data = _fetch()
        except (httpx.HTTPError, ScrapeError) as exc:
            raise ScrapeError(
                f"[{self.key}] Không gọi được {url} sau {self.cfg.max_retries + 1} lần: {exc}"
            ) from exc
        time.sleep(self.cfg.request_delay_sec)
        return data

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        search_text = self._search_text_from_list_url(genre_list_url)
        data = self._request_json(
            "GET",
            f"{self.cfg.base_url}/proc/novelsearch_v2/",
            params={"search_text": search_text, "page": page, "rows": 20},
        )
        if not isinstance(data, dict) or data.get("status") != 200:
            errmsg = data.get("errmsg") if isinstance(data, dict) else data
            if page > 1:
                return []
            raise ScrapeError(f"[{self.key}] novelsearch_v2 lỗi: {errmsg}")

        items = (data.get("novel_search") or {}).get("list") or []
        results: list[NovelRef] = []
        for item in items:
            novel_no = item.get("novel_no")
            name = (item.get("novel_name") or "").strip()
            if not novel_no or not name:
                continue
            results.append(
                NovelRef(
                    title=name,
                    url=f"{self.cfg.base_url}/novel/{novel_no}",
                    latest_chapter_title="",
                )
            )
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không có kết quả search '{search_text}'")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _NOVEL_URL.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL novel không hợp lệ: {novel_url}")
        novel_no = m.group(1)

        chapters: list[ChapterRef] = []
        seen_ep: set[str] = set()
        max_pages = 1
        page = 0  # Novelpia dùng page 0-based
        while page < max_pages and page < 80:
            html = self._request_json(
                "POST",
                f"{self.cfg.base_url}/proc/episode_list",
                data={"novel_no": novel_no, "page": str(page)},
            )
            if not isinstance(html, str):
                html = str(html)
            soup = BeautifulSoup(html, "lxml")
            rows = soup.select("tr.ep_style5[data-episode-no]")
            if not rows:
                break
            for tr in rows:
                ep_no = (tr.get("data-episode-no") or "").strip()
                if not ep_no or ep_no in seen_ep:
                    continue
                seen_ep.add(ep_no)
                title = self._clean_episode_title(tr.get_text(" ", strip=True), len(chapters) + 1)
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=title,
                        url=f"{self.cfg.base_url}/viewer/{ep_no}",
                    )
                )
            # "/ 39" trong UI chọn trang
            m_max = re.search(r"/\s*(\d+)\s*</strong>", html)
            if m_max:
                max_pages = max(max_pages, int(m_max.group(1)))
            else:
                # fallback: số page-item lớn nhất
                nums = [
                    int(n.get_text(strip=True))
                    for n in soup.select("li.page-item")
                    if n.get_text(strip=True).isdigit()
                ]
                if nums:
                    max_pages = max(max_pages, max(nums))
                elif page == 0:
                    break
            page += 1

        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy chương cho novel {novel_no} — "
                "có thể cần phiên đăng nhập / PLUS."
            )
        return chapters

    @staticmethod
    def _clean_episode_title(raw: str, fallback_idx: int) -> str:
        text = re.sub(r"\s+", " ", (raw or "").strip())
        text = re.sub(r"^(무료|PLUS|잠금)\s*", "", text)
        # giữ phần đến hết EP.N, bỏ cụm số liệu/ngày phía sau
        m = re.match(r"^(.*?EP\.\s*\d+)", text, re.I)
        if m:
            return m.group(1).strip()
        text = re.sub(
            r"\s+\d{1,3}(?:,\d{3})*(?:\s+\d+){0,5}\s+\d{2}\.\d{2}\.\d{2}\s*$",
            "",
            text,
        ).strip()
        return text or f"EP.{fallback_idx}"

    def fetch_novel_title(self, novel_url: str) -> str | None:
        soup = self._get_soup(novel_url)
        # title dạng "노벨피아 - ... - {name}"
        if soup.title:
            raw = soup.title.get_text(strip=True)
            parts = [p.strip() for p in raw.split(" - ") if p.strip()]
            if len(parts) >= 2:
                return parts[-1]
        return None

    def fetch_chapter_content(self, chapter_url: str) -> str:
        m = _VIEWER_URL.search(chapter_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL viewer không hợp lệ: {chapter_url}")
        ep_no = m.group(1)
        data = self._request_json("GET", f"{self.cfg.base_url}/proc/viewer_data/{ep_no}")
        if not isinstance(data, dict) or "s" not in data:
            raise ScrapeError(f"[{self.key}] viewer_data không hợp lệ cho episode {ep_no}")

        chunks: list[str] = []
        for block in data.get("s") or []:
            raw = block.get("text") if isinstance(block, dict) else None
            if not raw:
                continue
            soup = BeautifulSoup(raw, "lxml")
            for br in soup.find_all("br"):
                br.replace_with("\n")
            text = soup.get_text("\n")
            chunks.append(text)

        combined = "\n".join(chunks)
        lines = [
            line.strip()
            for line in combined.splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        # bỏ dòng cover UI
        lines = [ln for ln in lines if "커버접기" not in ln and "cover-wrapper" not in ln]
        text = "\n".join(lines)
        if not text:
            raise ScrapeError(
                f"[{self.key}] Nội dung rỗng (episode {ep_no}) — có thể là VIP cần phiên."
            )
        return text
