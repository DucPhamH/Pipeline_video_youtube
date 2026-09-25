"""Tầng 1b — HTTP với TLS fingerprint trình duyệt (`curl_cffi`).

Dùng khi httpx bị soft-block / CF nhẹ vì fingerprint TLS. Cookie user
(session) gắn vào mọi request. Fallback: caller chuyển Playwright.
"""
from __future__ import annotations

from crawl.domain.ports import ScrapeError

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def tls_get(
    url: str,
    *,
    cookie_header: str = "",
    referer: str = "",
    timeout: float = 25.0,
    impersonate: str = "chrome136",
    proxy: str | None = None,
    source_key: str | None = None,
) -> tuple[int, bytes, str]:
    """GET → (status_code, body_bytes, final_url). Raise ScrapeError nếu thiếu curl_cffi."""
    try:
        from curl_cffi import requests as crequests
    except ImportError as exc:
        raise ScrapeError(
            "Thiếu curl_cffi — pip install curl_cffi (tầng 1b TLS impersonate)"
        ) from exc

    headers: dict[str, str] = {
        "User-Agent": _DEFAULT_UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if cookie_header:
        headers["Cookie"] = cookie_header

    if proxy is None:
        from crawl.infrastructure.sources.proxy_pool import get_a_proxy

        proxy = get_a_proxy(source_key=source_key)

    try:
        kwargs: dict = {
            "headers": headers,
            "timeout": timeout,
            "impersonate": impersonate,
            "allow_redirects": True,
        }
        if proxy:
            kwargs["proxy"] = proxy
        resp = crequests.get(url, **kwargs)
    except Exception as exc:
        raise ScrapeError(f"tls_fetch lỗi mạng {url}: {exc}") from exc

    return resp.status_code, resp.content, str(resp.url)


def looks_like_cloudflare_challenge(html: str | bytes) -> bool:
    """Trang chặn CF thật — KHÔNG dùng script challenge-platform (wenku8 gắn trên mọi trang)."""
    text = html.decode("utf-8", errors="ignore") if isinstance(html, bytes) else html
    lower = text.lower()
    head = lower[:8000]

    if "just a moment" in head and "cloudflare" in head:
        return True
    if "access denied" in head and "cloudflare" in head:
        return True
    if "cf-browser-verification" in head:
        return True
    if "attention required" in head and "cloudflare" in head:
        return True
    if "challenges.cloudflare.com" in head:
        return True
    # Trang challenge tương tác — thường rất ngắn, không có nội dung site
    if len(text) < 3000 and "cdn-cgi/challenge" in head and "just a moment" in head:
        return True
    return False


def tls_get_html(
    url: str,
    *,
    cookie_header: str = "",
    referer: str = "",
    encoding: str | None = None,
    timeout: float = 25.0,
    proxy: str | None = None,
    source_key: str | None = None,
) -> str:
    from crawl.infrastructure.sources.text_decode import decode_html_bytes

    status, body, _ = tls_get(
        url,
        cookie_header=cookie_header,
        referer=referer,
        timeout=timeout,
        proxy=proxy,
        source_key=source_key,
    )
    if status != 200:
        raise ScrapeError(f"tls_fetch HTTP {status} tại {url}")
    if looks_like_cloudflare_challenge(body):
        raise ScrapeError(f"tls_fetch gặp Cloudflare challenge tại {url}")
    return decode_html_bytes(body, preferred=encoding)
