"""Test tích hợp: gọi thật qua FastAPI TestClient, chạy thật use case +
repository + SQLite test DB — chỉ có source là `demo_local` (đọc file cục
bộ) nên không cần mạng, không cần mock. Đây là bản test-hoá của các lần
`curl` thủ công đã làm khi build tính năng."""
import time


def _get_genre(client, genre_id: int) -> dict:
    genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 50}).json()["items"]
    return next(g for g in genres if g["id"] == genre_id)


def _wait_for_run(client, genre_id: int, timeout: float = 2.0) -> dict:
    """`/run-now` chạy NỀN (mục 9.2) -> đợi tới khi xong thay vì đọc response
    ngay (response chỉ trả trạng thái "running" lúc vừa bấm)."""
    deadline = time.time() + timeout
    genre = _get_genre(client, genre_id)
    while genre["last_run_status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        genre = _get_genre(client, genre_id)
    assert genre["last_run_status"] != "running", f"Genre {genre_id} vẫn 'running' sau {timeout}s"
    return genre


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_genres_seeded_on_startup(client):
    r = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 50})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert all(g["source_key"] == "demo_local" for g in data["items"])


def test_settings_seeded_and_patchable(client):
    r = client.get("/api/crawl/settings")
    assert r.status_code == 200
    # Setting toàn cục (không thuộc site nào) — mục 9.0.
    assert r.json()["values"]["crawl.max_chapters_translate_per_day"] == 20
    # Setting RIÊNG từng site — seed sẵn theo key "crawl.<key>.<source_key>"
    # cho mọi site đăng ký (kể cả demo_local, dùng nội bộ) lúc khởi động.
    assert r.json()["values"]["crawl.scan_window.demo_local"] == 5

    r = client.patch("/api/crawl/settings", json={"values": {"crawl.scan_window.demo_local": 9}})
    assert r.status_code == 200
    assert r.json()["values"]["crawl.scan_window.demo_local"] == 9

    # Trả lại giá trị cũ để không ảnh hưởng test khác chạy sau.
    client.patch("/api/crawl/settings", json={"values": {"crawl.scan_window.demo_local": 5}})


def _get_demo_genre_id(client) -> int:
    genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 50}).json()["items"]
    return genres[0]["id"]


def test_full_crawl_pipeline_via_demo_source(client):
    genre_id = _get_demo_genre_id(client)

    r = client.post(f"/api/crawl/genres/{genre_id}/run-now")
    assert r.status_code == 202
    assert r.json()["last_run_status"] == "running"

    genre = _wait_for_run(client, genre_id)
    assert genre["last_run_status"] == "done"
    assert genre["last_run_discovered"] == 1
    assert genre["last_run_errors"] == 0

    novels = client.get("/api/crawl/novels").json()["items"]
    demo_novel = next(n for n in novels if n["source_key"] == "demo_local")
    assert demo_novel["lifecycle_status"] == "fully_crawled"
    assert demo_novel["total_chapters"] == 2

    chapters = client.get(
        f"/api/crawl/novels/{demo_novel['id']}/chapters", params={"limit": 50}
    ).json()
    assert chapters["total"] == 2
    assert all(c["status"] == "crawled" for c in chapters["items"])


def test_running_same_genre_twice_does_not_duplicate(client):
    genre_id = _get_demo_genre_id(client)
    client.post(f"/api/crawl/genres/{genre_id}/run-now")  # lần 1 (idempotent nếu đã chạy ở test trước)
    _wait_for_run(client, genre_id)

    client.post(f"/api/crawl/genres/{genre_id}/run-now")  # lần 2
    genre = _wait_for_run(client, genre_id)
    assert genre["last_run_discovered"] == 0  # đã "discovered" từ trước -> bỏ qua ("Library mode")

    novels = [n for n in client.get("/api/crawl/novels").json()["items"] if n["source_key"] == "demo_local"]
    assert len(novels) == 1  # không tạo trùng


def test_dry_run_content_mode(client):
    r = client.post(
        "/api/crawl/dry-run",
        json={"source_key": "demo_local", "url": _demo_chapter_path(), "mode": "content"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["validation_passed"] is True


def _demo_chapter_path() -> str:
    from pathlib import Path

    fixtures_dir = Path(__file__).resolve().parent.parent / "data" / "fixtures"
    return str(fixtures_dir / "demo_novel" / "chapter_001.txt")


def test_add_novel_via_chapter_url_derives_novel_url(client):
    """Tính năng 'crawl ở URL chương chỉ định' — dán thẳng URL 1 CHƯƠNG
    (không phải trang mục lục), hệ thống tự suy ra mục lục qua
    SourcePort.derive_novel_url() rồi crawl toàn bộ như bình thường.
    Dùng thư mục fixture RIÊNG (không phải demo_novel) để không đụng các
    test khác đang thao tác trên demo_novel."""
    import time
    from pathlib import Path

    novel_dir = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "derive_test_novel"
    chapter_url = str(novel_dir / "chapter_001.txt")

    r = client.post(
        "/api/crawl/novels",
        json={"source_key": "demo_local", "url": chapter_url},
    )
    assert r.status_code == 202
    result = r.json()
    assert result["success"] is True
    novel_id = result["novel_id"]

    # Crawl chạy nền — đợi lifecycle fully_crawled (demo fixture nhanh).
    added = None
    for _ in range(100):
        novels = client.get("/api/crawl/novels").json()["items"]
        added = next((n for n in novels if n["id"] == novel_id), None)
        if added and added["lifecycle_status"] == "fully_crawled":
            break
        time.sleep(0.05)
    assert added is not None
    assert added["is_manual"] is True
    assert added["lifecycle_status"] == "fully_crawled"
    assert added["source_url"] == str(novel_dir)

    # Thêm lại đúng chương đó lần nữa -> phải báo "đã có", không tạo trùng
    # (kiểm tra "existing" cũng áp dụng cho URL đã suy ra, không chỉ URL gốc).
    r2 = client.post(
        "/api/crawl/novels",
        json={"source_key": "demo_local", "url": chapter_url},
    )
    assert r2.status_code == 200
    assert r2.json()["success"] is False
