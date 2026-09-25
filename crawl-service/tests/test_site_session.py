"""Cookie/session do user dán vào — parse + lưu settings."""
from platform_.session_cookies import cookie_header_from_dict, parse_cookie_header


def test_parse_cookie_header_basic():
    assert parse_cookie_header("a=1; b=two") == {"a": "1", "b": "two"}
    assert parse_cookie_header("  ") == {}
    assert parse_cookie_header(None) == {}


def test_cookie_roundtrip_dict():
    raw = cookie_header_from_dict({"sid": "abc", "token": "x=y"})
    assert parse_cookie_header(raw)["sid"] == "abc"
    assert parse_cookie_header(raw)["token"] == "x=y"


def test_site_session_api_save_and_read(client):
    r = client.put(
        "/api/crawl/sites/bqgxs_com/session",
        json={"cookie_header": "uid=42; token=hello"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert set(data["cookie_names"]) == {"uid", "token"}

    got = client.get("/api/crawl/sites/bqgxs_com/session").json()
    assert "uid=42" in got["cookie_header"]

    cleared = client.put("/api/crawl/sites/bqgxs_com/session", json={"cookie_header": ""}).json()
    assert cleared["configured"] is False


def test_site_session_unknown_source_404(client):
    r = client.get("/api/crawl/sites/no_such_site/session")
    assert r.status_code == 404


def test_zhihu_session_requires_z_c0_and_d_c0(client):
    incomplete = client.put(
        "/api/crawl/sites/zhihu_com/session",
        json={"cookie_header": "z_c0=only_login; other=1"},
    ).json()
    assert incomplete["configured"] is False
    assert "d_c0" in incomplete["missing_required_cookies"]
    assert set(incomplete["required_cookies"]) == {"z_c0", "d_c0"}

    complete = client.put(
        "/api/crawl/sites/zhihu_com/session",
        json={"cookie_header": "z_c0=ok; d_c0=sign_me"},
    ).json()
    assert complete["configured"] is True
    assert complete["missing_required_cookies"] == []

    probe = client.post("/api/crawl/sites/zhihu_com/session/probe").json()
    # Có đủ tên cookie thì probe mới đi mạng (có thể fail mạng) — không còn báo thiếu d_c0
    assert "d_c0" not in (probe.get("missing_required_cookies") or [])
