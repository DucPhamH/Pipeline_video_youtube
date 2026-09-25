"""Verify `GET /novels/{id}/chapters` phân trang + lọc."""
from crawl.domain.entities import Chapter, ChapterStatus, Novel
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)


def _seed_novel_with_chapters(db, count: int) -> int:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    novel = novel_repo.add(
        Novel(
            id=None,
            title="Test novel chapters",
            source_key="pg_chapter_site",
            source_url=f"http://x/pg-chapters-{count}",
        )
    )
    for i in range(1, count + 1):
        chapter_repo.add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=i,
                title=f"Chương {i}",
                source_url=f"http://x/ch/{i}",
                status=ChapterStatus.CRAWLED if i % 2 == 0 else ChapterStatus.FAILED,
                reviewed=i == 2,
            )
        )
    return novel.id


def test_list_chapters_paginates(client):  # noqa: ARG001
    db = _db()
    try:
        novel_id = _seed_novel_with_chapters(db, 5)

        page1 = client.get(
            f"/api/crawl/novels/{novel_id}/chapters",
            params={"limit": 2, "offset": 0},
        ).json()
        page2 = client.get(
            f"/api/crawl/novels/{novel_id}/chapters",
            params={"limit": 2, "offset": 2},
        ).json()

        assert page1["total"] == page2["total"] == 5
        assert len(page1["items"]) == 2
        assert page1["items"][0]["chapter_index"] == 1
        assert page2["items"][0]["chapter_index"] == 3
    finally:
        db.close()


def test_list_chapters_filters_by_status_and_reviewed(client):  # noqa: ARG001
    db = _db()
    try:
        novel_id = _seed_novel_with_chapters(db, 4)

        crawled = client.get(
            f"/api/crawl/novels/{novel_id}/chapters",
            params={"status": "crawled", "limit": 50},
        ).json()
        reviewed = client.get(
            f"/api/crawl/novels/{novel_id}/chapters",
            params={"reviewed": True, "limit": 50},
        ).json()
        search = client.get(
            f"/api/crawl/novels/{novel_id}/chapters",
            params={"search": "Chương 3", "limit": 50},
        ).json()

        assert crawled["total"] == 2
        assert reviewed["total"] == 1
        assert reviewed["items"][0]["chapter_index"] == 2
        assert search["total"] == 1
        assert search["items"][0]["chapter_index"] == 3
    finally:
        db.close()


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
