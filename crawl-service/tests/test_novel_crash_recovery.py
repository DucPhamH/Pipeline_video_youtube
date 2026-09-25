"""Bug thật (17/9/2026, cùng dạng với genre — xem test_genre_run_status.py::
test_recover_interrupted_genre_runs_resets_stuck_running_status): server
restart/crash giữa lúc 1 novel đang `lifecycle_status="crawling"` -> thread
nền + khoá `crawl-novel:{id}` của tiến trình CŨ chết theo, novel kẹt
"crawling" MÃI MÃI. Nặng hơn cấp genre: "Thử lại" (`POST /novels/{id}/retry`)
CHỈ nhận truyện đang error/fully_crawled — "crawling" không nằm trong 2
trạng thái đó nên không có cách nào tự bấm lại được qua UI."""
from crawl.domain.entities import Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository


def test_recover_interrupted_novel_crawls_resets_stuck_crawling_status(client):  # noqa: ARG001
    from main import _recover_interrupted_novel_crawls

    db = _db()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        stuck = novel_repo.add(
            Novel(
                id=None,
                title="Stuck novel",
                source_key="fake_recover_test",
                source_url="http://x/stuck-novel",
                lifecycle_status=NovelLifecycle.CRAWLING,
                last_chapter_index=2,
                total_chapters=5,
            )
        )
        # Không liên quan — không được đụng vào.
        fully_crawled = novel_repo.add(
            Novel(
                id=None,
                title="Done novel",
                source_key="fake_recover_test",
                source_url="http://x/done-novel",
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        discovered = novel_repo.add(
            Novel(
                id=None,
                title="Fresh novel",
                source_key="fake_recover_test",
                source_url="http://x/fresh-novel",
                lifecycle_status=NovelLifecycle.DISCOVERED,
            )
        )

        _recover_interrupted_novel_crawls(novel_repo)

        stuck_after = novel_repo.get_by_id(stuck.id)
        assert stuck_after.lifecycle_status == NovelLifecycle.ERROR
        assert "gián đoạn" in (stuck_after.error_message or "")
        # last_chapter_index KHÔNG bị đụng — resume vẫn tiếp tục đúng chỗ dở.
        assert stuck_after.last_chapter_index == 2

        assert novel_repo.get_by_id(fully_crawled.id).lifecycle_status == NovelLifecycle.FULLY_CRAWLED
        assert novel_repo.get_by_id(discovered.id).lifecycle_status == NovelLifecycle.DISCOVERED
    finally:
        db.close()


def test_recovered_novel_can_be_retried_through_api(client):
    """Sau khi phục hồi về "error" — endpoint /retry (mục 9.2b) phải nhận
    lại được ngay, không còn kẹt vĩnh viễn."""
    from main import _recover_interrupted_novel_crawls

    db = _db()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        stuck = novel_repo.add(
            Novel(
                id=None,
                title="Stuck novel 2",
                source_key="demo_local",
                source_url="http://x/stuck-novel-2",
                lifecycle_status=NovelLifecycle.CRAWLING,
            )
        )
        _recover_interrupted_novel_crawls(novel_repo)
    finally:
        db.close()

    r = client.post(f"/api/crawl/novels/{stuck.id}/retry")
    assert r.status_code == 202, r.text


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
