"""Handoff payload cho translate-service — Phase 0 contract."""


def test_translate_handoff_404(client):
    r = client.get("/api/crawl/novels/999999/translate-handoff")
    assert r.status_code == 404


def test_translate_handoff_demo_novel_if_any(client):
    """Smoke: endpoint tồn tại; nếu chưa có novel thì 404/400 đều OK schema."""
    listed = client.get("/api/crawl/novels?limit=1").json()
    if listed.get("total", 0) == 0:
        r = client.get("/api/crawl/novels/1/translate-handoff")
        assert r.status_code in (400, 404)
        return
    novel_id = listed["items"][0]["id"]
    r = client.get(f"/api/crawl/novels/{novel_id}/translate-handoff")
    if r.status_code == 400:
        detail = str(r.json().get("detail", "")).lower()
        assert "chương" in detail or "chapter" in detail
        return
    assert r.status_code == 200
    data = r.json()
    assert data["external_id"] == f"crawl:novel:{novel_id}"
    assert "chapters" in data
    assert data["lang_tgt_hint"] == "vi"
    if data["chapters"]:
        ch = data["chapters"][0]
        assert "fingerprint" in ch and "text" in ch and "crawl_chapter_id" in ch
