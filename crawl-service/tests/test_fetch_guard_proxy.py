"""DNS nhà mạng trả 127.0.0.1 cho site truyện VN: đi qua proxy tự resolve DNS
(http/socks5h) thì không được chặn vì kết quả DNS tại máy; proxy socks5://
(DNS tại chỗ) thì tra lại qua DoH và kiểm tra IP đó."""
import httpx
import pytest

from crawl.infrastructure.sources import fetch_guard
from crawl.infrastructure.sources.fetch_guard import BlockedUrlError, assert_public_url
from crawl.infrastructure.sources.proxy_pool import LocalDnsSocksTransport


@pytest.fixture(autouse=True)
def isp_dns_block(monkeypatch):
    monkeypatch.setattr(fetch_guard, "_resolve", lambda host: ["127.0.0.1"])
    monkeypatch.setattr(fetch_guard, "_resolve_doh", lambda host: [])
    monkeypatch.setattr(fetch_guard, "_dns_cache", {})


def test_blocked_without_proxy():
    with pytest.raises(BlockedUrlError):
        assert_public_url("https://sstruyen.net/", allow_private=False)


@pytest.mark.parametrize("proxy", ["socks5h://127.0.0.1:40000", "http://127.0.0.1:7890"])
def test_allowed_through_remote_dns_proxy(proxy):
    assert_public_url("https://sstruyen.net/", allow_private=False, proxy=proxy)


def test_socks5_local_dns_still_checked():
    with pytest.raises(BlockedUrlError):
        assert_public_url("https://sstruyen.net/", allow_private=False, proxy="socks5://127.0.0.1:1080")


def test_socks5_allowed_when_doh_returns_public_ip(monkeypatch):
    monkeypatch.setattr(fetch_guard, "_resolve_doh", lambda host: ["104.21.9.104"])
    assert_public_url("https://sstruyen.net/", allow_private=False, proxy="socks5://127.0.0.1:40000")


def test_socks5_blocked_when_doh_also_private(monkeypatch):
    monkeypatch.setattr(fetch_guard, "_resolve_doh", lambda host: ["10.0.0.1"])
    with pytest.raises(BlockedUrlError):
        assert_public_url("https://sstruyen.net/", allow_private=False, proxy="socks5://127.0.0.1:40000")


def test_doh_not_used_without_proxy(monkeypatch):
    monkeypatch.setattr(fetch_guard, "_resolve_doh", lambda host: ["104.21.9.104"])
    with pytest.raises(BlockedUrlError):
        assert_public_url("https://sstruyen.net/", allow_private=False)


def test_transport_connects_to_doh_ip(monkeypatch):
    monkeypatch.setattr(fetch_guard, "_resolve_doh", lambda host: ["104.21.9.104"])
    seen = {}

    def fake_handle(self, request):
        seen["host"] = request.url.host
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    transport = LocalDnsSocksTransport(proxy="socks5://127.0.0.1:40000")
    transport.handle_request(httpx.Request("GET", "https://sstruyen.net/"))
    assert seen == {"host": "104.21.9.104", "sni": "sstruyen.net"}


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/", "http://localhost/", "http://10.0.0.5/"])
def test_private_literals_blocked_even_with_proxy(url):
    with pytest.raises(BlockedUrlError):
        assert_public_url(url, allow_private=False, proxy="socks5h://127.0.0.1:40000")
