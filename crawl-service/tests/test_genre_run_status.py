"""Verify Genre.last_run_* được LƯU LẠI đúng (không chỉ trả về response) —
đây là phần cốt lõi giải quyết vấn đề "bấm Quét ngay xong không biết đang
chạy hay đã xong" khi /run-now chuyển sang chạy nền (mục 9.2)."""
from pathlib import Path

from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)


class _FakeSource:
    key = "fake_run_status_test"
    name = "fake source for run-status test"

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page != 1:
            return []
        return [
            NovelRef(title="Truyện test", url=f"{genre_list_url}/novel", latest_chapter_title="第二章 大结局")
        ]

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=1, title="第一章", url="ch1"),
            ChapterRef(index=2, title="第二章 大结局", url="ch2"),
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        return "他走在路上，看见前方有一道光，心里很害怕，不知道该怎么办。" * 5

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


class _BoomSource(_FakeSource):
    """Giả lập crash bất ngờ (khác ScrapeError đã được bắt riêng) — dùng để
    xác nhận execute() vẫn lưu được last_run_status="error" thay vì kẹt mãi
    ở "running"."""

    def list_genre_novels_page(self, genre_list_url: str, page: int):
        raise RuntimeError("crash giả lập, không phải ScrapeError")


def _build_use_case(db, source) -> tuple[CrawlGenreUseCase, SqlAlchemyGenreRepository]:
    genre_repo = SqlAlchemyGenreRepository(db)
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    crawl_novel_use_case = CrawlNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(Path("/tmp/genre_run_status_test_raw")),
        source_resolver=lambda _key: source,
    )
    use_case = CrawlGenreUseCase(
        novel_repo=novel_repo,
        genre_repo=genre_repo,
        crawl_novel_use_case=crawl_novel_use_case,
        source_resolver=lambda _key: source,
        get_scan_window=lambda source_key: 5,
        get_max_chapters_per_story=lambda source_key: 50,
    )
    return use_case, genre_repo


def test_execute_marks_run_done_with_result_counts(client):  # noqa: ARG001
    db = _db()
    try:
        use_case, genre_repo = _build_use_case(db, _FakeSource())
        genre = genre_repo.get_or_create(
            source_key="fake_run_status_test", genre_key="g1", label="G1", list_url="http://x/list"
        )
        assert genre.last_run_status == "idle"

        result = use_case.execute(genre.id)

        saved = genre_repo.get_by_id(genre.id)
        assert saved.last_run_status == "done"
        assert saved.last_run_started_at is not None
        assert saved.last_run_finished_at is not None
        assert saved.last_run_discovered == result.discovered == 1
        assert saved.last_run_errors == result.errors == 0
    finally:
        db.close()


def test_execute_marks_run_error_on_unexpected_crash(client):  # noqa: ARG001
    db = _db()
    try:
        use_case, genre_repo = _build_use_case(db, _BoomSource())
        genre = genre_repo.get_or_create(
            source_key="fake_run_status_test", genre_key="g2", label="G2", list_url="http://x/list2"
        )

        use_case.execute(genre.id)

        saved = genre_repo.get_by_id(genre.id)
        # Crash bất ngờ (RuntimeError, không phải ScrapeError đã được bắt
        # riêng trong _scan) vẫn phải kết thúc ở "error", KHÔNG kẹt "running".
        assert saved.last_run_status == "error"
        assert saved.last_run_finished_at is not None
        assert saved.last_run_errors == 1
    finally:
        db.close()


def test_recover_interrupted_genre_runs_resets_stuck_running_status(client):  # noqa: ARG001
    """Bug thật (16/9/2026): server restart/crash giữa lúc 1 genre đang
    "running" -> thread nền của tiến trình CŨ chết theo, không còn ai cập
    nhật nốt -> genre kẹt "running" MÃI MÃI, nút "Quét ngay" ở FE (dựa vào
    đúng field này) bị disable vĩnh viễn, không tự bấm lại được. Verify
    hàm phục hồi lúc khởi động (`main._recover_interrupted_genre_runs`) reset
    đúng các genre đang kẹt về "error", KHÔNG đụng genre khác đang idle/done."""
    from main import _recover_interrupted_genre_runs

    db = _db()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        stuck = genre_repo.get_or_create(
            source_key="fake_recover_test", genre_key="stuck", label="Stuck", list_url="http://x/stuck"
        )
        stuck.mark_run_started()
        genre_repo.update(stuck)
        idle = genre_repo.get_or_create(
            source_key="fake_recover_test", genre_key="idle", label="Idle", list_url="http://x/idle"
        )

        _recover_interrupted_genre_runs(genre_repo)

        stuck_after = genre_repo.get_by_id(stuck.id)
        assert stuck_after.last_run_status == "error"
        assert stuck_after.last_run_finished_at is not None
        assert "gián đoạn" in (stuck_after.last_run_messages or "")

        idle_after = genre_repo.get_by_id(idle.id)
        assert idle_after.last_run_status == "idle"  # không đụng genre không liên quan
    finally:
        db.close()


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
