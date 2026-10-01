"""Crawl linh hoạt — bỏ qua chương lỗi, thử chương sau (mọi site)."""
from crawl.application.use_cases import CrawlNovelUseCase, RawTextStorage
from crawl.domain.entities import Novel
from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)

_SAMPLE_TEXT = "这是一段用于测试的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3
_SHORT_TEXT = "空の彼方\n菱田愛日"


class MixedContentSource:
    key = "mixed_content"
    name = "mixed content test"

    def __init__(self, short_indices: set[int]):
        self.short_indices = short_indices

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=i, title=f"Ch {i}", url=f"{novel_url}#{i}")
            for i in range(1, 6)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        index = int(chapter_url.rsplit("#", 1)[1])
        if index in self.short_indices:
            return _SHORT_TEXT
        return _SAMPLE_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _use_case(db, source) -> CrawlNovelUseCase:
    return CrawlNovelUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(__import__("pathlib").Path("/tmp/crawl_skip_invalid_test_raw")),
        source_resolver=lambda _key: source,
    )


def test_skips_one_invalid_chapter_and_continues(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="Skip one", source_key="mixed_content", source_url="u-skip-one")
        )
        use_case = _use_case(db, MixedContentSource(short_indices={2}))
        result = use_case.execute(novel.id)
        # Thiếu ĐÚNG 1 chương lẻ tẻ (không chạm circuit breaker) — vẫn coi
        # là THÀNH CÔNG, vẫn lưu được 4 chương hợp lệ, Retry bù chương còn
        # thiếu sau (quyết định thật 17/9/2026, khớp
        # test_single_scrape_error_skips_and_continues bên
        # test_crawl_novel_resume.py).
        assert result.success is True
        assert result.chapters_crawled == 4

        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters if c.status.value == "crawled"] == [1, 3, 4, 5]
        assert [c.chapter_index for c in chapters if c.status.value == "failed"] == [2]

        novel_final = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        assert novel_final.lifecycle_status.value == "fully_crawled"
        assert "Thiếu" in (novel_final.error_message or "")
        assert novel_final.last_chapter_index == 5
    finally:
        db.close()


def test_vip_scrape_errors_do_not_stop_after_three(client):  # noqa: ARG001
    """VIP/lỗi riêng chương — bỏ qua liên tục, không kết luận site chết."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="VIP skip", source_key="mixed_content", source_url="u-vip")
        )
        use_case = _use_case(db, VipChapterSource())
        result = use_case.execute(novel.id)
        # 3 chương VIP bị bỏ qua KHÔNG chạm circuit breaker (lỗi riêng
        # chương, không tính "liên tiếp" như lỗi hạ tầng) — vẫn thành công,
        # Retry bù lại sau khi có cookie (quyết định thật 17/9/2026).
        assert result.success is True
        assert result.chapters_crawled == 2
        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters if c.status.value == "crawled"] == [1, 5]
        assert [c.chapter_index for c in chapters if c.status.value == "failed"] == [2, 3, 4]
        novel_final = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        assert novel_final.lifecycle_status.value == "fully_crawled"
    finally:
        db.close()


class VipChapterSource(MixedContentSource):
    def __init__(self) -> None:
        super().__init__(short_indices=set())

    def fetch_chapter_content(self, chapter_url: str) -> str:
        index = int(chapter_url.rsplit("#", 1)[1])
        if index in (2, 3, 4):
            raise ScrapeError(f"[test] Chương VIP — cần cookie đăng nhập: {chapter_url}")
        return super().fetch_chapter_content(chapter_url)


def test_fails_after_three_consecutive_invalid(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="Skip fail", source_key="mixed_content", source_url="u-skip-fail")
        )
        use_case = _use_case(db, MixedContentSource(short_indices={3, 4, 5}))
        result = use_case.execute(novel.id)
        assert result.success is False
        assert result.chapters_crawled == 2
        assert "liên tiếp" in (SqlAlchemyNovelRepository(db).get_by_id(novel.id).error_message or "")
    finally:
        db.close()


def test_retry_fills_skipped_vip_chapter(client):  # noqa: ARG001
    """Sau khi có cookie — Retry lấy lại chương VIP đã bỏ qua."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="VIP retry", source_key="mixed_content", source_url="u-vip-retry")
        )
        use_case = _use_case(db, VipChapterSource())
        first = use_case.execute(novel.id)
        assert first.success is True  # thiếu 3 chương VIP nhưng chưa chạm breaker
        assert first.chapters_crawled == 2

        # Lần 2: không còn VIP
        use_case2 = _use_case(db, MixedContentSource(short_indices=set()))
        second = use_case2.execute(novel.id, incremental=True)
        assert second.success is True
        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [c.chapter_index for c in chapters] == [1, 2, 3, 4, 5]
        assert SqlAlchemyNovelRepository(db).get_by_id(novel.id).lifecycle_status.value == "fully_crawled"
    finally:
        db.close()
