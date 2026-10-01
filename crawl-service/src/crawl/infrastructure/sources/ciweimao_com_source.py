"""Adapter ciweimao.com (刺猬猫) — cookie session; text chapter qua API;
ảnh VIP → OCR (`content_pipeline.ocr_image_bytes`). Tham khảo novel-downloader.
"""
from __future__ import annotations

import base64
import json
import re

from bs4 import BeautifulSoup

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import assert_not_vip_locked, ocr_image_bytes
from crawl.infrastructure.sources.fetch_guard import assert_public_url, url_belongs_to_source
_BOOK = re.compile(r"/book/(\d+)")
_CHAPTER = re.compile(r"/chapter/(\d+)")


class CiweimaoComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="ciweimao_com",
                name="ciweimao.com (刺猬猫)",
                base_url="https://www.ciweimao.com",
                genre_item_selector=".book-list li, .cover-list li",
                genre_title_selector='a[href*="/book/"]',
                chapter_list_selector='a[href*="/chapter/"]',
                content_selector=".chapter-content, #J_BookRead",
                novel_title_selector="h1.title, h1",
                strip_lines_containing=["刺猬猫", "ciweimao"],
                request_delay_sec=1.5,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    def _fetch_bytes(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict | None = None,
        ajax: bool = False,
        referer: str | None = None,
    ) -> bytes:
        self._apply_user_session()
        cookie = getattr(self, "_session_cookie_header", "") or ""
        headers = {
            "Referer": referer or self.cfg.base_url,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": self.cfg.base_url,
        }
        if ajax:
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        if cookie and url_belongs_to_source(url, self):
            headers["Cookie"] = cookie
        assert_public_url(url)

        try:
            from curl_cffi import requests as crequests

            proxy = getattr(self, "_proxy_url", None) or None
            req_kwargs: dict = {"headers": headers, "impersonate": "chrome124", "timeout": 25}
            if proxy:
                req_kwargs["proxy"] = proxy
            if method == "POST":
                resp = crequests.post(url, data=data or {}, **req_kwargs)
            else:
                resp = crequests.get(url, **req_kwargs)
        except ImportError:
            if method == "POST":
                resp = self._client.post(url, data=data or {}, headers=headers)
            else:
                resp = self._client.get(url, headers=headers)

        if resp.status_code != 200:
            raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} {url}")
        return resp.content

    def _get_soup(self, url: str) -> BeautifulSoup:
        import time

        body = self._fetch_bytes(url)
        time.sleep(self.cfg.request_delay_sec)
        return BeautifulSoup(body, "lxml")

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
        for a in soup.select('a[href*="/book/"]'):
            href = a.get("href") or ""
            m = _BOOK.search(href)
            if not m:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 2 or title in ("登录", "注册"):
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
        m = _BOOK.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL book không hợp lệ: {novel_url}")
        book_id = m.group(1)
        raw = self._fetch_bytes(
            "https://www.ciweimao.com/chapter/get_chapter_list_in_chapter_detail",
            method="POST",
            data={"book_id": book_id, "chapter_id": "0", "orderby": "0"},
        )
        text = raw.decode("utf-8", errors="ignore")
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        # HTML fragment with chapter links
        soup = BeautifulSoup(text, "lxml")
        for a in soup.select('a[href*="/chapter/"]'):
            href = a.get("href") or ""
            cm = _CHAPTER.search(href)
            if not cm:
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
            # try JSON
            try:
                data = json.loads(text)
                html_frag = data.get("chapter_list") or data.get("data") or ""
                if isinstance(html_frag, str) and html_frag:
                    soup = BeautifulSoup(html_frag, "lxml")
                    for a in soup.select('a[href*="/chapter/"]'):
                        href = a.get("href") or ""
                        title = a.get_text(strip=True)
                        if not href or not title:
                            continue
                        abs_url = self._abs_url(href)
                        if abs_url in seen:
                            continue
                        seen.add(abs_url)
                        chapters.append(
                            ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
                        )
            except json.JSONDecodeError:
                pass
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không lấy được mục lục (cần cookie?) book={book_id}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        m = _CHAPTER.search(chapter_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL chương không hợp lệ: {chapter_url}")
        chapter_id = m.group(1)
        page = self._fetch_bytes(chapter_url).decode("utf-8", errors="ignore")
        page_soup = BeautifulSoup(page, "lxml")
        page_title = page_soup.title.get_text(strip=True) if page_soup.title else ""
        if "验证码" in page_title:
            raise ScrapeError(
                f"[{self.key}] Trang chương yêu cầu đăng nhập/CAPTCHA — "
                f"dán cookie session ciweimao: {chapter_url}"
            )
        assert_not_vip_locked(page, source_key=self.key, url=chapter_url)

        if "J_ImgRead" in page:
            return self._fetch_image_chapter(chapter_id, chapter_url)

        from crawl.infrastructure.sources.ciweimao_crypto import ciweimao_decrypt

        sess_raw = self._fetch_bytes(
            "https://www.ciweimao.com/chapter/ajax_get_session_code",
            method="POST",
            data={"chapter_id": chapter_id},
            ajax=True,
            referer=chapter_url,
        )
        try:
            sess = json.loads(sess_raw.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as exc:
            raise ScrapeError(f"[{self.key}] session JSON lỗi: {exc}") from exc

        chapter_access = sess.get("chapter_access_key")
        if not chapter_access:
            soup = BeautifulSoup(page, "lxml")
            node = soup.select_one(self.cfg.content_selector)
            if node and len(node.get_text(strip=True)) > 50:
                return self._clean_text(node.get_text("\n"))
            raise ScrapeError(
                f"[{self.key}] Không lấy session chapter — cần cookie đăng nhập: {chapter_url}"
            )

        detail_raw = self._fetch_bytes(
            "https://www.ciweimao.com/chapter/get_book_chapter_detail_info",
            method="POST",
            data={"chapter_id": chapter_id, "chapter_access_key": chapter_access},
            ajax=True,
            referer=chapter_url,
        )
        try:
            detail = json.loads(detail_raw.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as exc:
            raise ScrapeError(f"[{self.key}] detail JSON lỗi") from exc

        code = detail.get("code")
        if code not in (None, 100000, "100000"):
            tip = detail.get("tip") or detail.get("msg") or code
            raise ScrapeError(
                f"[{self.key}] API chương từ chối ({tip}) — cần cookie / đã mua: {chapter_url}"
            )

        enc_content = detail.get("chapter_content") or ""
        enc_keys = detail.get("encryt_keys") or []
        if not enc_content:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng / VIP chưa mua: {chapter_url}")
        if enc_keys:
            try:
                content = ciweimao_decrypt(enc_content, enc_keys, chapter_access)
            except Exception as exc:
                raise ScrapeError(f"[{self.key}] Giải mã AES thất bại: {exc}") from exc
        else:
            content = enc_content
        soup = BeautifulSoup(content, "lxml")
        for span in soup.select("span"):
            span.decompose()
        return self._clean_text(soup.get_text("\n"))

    def _fetch_image_chapter(self, chapter_id: str, chapter_url: str) -> str:
        """VIP ảnh — lấy image bytes rồi OCR."""
        sess_raw = self._fetch_bytes(
            "https://www.ciweimao.com/chapter/ajax_get_image_session_code",
            method="POST",
            data={"chapter_id": chapter_id},
        )
        try:
            sess = json.loads(sess_raw.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as exc:
            raise ScrapeError(f"[{self.key}] image session JSON lỗi") from exc

        # Một số response trả sẵn base64; nếu có thì OCR luôn
        for key in ("image_content", "data"):
            val = sess.get(key)
            if isinstance(val, str) and len(val) > 200:
                try:
                    raw = base64.b64decode(val)
                    return ocr_image_bytes(raw)
                except Exception:
                    pass

        # URL ảnh VIP
        img_url = (
            f"https://www.ciweimao.com/chapter/book_chapter_image"
            f"?chapter_id={chapter_id}&area_width=820&quality=80"
        )
        try:
            img_bytes = self._fetch_bytes(img_url)
        except ScrapeError as exc:
            raise ScrapeError(
                f"[{self.key}] Không tải ảnh VIP (cần cookie đã mua chương): {chapter_url}"
            ) from exc
        if len(img_bytes) < 500 or img_bytes[:1] == b"{":
            raise ScrapeError(
                f"[{self.key}] Ảnh VIP không hợp lệ / hết quyền — kiểm tra cookie: {chapter_url}"
            )
        return ocr_image_bytes(img_bytes)

    def _clean_text(self, text: str) -> str:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        out = "\n".join(lines)
        if not out:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng sau lọc")
        return out

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        return super()._abs_url(href)

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        # chapter page alone không suy ra book id ổn định → None
        return None

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        # /book_list/xuanhuan → /book_list/0-0-0-0-0-0/xuanhuan/{page}
        m = re.search(r"/book_list/([^/]+)/?$", url)
        if m and "-" not in m.group(1):
            slug = m.group(1)
            return f"https://www.ciweimao.com/book_list/0-0-0-0-0-0/{slug}/{page}"
        if re.search(r"/\d+$", url):
            return re.sub(r"/\d+$", f"/{page}", url)
        return f"{url.rstrip('/')}/{page}"
