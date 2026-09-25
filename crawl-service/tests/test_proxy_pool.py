"""Proxy pool — parse URL / vùng / UI settings / round-robin (không cần mạng)."""
from pathlib import Path

from crawl.infrastructure.sources.proxy_pool import (
    get_a_proxy,
    playwright_proxy_config,
    region_proxy,
    reset_proxy_cache,
)


def test_normalize_and_round_robin(monkeypatch, tmp_path: Path):
    reset_proxy_cache()
    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text(
        "# comment\n"
        "127.0.0.1:9001\n"
        "socks5h://127.0.0.1:9002\n"
        "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CRAWL_HTTP_PROXY", raising=False)
    monkeypatch.delenv("CRAWL_PROXY", raising=False)
    monkeypatch.delenv("CRAWL_PROXY_VN", raising=False)
    for k in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CRAWL_PROXY_FILE", str(proxy_file))
    # UI trống — chỉ pool file
    monkeypatch.setattr(
        "crawl.infrastructure.sources.proxy_pool._read_setting", lambda _k: ""
    )

    a = get_a_proxy()
    b = get_a_proxy()
    assert a == "http://127.0.0.1:9001"
    assert b == "socks5h://127.0.0.1:9002"
    assert get_a_proxy() == "http://127.0.0.1:9001"


def test_region_override_vn(monkeypatch):
    reset_proxy_cache()
    monkeypatch.setenv("CRAWL_HTTP_PROXY", "http://global:1")
    monkeypatch.setenv("CRAWL_PROXY_VN", "socks5h://vn-exit:1080")
    monkeypatch.delenv("CRAWL_PROXY_FILE", raising=False)
    monkeypatch.setattr(
        "crawl.infrastructure.sources.proxy_pool._read_setting", lambda _k: ""
    )

    assert region_proxy("vietnam") == "socks5h://vn-exit:1080"
    assert get_a_proxy(source_key="truyenfull_vn") == "socks5h://vn-exit:1080"
    # site TQ dùng proxy global
    assert get_a_proxy(source_key="bqgxs_com") == "http://global:1"


def test_ui_per_site_overrides_env(monkeypatch):
    reset_proxy_cache()
    monkeypatch.setenv("CRAWL_PROXY_VN", "socks5h://env-vn:1080")
    monkeypatch.delenv("CRAWL_HTTP_PROXY", raising=False)
    monkeypatch.delenv("CRAWL_PROXY_FILE", raising=False)

    def fake_read(key: str) -> str:
        if key == "crawl.http_proxy.truyenfull_today":
            return "http://127.0.0.1:7890"
        if key == "crawl.proxy.vn":
            return "http://ui-vn:1"
        return ""

    monkeypatch.setattr(
        "crawl.infrastructure.sources.proxy_pool._read_setting", fake_read
    )
    assert get_a_proxy(source_key="truyenfull_today") == "http://127.0.0.1:7890"
    # site VN khác không có per-site → UI vùng
    assert get_a_proxy(source_key="dtruyen_com") == "http://ui-vn:1"


def test_ui_region_overrides_env(monkeypatch):
    reset_proxy_cache()
    monkeypatch.setenv("CRAWL_PROXY_VN", "socks5h://env-vn:1080")
    monkeypatch.setattr(
        "crawl.infrastructure.sources.proxy_pool._read_setting",
        lambda k: "http://ui-vn:7890" if k == "crawl.proxy.vn" else "",
    )
    assert region_proxy("vietnam") == "http://ui-vn:7890"
    assert get_a_proxy(source_key="truyenfull_vn") == "http://ui-vn:7890"


def test_playwright_proxy_auth():
    cfg = playwright_proxy_config("socks5://user%40x:p%40ss@127.0.0.1:1080")
    assert cfg["server"] == "socks5://127.0.0.1:1080"
    assert cfg["username"] == "user@x"
    assert cfg["password"] == "p@ss"
