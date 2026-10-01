"""Verify: khi 1 chương lỗi giữa chừng, bấm lại (retry) phải resume đúng từ
chương lỗi đó — không crawl lại từ đầu, không tạo trùng Chapter cho các
chương đã crawl thành công trước đó."""
from crawl.application.use_cases import CrawlNovelUseCase, RawTextStorage
from crawl.domain.entities import Novel
from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)

_SAMPLE_TEXT = "这是一段用于测试的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3


class FlakyOnceSource:
    """Source giả: chương số `fail_index` lỗi ĐÚNG 1 LẦN đầu tiên, các lần
    gọi sau (retry) thì thành công — mô phỏng lỗi mạng thoáng qua."""

    key = "flaky_test"
    name = "flaky test source"

    def __init__(self, total_chapters: int, fail_index: int):
        self.total_chapters = total_chapters
        self.fail_index = fail_index
        self._fail_used = False

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=i, title=f"Chương {i}", url=f"{novel_url}#{i}")
            for i in range(1, self.total_chapters + 1)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        index = int(chapter_url.rsplit("#", 1)[1])
        if index == self.fail_index and not self._fail_used:
            self._fail_used = True
            raise ScrapeError(f"lỗi giả lập tại chương {index}")
        return _SAMPLE_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _use_case(db, source) -> CrawlNovelUseCase:
    return CrawlNovelUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(__import__("pathlib").Path("/tmp/crawl_resume_test_raw")),
        source_resolver=lambda _key: source,
    )


def test_single_scrape_error_skips_and_continues(client):  # noqa: ARG001
    """1 lỗi fetch lẻ — bỏ qua chương đó, crawl tiếp (mọi site)."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        novel = novel_repo.add(
            Novel(id=None, title="Skip scrape", source_key="flaky_test", source_url="u-skip-scrape")
        )
        source = FlakyOnceSource(total_chapters=5, fail_index=3)
        use_case = _use_case(db, source)
        result = use_case.execute(novel.id)
        assert result.success is True
        assert result.chapters_crawled == 4

        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters if c.status.value == "crawled"] == [1, 2, 4, 5]
        # Chương lỗi được lưu thành row failed (FE lọc + retry từng chương).
        failed = [c for c in chapters if c.status.value == "failed"]
        assert [c.chapter_index for c in failed] == [3]
        assert "lỗi giả lập" in (failed[0].error_message or "")
        assert novel_repo.get_by_id(novel.id).lifecycle_status.value == "fully_crawled"
    finally:
        db.close()


class ConsecutiveScrapeFailSource:
    key = "consecutive_fail"
    name = "consecutive fail"

    def __init__(self, total_chapters: int, fail_from: int, fail_count: int):
        self.total_chapters = total_chapters
        self.fail_from = fail_from
        self.fail_count = fail_count

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=i, title=f"Ch {i}", url=f"{novel_url}#{i}")
            for i in range(1, self.total_chapters + 1)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        index = int(chapter_url.rsplit("#", 1)[1])
        if self.fail_from <= index < self.fail_from + self.fail_count:
            raise ScrapeError(f"HTTP 503 block tại chương {index}")
        return _SAMPLE_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def test_retry_resumes_from_failed_chapter_not_from_scratch(client):  # noqa: ARG001 (client khởi động app/DB)
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        novel = novel_repo.add(
            Novel(id=None, title="Resume test novel", source_key="flaky_test", source_url="u-resume-test")
        )

        source = ConsecutiveScrapeFailSource(total_chapters=5, fail_from=3, fail_count=3)
        use_case = _use_case(db, source)

        # --- Lần 1: 3 lỗi fetch liên tiếp (ch 3–5) → dừng sau ch 2 ---
        result1 = use_case.execute(novel.id)
        assert result1.success is False
        assert result1.chapters_crawled == 2

        chapter_repo = SqlAlchemyChapterRepository(db)
        chapters_after_fail = chapter_repo.list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters_after_fail if c.status.value == "crawled"] == [1, 2]
        # ch 3-5 lỗi được lưu row failed; Retry bên dưới lật chúng thành crawled.
        assert [c.chapter_index for c in chapters_after_fail if c.status.value == "failed"] == [3, 4, 5]

        novel_after_fail = novel_repo.get_by_id(novel.id)
        assert novel_after_fail.lifecycle_status.value == "error"
        # KHÔNG advance qua ch 3-4 dù bị bỏ qua (quyết định thật 17/9/2026,
        # giữ nguyên code hiện tại — xem docstring `_skip_chapter_and_maybe_stop`):
        # để lần Retry sau còn TỰ BIẾT cần bù lại đúng 3-4-5, không đánh rơi
        # vĩnh viễn — khớp đúng ý "còn thiếu thì Thử lại sau bù tiếp".
        assert novel_after_fail.last_chapter_index == 2

        # --- Lần 2 (retry): source OK — bù lại ĐỦ 3-4-5, không bỏ sót ---
        ok_source = FlakyOnceSource(total_chapters=5, fail_index=99)
        use_case = _use_case(db, ok_source)
        result2 = use_case.execute(novel.id)
        assert result2.success is True
        assert result2.chapters_crawled == 3

        chapters_final = chapter_repo.list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters_final] == [1, 2, 3, 4, 5]
        assert all(c.status.value == "crawled" for c in chapters_final)
        assert len(chapters_final) == len({c.chapter_index for c in chapters_final})

        novel_final = novel_repo.get_by_id(novel.id)
        assert novel_final.lifecycle_status.value == "fully_crawled"
        assert novel_final.last_chapter_index == 5
    finally:
        db.close()


def _seed_crawled_chapters(db, novel_id: int, count: int) -> None:
    """Tạo sẵn `count` Chapter đã `crawled` — mô phỏng ĐÚNG thực tế 1 novel
    `fully_crawled` thật (Chapter luôn được tạo cùng lúc `last_chapter_index`
    tăng, không có đường nào khiến 2 thứ này lệch nhau — sửa 17/9/2026, thay
    cho việc chỉ set `last_chapter_index`/`total_chapters` trên Novel mà
    không tạo Chapter tương ứng như bản test cũ, khiến 2 test dưới đây coi
    incremental "hụt mất" 3 chương đã có, tưởng đâu là bug thật trong lúc
    thực ra chỉ là fixture giả không khớp tình huống thật)."""
    from crawl.domain.entities import Chapter, ChapterStatus

    chapter_repo = SqlAlchemyChapterRepository(db)
    for i in range(1, count + 1):
        ch = Chapter(
            id=None, novel_id=novel_id, chapter_index=i, title=f"Ch {i}", source_url=f"u{i}",
        )
        ch.status = ChapterStatus.CRAWLED
        ch.raw_path = f"/tmp/fake-resume-{novel_id}-{i}.txt"
        chapter_repo.add(ch)


def test_incremental_from_fully_crawled_crawls_only_new_chapters(client):  # noqa: ARG001
    """fully_crawled + mục lục dài hơn → chỉ crawl chương mới (sync tay)."""
    from platform_.db import SessionLocal

    from crawl.domain.entities import NovelLifecycle

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Sync test",
                source_key="flaky_test",
                source_url="u-sync-test",
                last_chapter_index=3,
                total_chapters=3,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        _seed_crawled_chapters(db, novel.id, 3)
        source = FlakyOnceSource(total_chapters=5, fail_index=99)
        use_case = _use_case(db, source)
        result = use_case.execute(novel.id, incremental=True)
        assert result.success is True
        assert result.chapters_crawled == 2

        # Đủ cả 5 chương (1-3 seed sẵn + 4-5 mới crawl lần này) — chỉ 2
        # chương SAU CÙNG mới thật sự được fetch/lưu lượt này (đã xác nhận
        # qua `result.chapters_crawled == 2` ở trên).
        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters] == [1, 2, 3, 4, 5]

        updated = novel_repo.get_by_id(novel.id)
        assert updated.lifecycle_status.value == "fully_crawled"
        assert updated.last_chapter_index == 5
        assert updated.total_chapters == 5
    finally:
        db.close()


def test_incremental_from_fully_crawled_noop_when_no_new_chapters(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    from crawl.domain.entities import NovelLifecycle

    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Sync noop",
                source_key="flaky_test",
                source_url="u-sync-noop",
                last_chapter_index=3,
                total_chapters=3,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        _seed_crawled_chapters(db, novel.id, 3)
        source = FlakyOnceSource(total_chapters=3, fail_index=99)
        result = _use_case(db, source).execute(novel.id, incremental=True)
        assert result.success is True
        assert result.chapters_crawled == 0
        assert novel_repo.get_by_id(novel.id).lifecycle_status.value == "fully_crawled"
    finally:
        db.close()
