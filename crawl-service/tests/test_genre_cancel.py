"""Hủy lượt quét genre đang chạy."""
import time

from pathlib import Path

from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)
from platform_.db import SessionLocal
from platform_.run_cancel import begin_run, end_run, is_cancelled, request_cancel


def test_run_cancel_flag_lifecycle():
    begin_run(99)
    assert not is_cancelled(99)
    assert request_cancel(99)
    assert is_cancelled(99)
    end_run(99)
    assert not is_cancelled(99)


def test_cancel_before_begin_is_honored():
    """FE có thể bấm Dừng trước khi thread gọi begin_run."""
    request_cancel(42)
    begin_run(42)
    assert is_cancelled(42)
    end_run(42)


def test_cancel_genre_endpoint_requires_running(client):
    genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 5}).json()
    items = genres.get("items") or []
    if not items:
        return
    gid = items[0]["id"]
    r = client.post(f"/api/crawl/genres/{gid}/cancel")
    assert r.status_code == 409


class _SlowListSource:
    key = "fake_cancel_test"
    name = "slow list for cancel"

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        # Chờ cancel cờ — mô phỏng HTTP chậm
        deadline = time.time() + 5
        while time.time() < deadline:
            # genre id gắn qua begin_run trong execute; đợi cờ bất kỳ set?
            # Không biết id — sleep ngắn rồi return, test sẽ cancel từ ngoài.
            time.sleep(0.05)
            break
        if page != 1:
            return []
        return [
            NovelRef(title="Truyện chậm", url=f"{genre_list_url}/n1", latest_chapter_title="完結")
        ]

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=1, title="第一章", url="ch1"),
            ChapterRef(index=2, title="第二章 大结局", url="ch2"),
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        time.sleep(0.2)
        return "他走在路上，看见前方有一道光，心里很害怕，不知道该怎么办。" * 5

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def test_execute_marks_cancelled_when_flag_set(client):  # noqa: ARG001
    db = SessionLocal()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        source = _SlowListSource()
        crawl_novel = CrawlNovelUseCase(
            novel_repo=novel_repo,
            chapter_repo=chapter_repo,
            storage=RawTextStorage(Path("/tmp/genre_cancel_test_raw")),
            source_resolver=lambda _key: source,
        )
        use_case = CrawlGenreUseCase(
            novel_repo=novel_repo,
            genre_repo=genre_repo,
            crawl_novel_use_case=crawl_novel,
            source_resolver=lambda _key: source,
            get_scan_window=lambda _k: 5,
            get_max_chapters_per_story=lambda _k: 50,
        )
        genre = genre_repo.get_or_create(
            source_key="fake_cancel_test",
            genre_key="g_cancel",
            label="Cancel",
            list_url="http://x/cancel-list",
        )
        genre.mark_run_started()
        genre_repo.update(genre)

        # Cancel ngay trước khi scan bắt đầu vòng ứng viên
        request_cancel(genre.id)
        result = use_case.execute(genre.id)

        assert result.cancelled is True
        saved = genre_repo.get_by_id(genre.id)
        assert saved.last_run_status == "cancelled"
        assert saved.last_run_finished_at is not None
        assert "dừng" in (saved.last_run_messages or "").lower()
    finally:
        db.close()


def test_cancel_api_while_running(client):
    genres = client.get("/api/crawl/genres", params={"source_key": "demo_local", "limit": 5}).json()
    items = genres.get("items") or []
    if not items:
        return
    gid = items[0]["id"]
    client.patch(f"/api/crawl/genres/{gid}", json={"enabled": True})

    r = client.post(f"/api/crawl/genres/{gid}/run-now")
    assert r.status_code == 202

    time.sleep(0.02)
    cr = client.post(f"/api/crawl/genres/{gid}/cancel")
    # 200 nếu còn running; 409 nếu đã xong trước cancel
    assert cr.status_code in (200, 409)

    deadline = time.time() + 30
    status = "running"
    while time.time() < deadline:
        listed = client.get(
            "/api/crawl/genres", params={"source_key": "demo_local", "limit": 50}
        ).json()
        g = next((x for x in listed["items"] if x["id"] == gid), None)
        assert g is not None
        status = g["last_run_status"]
        if status != "running":
            break
        time.sleep(0.1)

    assert status in ("cancelled", "done", "error"), f"stuck running? got {status}"
