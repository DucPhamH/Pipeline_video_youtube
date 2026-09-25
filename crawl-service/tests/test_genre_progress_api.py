"""API tiến độ live genre scan."""
from crawl.application.progress import CrawlProgress
from platform_.run_progress import clear, publish


def test_genre_progress_endpoint_returns_snapshot(client):
    publish(
        CrawlProgress(
            task_id="genre:1",
            kind="genre",
            label="demo_local/demo",
            phase="crawling",
            page=1,
            max_pages=3,
            discovered=2,
            rejected=1,
            errors=0,
            scan_window=5,
            novel_title="短編テスト",
            chapter_index=3,
            chapter_total=7,
            message="第3話",
        )
    )
    try:
        # demo genre id thường là 1 sau seed — nếu không có, skip mềm
        genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 5}).json()
        items = genres.get("items") or []
        if not items:
            return
        gid = items[0]["id"]
        publish(
            CrawlProgress(
                task_id=f"genre:{gid}",
                kind="genre",
                label="demo_local/demo",
                phase="crawling",
                page=2,
                max_pages=3,
                discovered=1,
                rejected=0,
                scan_window=5,
                novel_title="Demo",
                chapter_index=1,
                chapter_total=2,
            )
        )
        r = client.get(f"/api/crawl/genres/{gid}/progress")
        assert r.status_code == 200
        body = r.json()
        assert body["progress"] is not None
        assert body["progress"]["phase"] == "crawling"
        assert body["progress"]["discovered"] == 1
        assert body["progress"]["novel_title"] == "Demo"
    finally:
        clear("genre:1")
        if items:
            clear(f"genre:{items[0]['id']}")


def test_genre_progress_null_when_idle(client):
    genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 5}).json()
    items = genres.get("items") or []
    if not items:
        return
    gid = items[0]["id"]
    clear(f"genre:{gid}")
    r = client.get(f"/api/crawl/genres/{gid}/progress")
    assert r.status_code == 200
    assert r.json()["progress"] is None
