"""Verify tính năng review/sửa nội dung chương đã crawl — GET để xem,
PUT để lưu bản đã sửa, đánh dấu `reviewed`."""
import time


def _demo_genres(client) -> list[dict]:
    params = {"source_key": "demo_local", "limit": 50}
    return client.get("/api/crawl/genres", params=params).json()["items"]


def _wait_for_run(client, genre_id: int, timeout: float = 2.0) -> None:
    """`/run-now` chạy NỀN (mục 9.2) -> đợi tới khi xong thay vì đọc kết
    quả ngay sau khi bấm."""
    deadline = time.time() + timeout
    genres = _demo_genres(client)
    genre = next(g for g in genres if g["id"] == genre_id)
    while genre["last_run_status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        genres = _demo_genres(client)
        genre = next(g for g in genres if g["id"] == genre_id)


def _crawl_demo_and_get_first_chapter_id(client) -> int:
    genres = _demo_genres(client)
    genre_id = genres[0]["id"]
    client.post(f"/api/crawl/genres/{genre_id}/run-now")
    _wait_for_run(client, genre_id)

    novels = client.get("/api/crawl/novels").json()["items"]
    demo_novel = next(n for n in novels if n["source_key"] == "demo_local")
    chapters = client.get(
        f"/api/crawl/novels/{demo_novel['id']}/chapters", params={"limit": 50}
    ).json()["items"]
    return chapters[0]["id"]


def test_get_chapter_content_returns_raw_text(client):
    chapter_id = _crawl_demo_and_get_first_chapter_id(client)

    r = client.get(f"/api/crawl/chapters/{chapter_id}/content")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["reviewed"] is False  # chưa ai sửa
    assert "山中初遇" in data["content"] or len(data["content"]) > 0


def test_update_chapter_content_saves_and_marks_reviewed(client):
    chapter_id = _crawl_demo_and_get_first_chapter_id(client)

    new_text = "第一章 山中初遇（编辑版）\n\n这是审阅后修改过的章节内容,用于测试保存功能。"
    r = client.put(f"/api/crawl/chapters/{chapter_id}/content", json={"content": new_text})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["reviewed"] is True
    assert data["content"] == new_text

    # Đọc lại xác nhận đã lưu thật (không chỉ trả về trong response) và
    # reviewed vẫn giữ nguyên True sau khi tách request khác.
    r2 = client.get(f"/api/crawl/chapters/{chapter_id}/content")
    data2 = r2.json()
    assert data2["content"] == new_text
    assert data2["reviewed"] is True

    # Chapter list ở trang chi tiết truyện cũng phải phản ánh reviewed=True.
    novels = client.get("/api/crawl/novels").json()["items"]
    demo_novel = next(n for n in novels if n["source_key"] == "demo_local")
    chapters = client.get(
        f"/api/crawl/novels/{demo_novel['id']}/chapters", params={"limit": 50}
    ).json()["items"]
    chapter_row = next(c for c in chapters if c["id"] == chapter_id)
    assert chapter_row["reviewed"] is True


def test_get_chapter_content_404_for_missing_chapter(client):
    r = client.get("/api/crawl/chapters/999999/content")
    assert r.status_code == 404


def test_update_chapter_content_rejects_empty_content(client):
    chapter_id = _crawl_demo_and_get_first_chapter_id(client)

    r = client.put(f"/api/crawl/chapters/{chapter_id}/content", json={"content": "   "})
    assert r.status_code == 400
