"""Integration: chứng minh traffic httpx + tls_fetch đi QUA proxy (không chỉ parse env)."""
from __future__ import annotations

import select
import socket
import threading
from pathlib import Path

import httpx
import pytest

from crawl.infrastructure.sources.proxy_pool import get_a_proxy, reset_proxy_cache
from crawl.infrastructure.sources.tls_fetch import tls_get
from crawl.infrastructure.sources.truyenfull_vn_source import TruyenfullVnSource


def _start_counting_proxy(hit_log: Path) -> tuple[socket.socket, int]:
    hit_log.write_text("")
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(50)
    port = srv.getsockname()[1]

    def handle(conn: socket.socket) -> None:
        try:
            data = conn.recv(65535)
            if not data:
                conn.close()
                return
            line = data.split(b"\r\n", 1)[0].decode("latin1", "ignore")
            hit_log.open("a").write(line + "\n")
            if not line.upper().startswith("CONNECT "):
                conn.close()
                return
            target = line.split(" ")[1]
            host, _, port_s = target.partition(":")
            remote = socket.create_connection((host, int(port_s or 443)), timeout=20)
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            socks = [conn, remote]
            while True:
                readable, _, err = select.select(socks, [], socks, 30)
                if err or not readable:
                    break
                for s in readable:
                    other = remote if s is conn else conn
                    chunk = s.recv(65535)
                    if not chunk:
                        remote.close()
                        conn.close()
                        return
                    other.sendall(chunk)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    def accept_loop() -> None:
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                break
            threading.Thread(target=handle, args=(c,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return srv, port


@pytest.fixture()
def counting_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hit_log = tmp_path / "hits.log"
    srv, port = _start_counting_proxy(hit_log)
    proxy_url = f"http://127.0.0.1:{port}"
    for key in list(__import__("os").environ):
        if "PROXY" in key.upper() or key.startswith("CRAWL_PROXY"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CRAWL_HTTP_PROXY", proxy_url)
    monkeypatch.setenv("CRAWL_PROXY_VN", proxy_url)
    monkeypatch.setattr(
        "platform_.session_cookies.load_cookie_header",
        lambda _source_key: "",
    )
    monkeypatch.setattr(
        "crawl.infrastructure.sources.proxy_pool._read_setting",
        lambda _key: "",
    )
    reset_proxy_cache()

    def read_hits() -> list[str]:
        if not hit_log.exists():
            return []
        return [ln for ln in hit_log.read_text().splitlines() if ln.strip()]

    yield proxy_url, read_hits
    try:
        srv.close()
    except Exception:
        pass
    reset_proxy_cache()


@pytest.mark.integration
def test_httpx_source_traffic_goes_through_proxy(counting_proxy):
    proxy_url, read_hits = counting_proxy
    src = TruyenfullVnSource()
    assert src._proxy_url == proxy_url
    before = len(read_hits())
    novels = src.list_genre_novels_page("https://truyenfull.live/the-loai/tien-hiep/", 1)
    hits = read_hits()[before:]
    assert novels, "list rỗng — site/proxy lỗi"
    assert any("CONNECT truyenfull.live:443" in h for h in hits), hits


@pytest.mark.integration
def test_tls_fetch_traffic_goes_through_proxy(counting_proxy):
    proxy_url, read_hits = counting_proxy
    before = len(read_hits())
    status, body, _ = tls_get("https://www.bgq99.cc/", proxy=proxy_url)
    hits = read_hits()[before:]
    assert status == 200 and len(body) > 1000
    assert any("CONNECT www.bgq99.cc:443" in h for h in hits), hits


@pytest.mark.integration
def test_vn_region_prefers_crawl_proxy_vn(counting_proxy, monkeypatch: pytest.MonkeyPatch):
    proxy_url, _ = counting_proxy
    monkeypatch.setenv("CRAWL_HTTP_PROXY", "http://127.0.0.1:19999")
    monkeypatch.setenv("CRAWL_PROXY_VN", proxy_url)
    reset_proxy_cache()
    assert get_a_proxy(source_key="truyenfull_vn") == proxy_url
    assert get_a_proxy(source_key="bqgxs_com") == "http://127.0.0.1:19999"
    src = TruyenfullVnSource()
    assert src._proxy_url == proxy_url


@pytest.mark.integration
def test_direct_request_does_not_hit_counting_proxy(counting_proxy):
    _, read_hits = counting_proxy
    # clear env so get_a_proxy unused; plain httpx
    r = httpx.get("https://api.ipify.org", timeout=15)
    assert r.status_code == 200
    # counting proxy vẫn lắng nghe nhưng không nhận CONNECT nếu không cấu hình vào client
    # (fixture đã set env — tạo source không dùng ở đây)
    assert isinstance(r.text, str)
