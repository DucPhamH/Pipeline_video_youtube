"""Tầng 2 — BaseHtmlSource nhưng `_get_soup` đi qua TLS rồi Playwright.

Site CF/JS kế thừa class này (hoặc override `_fetch_html`). Parse selector
vẫn dùng chung SourceConfig như tầng 1.
"""
from __future__ import annotations

import time

from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from crawl.domain.ports import ScrapeError
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource
from crawl.infrastructure.sources.browser_fetch import browser_get_html
from crawl.infrastructure.sources.content_pipeline import check_fetched_html
from crawl.infrastructure.sources.text_decode import decode_html_bytes
from crawl.infrastructure.sources.tls_fetch import (
    looks_like_cloudflare_challenge,
    tls_get,
)


class _TlsCloudflare(Exception):
    """TLS gặp CF/challenge — chuyển Playwright (không retry TLS thêm)."""


class BaseBrowserSource(BaseHtmlSource):
    """Escalation: httpx (base) bị bỏ qua — luôn TLS trước, CF → Playwright."""

    browser_wait_selector: str | None = None
    prefer_tls_first: bool = True
    tls_only: bool = False

    def _tls_fetch_once(self, url: str, *, cookie: str, referer: str) -> str:
        status, body, _ = tls_get(
            url,
            cookie_header=cookie,
            referer=referer,
            source_key=self.key,
            proxy=getattr(self, "_proxy_url", None) or None,
        )
        if looks_like_cloudflare_challenge(body):
            raise _TlsCloudflare(f"[{self.key}] Cloudflare/challenge tại {url}")
        if status != 200:
            raise ScrapeError(f"[{self.key}] tls_fetch HTTP {status} tại {url}")
        return decode_html_bytes(body, preferred=self.cfg.encoding)

    def _fetch_html(self, url: str, *, check_content_blockers: bool = False) -> str:
        self._apply_user_session()
        cookie = getattr(self, "_session_cookie_header", "") or ""
        referer = self.cfg.base_url

        if self.prefer_tls_first:
            @retry(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=2, min=2, max=8),
                retry=retry_if_exception_type(ScrapeError),
            )
            def _tls_with_retry() -> str:
                return self._tls_fetch_once(url, cookie=cookie, referer=referer)

            try:
                html = _tls_with_retry()
            except _TlsCloudflare:
                if getattr(self, "tls_only", False):
                    raise ScrapeError(
                        f"[{self.key}] Cloudflare/rate-limit tại {url} — "
                        f"dán cookie (cf_clearance + jieqiUserInfo), tăng delay quét, "
                        f"hoặc thử lại sau vài phút"
                    ) from None
            except ScrapeError:
                raise
            else:
                if check_content_blockers:
                    check_fetched_html(html, source_key=self.key, url=url)
                return html

        html = browser_get_html(
            url,
            cookie_header=cookie,
            wait_selector=self.browser_wait_selector,
            proxy=getattr(self, "_proxy_url", None) or None,
            source_key=self.key,
        )
        if looks_like_cloudflare_challenge(html):
            raise ScrapeError(f"[{self.key}] Cloudflare chưa qua tại {url}")
        if check_content_blockers:
            check_fetched_html(html, source_key=self.key, url=url)
        return html

    def _get_soup(self, url: str, *, check_content_blockers: bool = False) -> BeautifulSoup:
        try:
            html = self._fetch_html(url, check_content_blockers=check_content_blockers)
        except ScrapeError:
            raise
        except Exception as exc:
            raise ScrapeError(f"[{self.key}] Không tải được {url}: {exc}") from exc
        time.sleep(self.cfg.request_delay_sec)
        return BeautifulSoup(html, "lxml")
