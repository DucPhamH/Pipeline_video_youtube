"""Zhihu adapter — URL normalize / derive / sign (không cần mạng)."""
from crawl.infrastructure.sources.zhihu_com_source import ZhihuComSource
from crawl.infrastructure.sources.zhihu_sign import generate_zhihu_sign


def test_derive_and_normalize_urls():
    src = ZhihuComSource()
    assert (
        src.derive_novel_url(
            "https://www.zhihu.com/market/paid_column/123/section/456"
        )
        == "https://www.zhihu.com/market/paid_column/123"
    )
    assert (
        src.derive_novel_url("https://story.zhihu.com/manuscript/paid_column/99/88")
        == "https://www.zhihu.com/market/paid_column/99"
    )
    assert (
        src._normalize_url("https://story.zhihu.com/manuscript/paid_column/11")
        == "https://www.zhihu.com/market/paid_column/11"
    )


def test_sign_requires_d_c0():
    assert generate_zhihu_sign("https://www.zhihu.com/", {}) == {}
    signed = generate_zhihu_sign(
        "https://www.zhihu.com/market/paid_column/1",
        {"d_c0": "x|dummy"},
    )
    assert signed["x-zse-96"].startswith("2.0_")
    assert "x-zst-81" in signed


def test_zhihu_registered_session_required(client):
    r = client.get("/api/crawl/sites", params={"search": "zhihu", "limit": 20})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(s["key"] == "zhihu_com" for s in items)
    zh = next(s for s in items if s["key"] == "zhihu_com")
    assert zh["access_kind"] == "session_required"
    assert zh["region"] == "china"
