"""Tính năng thật 17/9/2026: "mỗi chương lỗi sẽ có nút crawl lại" — retry
ĐÚNG 1 chương, không đụng chương khác/không crawl lại cả truyện (khác
`POST /novels/{id}/retry`, mục 9.2b)."""
from pathlib import Path

from crawl.application.use_cases import RawTextStorage, RetryChapterUseCase
from crawl.domain.entities import Chapter, ChapterStatus, Novel, NovelLifecycle
from crawl.domain.ports import ScrapeError
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)

_GOOD_TEXT = "这是一段用于测试的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3


class _FlipSource:
    """Chương `bad_index` fail lần đầu (VIP/lỗi mạng giả lập), sau khi
    `unlock()` được gọi thì thành công — mô phỏng "cập nhật cookie rồi bấm
    Crawl lại"."""

    key = "flip_test"
    name = "flip test source"

    def __init__(self, bad_index: int):
        self.bad_index = bad_index
        self.unlocked = False

    def unlock(self) -> None:
        self.unlocked = True

    def fetch_chapter_content(self, chapter_url: str) -> str:
        index = int(chapter_url.rsplit("#", 1)[1])
        if index == self.bad_index and not self.unlocked:
            raise ScrapeError(f"[flip_test] Chương VIP — cần cookie đăng nhập tại {chapter_url}")
        return _GOOD_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _use_case(db, source) -> RetryChapterUseCase:
    return RetryChapterUseCase(
        chapter_repo=SqlAlchemyChapterRepository(db),
        novel_repo=SqlAlchemyNovelRepository(db),
        storage=RawTextStorage(Path("/tmp/chapter_retry_test_raw")),
        source_resolver=lambda _key: source,
    )


def _seed_novel_with_chapters(
    db, *, total: int, missing: set[int], lifecycle: NovelLifecycle, source_url: str,
) -> Novel:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    novel = novel_repo.add(
        Novel(
            id=None,
            title="Retry chapter test novel",
            source_key="flip_test",
            source_url=source_url,
            total_chapters=total,
            lifecycle_status=lifecycle,
            error_message=f"Thiếu {len(missing)} chương (vd {min(missing)}) — VIP/lỗi nội dung; "
            "cập nhật cookie rồi Retry để lấy nốt",
        )
    )
    for i in range(1, total + 1):
        if i in missing:
            continue
        ch = Chapter(id=None, novel_id=novel.id, chapter_index=i, title=f"Ch {i}", source_url=f"u{i}#{i}")
        ch.status = ChapterStatus.CRAWLED
        ch.raw_path = f"/tmp/chapter_retry_test_raw/{novel.id}/{i:04d}.txt"
        chapter_repo.add(ch)
    return novel


def test_retry_chapter_succeeds_after_source_unlocked(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        novel = novel_repo.add(
            Novel(id=None, title="N", source_key="flip_test", source_url="u-single", total_chapters=3)
        )
        failed = Chapter(id=None, novel_id=novel.id, chapter_index=2, title="Ch 2", source_url="u#2")
        failed.mark_failed("[flip_test] Chương VIP — cần cookie đăng nhập tại u#2")
        failed = chapter_repo.add(failed)

        source = _FlipSource(bad_index=2)
        use_case = _use_case(db, source)

        first = use_case.execute(failed.id)
        assert first.success is False
        assert first.status == "failed"

        source.unlock()
        second = use_case.execute(failed.id)
        assert second.success is True
        assert second.status == "crawled"

        chapter_after = chapter_repo.get_by_id(failed.id)
        assert chapter_after.status.value == "crawled"
        assert chapter_after.error_message is None
        assert chapter_after.raw_path is not None
        assert Path(chapter_after.raw_path).read_text(encoding="utf-8") == _GOOD_TEXT
    finally:
        db.close()


def test_retry_chapter_completes_novel_when_last_gap_filled(client):  # noqa: ARG001
    """Chương vừa retry là chương THIẾU CUỐI CÙNG -> novel tự chuyển đủ,
    xoá ghi chú "Thiếu N chương" (mục 9.2b), không cần bấm "Thử lại" cả
    truyện thêm lần nữa."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = _seed_novel_with_chapters(
            db, total=3, missing={2}, lifecycle=NovelLifecycle.FULLY_CRAWLED,
            source_url="u-retry-chapter-test-complete",
        )
        chapter_repo = SqlAlchemyChapterRepository(db)
        gap = Chapter(id=None, novel_id=novel.id, chapter_index=2, title="Ch 2", source_url="u2#2")
        gap.mark_failed("[flip_test] Chương VIP — cần cookie đăng nhập tại u2#2")
        gap = chapter_repo.add(gap)

        source = _FlipSource(bad_index=2)
        source.unlock()  # đã cập nhật cookie trước khi bấm Crawl lại
        use_case = _use_case(db, source)

        result = use_case.execute(gap.id)
        assert result.success is True
        assert result.novel_completed is True

        novel_after = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        assert novel_after.lifecycle_status == NovelLifecycle.FULLY_CRAWLED
        assert novel_after.error_message is None
    finally:
        db.close()


def test_retry_chapter_not_yet_completes_novel_when_gap_remains(client):  # noqa: ARG001
    """Còn thiếu chương KHÁC -> chưa được coi là đủ, giữ nguyên ghi chú."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = _seed_novel_with_chapters(
            db, total=4, missing={2, 4}, lifecycle=NovelLifecycle.FULLY_CRAWLED,
            source_url="u-retry-chapter-test-partial",
        )
        chapter_repo = SqlAlchemyChapterRepository(db)
        gap = Chapter(id=None, novel_id=novel.id, chapter_index=2, title="Ch 2", source_url="u2#2")
        gap.mark_failed("lỗi cũ")
        gap = chapter_repo.add(gap)

        source = _FlipSource(bad_index=2)
        source.unlock()
        result = _use_case(db, source).execute(gap.id)
        assert result.success is True
        assert result.novel_completed is False  # ch 4 vẫn còn thiếu

        novel_after = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        assert novel_after.error_message is not None  # ghi chú giữ nguyên
    finally:
        db.close()


def test_retry_chapter_404_for_missing_chapter(client):
    r = client.post("/api/crawl/chapters/999999/retry")
    assert r.status_code == 404


def test_retry_chapter_endpoint_returns_success_false_without_http_error(client):  # noqa: ARG001
    """Fetch lại vẫn lỗi (vd cookie vẫn chưa cập nhật) — đây là kết quả
    BÌNH THƯỜNG cần FE hiện inline, không phải lỗi hệ thống (200, không
    404/500) — khớp cách `POST /novels` xử lý lỗi "biết trước". Cố tình
    dùng `source_key` KHÔNG có thật (không phải "demo_local") — DB test
    session-scoped dùng chung giữa mọi file, "demo_local" bị nhiều test
    khác (vd test_chapter_review.py) lấy "novel demo_local đầu tiên" theo
    kiểu lỏng lẻo, tạo thêm 1 novel demo_local giả ở đây từng làm gãy test
    đó (bug tự gây ra, phát hiện + sửa ngay 17/9/2026)."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        novel = novel_repo.add(
            Novel(id=None, title="N2", source_key="no_such_source_for_retry_test", source_url="u-still-bad")
        )
        failed = Chapter(id=None, novel_id=novel.id, chapter_index=1, title="Ch 1", source_url="u1#1")
        failed.mark_failed("lỗi cũ")
        failed = chapter_repo.add(failed)
    finally:
        db.close()

    r = client.post(f"/api/crawl/chapters/{failed.id}/retry")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is False
    assert data["status"] == "failed"
    assert "Nguồn không còn hỗ trợ" in (data["error"] or "")
