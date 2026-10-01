"""Chặn SSRF + rò cookie khi fetch — dùng chung mọi tầng (httpx/TLS/browser).

- `assert_public_url`: URL phải http(s) và host KHÔNG trỏ tới IP private/
  loopback/link-local (trừ khi bật `CRAWL_ALLOW_PRIVATE_FETCH`).
- `cookie_allowed_for`: cookie phiên của site chỉ gửi tới host thuộc domain
  site đó (base_url + www./m./wap. + mirror khai báo)."""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from urllib.parse import urlsplit

from crawl.domain.urls import host_matches_source
from crawl.infrastructure.sources.content_pipeline import NonRetryableScrapeError

_DNS_TTL_SEC = 300.0
_dns_cache: dict[str, tuple[float, list[str]]] = {}
_dns_lock = threading.Lock()


class BlockedUrlError(NonRetryableScrapeError):
    """URL trỏ tới địa chỉ nội bộ / scheme lạ — không fetch."""


def _private_fetch_allowed() -> bool:
    try:
        from platform_.config import config

        return bool(config.crawl_allow_private_fetch)
    except Exception:
        return False


def is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def _resolve(host: str) -> list[str]:
    now = time.monotonic()
    with _dns_lock:
        hit = _dns_cache.get(host)
        if hit is not None and now - hit[0] < _DNS_TTL_SEC:
            return hit[1]
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({info[4][0] for info in infos})
    except (OSError, UnicodeError):
        # Không resolve được (offline / DNS qua proxy socks5h) — request thật
        # sẽ tự lỗi hoặc proxy tự resolve; không chặn ở đây.
        addrs = []
    with _dns_lock:
        _dns_cache[host] = (now, addrs)
    return addrs


def host_is_private(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return any(is_private_ip(a) for a in _resolve(host))
    return is_private_ip(host)


def assert_public_url(url: str, *, allow_private: bool | None = None) -> None:
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise BlockedUrlError(f"URL không hợp lệ (chỉ nhận http/https): {url}")
    if allow_private is None:
        allow_private = _private_fetch_allowed()
    if not allow_private and host_is_private(parts.hostname):
        raise BlockedUrlError(f"Chặn fetch tới địa chỉ nội bộ/private: {parts.hostname}")


def source_allowed_hosts(source) -> tuple[str, tuple[str, ...]]:
    """(base_url, mirror_hosts) của 1 SourcePort — rỗng nếu không có cfg."""
    cfg = getattr(source, "cfg", None)
    base_url = getattr(cfg, "base_url", "") or ""
    mirrors = tuple(getattr(cfg, "mirror_hosts", ()) or ())
    return base_url, mirrors


def url_belongs_to_source(url: str, source) -> bool:
    base_url, mirrors = source_allowed_hosts(source)
    if not base_url:
        return False
    return host_matches_source(url, base_url, mirrors)


def cookie_allowed_for(url: str, source_key: str | None) -> bool:
    """Cookie phiên của `source_key` có được gửi tới `url` không."""
    if not source_key:
        return False
    try:
        from crawl.infrastructure.sources.registry import SOURCES
    except Exception:
        return False
    source = SOURCES.get(source_key)
    if source is None:
        return False
    return url_belongs_to_source(url, source)
