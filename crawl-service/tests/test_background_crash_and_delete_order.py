"""Thread nền chết không để kẹt RUNNING/CRAWLING; xóa truyện không mất chữ khi DB lỗi."""
from pathlib import Path

from crawl.api import routers
from crawl.application.use_cases import DeleteNovelUseCase, RawTextStorage
from crawl.domain.entities import Chapter, ChapterStatus, GenreRunStatus, Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal


def _boom(*_args, **_kwargs):
    raise RuntimeError("hỏng trước khi quét")


def test_genre_thread_crash_marks_error(client, monkeypatch):
    db = SessionLocal()
    try:
        repo = SqlAlchemyGenreRepository(db)
        genre = repo.get_or_create("demo_local", "crash-genre", "Crash", "http://demo.local/g")
        genre.mark_run_started()
        repo.update_run_state(genre)
        genre_id = genre.id
    finally:
        db.close()

    monkeypatch.setattr(routers, "get_crawl_genre_use_case", _boom)
    routers._run_genre_in_background(genre_id, f"genre-run:{genre_id}")

    db = SessionLocal()
    try:
        genre = SqlAlchemyGenreRepository(db).get_by_id(genre_id)
        assert genre.last_run_status == GenreRunStatus.ERROR
        assert genre.last_run_finished_at is not None
    finally:
        db.close()


def test_cancel_orphan_running_genre_clears_state(client):
    from platform_.locks import release, try_acquire

    db = SessionLocal()
    try:
        repo = SqlAlchemyGenreRepository(db)
        genre = repo.get_or_create("demo_local", "orphan-genre", "Orphan", "http://demo.local/o")
        genre.mark_run_started()
        repo.update_run_state(genre)
        genre_id = genre.id
    finally:
        db.close()

    lock_key = f"genre-run:{genre_id}"
    assert try_acquire(lock_key)
    try:
        held = client.post(f"/api/crawl/genres/{genre_id}/cancel")
        assert held.status_code == 200
        assert held.json()["last_run_status"] == "running"
    finally:
        release(lock_key)

    orphan = client.post(f"/api/crawl/genres/{genre_id}/cancel")
    assert orphan.status_code == 200
    assert orphan.json()["last_run_status"] == "cancelled"


def test_novel_thread_crash_marks_error(client, monkeypatch):
    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(
                id=None,
                title="Crash novel",
                source_key="demo_local",
                source_url="http://demo.local/crash-novel",
                lifecycle_status=NovelLifecycle.CRAWLING,
            )
        )
        novel_id = novel.id
    finally:
        db.close()

    monkeypatch.setattr(routers, "get_crawl_novel_use_case", _boom)
    routers._crawl_novel_in_background(novel_id, f"crawl-novel:{novel_id}")

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
        assert novel.lifecycle_status == NovelLifecycle.ERROR
        assert "hỏng trước khi quét" in (novel.error_message or "")
    finally:
        db.close()


def test_delete_keeps_files_when_db_delete_fails(client):
    db = SessionLocal()
    storage = RawTextStorage(config.raw_dir)
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Keep text",
                source_key="demo_local",
                source_url="http://demo.local/keep-text",
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        path = storage.save(novel.id, 1, "chương còn phải giữ nguyên.\n")
        chapter_repo.add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=1,
                title="Ch 1",
                source_url="http://demo.local/keep-1",
                raw_path=path,
                status=ChapterStatus.CRAWLED,
            )
        )

        class FailingDelete(SqlAlchemyNovelRepository):
            def delete(self, novel_id: int) -> bool:
                return False

        result = DeleteNovelUseCase(FailingDelete(db), chapter_repo, storage).execute(novel.id)
        assert result.success is False
        assert Path(path).is_file()
    finally:
        db.close()
