"""Quét lần 2+: bỏ qua truyện đã có nhưng sync chương mới + lọc quảng cáo."""
from pathlib import Path

from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.domain.entities import Novel, NovelLifecycle
from crawl.domain.services import is_genre_list_noise
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)

_SAMPLE_TEXT = "他走在路上，看见前方有一道光，心里很害怕，不知道该怎么办。" * 5


class _GrowingNovelSource:
    key = "growing_novel"
    name = "growing novel test"
    cfg = type("Cfg", (), {"base_url": "https://example.com"})()

    def __init__(self, chapter_counts: dict[str, int]):
        self.chapter_counts = chapter_counts

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page != 1:
            return []
        return [
            NovelRef(title="Quảng cáo", url="https://other-site.com/ad", latest_chapter_title=""),
            NovelRef(title="Truyện cũ", url="https://example.com/novel-a", latest_chapter_title=""),
            NovelRef(title="Truyện mới", url="https://example.com/novel-b", latest_chapter_title=""),
        ]

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        total = self.chapter_counts.get(novel_url, 3)
        return [
            ChapterRef(
                index=i,
                title=f"第{i}章" + (" 大结局" if i == total else ""),
                url=f"{novel_url}/ch{i}",
            )
            for i in range(1, total + 1)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        return _SAMPLE_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _build_use_case(db, source) -> CrawlGenreUseCase:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    crawl_novel = CrawlNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(Path("/tmp/scan_existing_sync_raw")),
        source_resolver=lambda _key: source,
    )
    return CrawlGenreUseCase(
        novel_repo=novel_repo,
        genre_repo=SqlAlchemyGenreRepository(db),
        crawl_novel_use_case=crawl_novel,
        source_resolver=lambda _key: source,
        get_scan_window=lambda _key: 1,
        get_max_chapters_per_story=lambda _key: 50,
        get_narration_filter=lambda _key: "any",
        get_max_pages_per_scan=lambda _key: 1,
        get_max_consecutive_errors=lambda _key: 5,
    )


def test_is_genre_list_noise_detects_ad_and_external_link():
    assert is_genre_list_noise(
        NovelRef(title="Quảng cáo hot", url="https://example.com/x", latest_chapter_title=""),
        base_url="https://example.com",
    )
    assert is_genre_list_noise(
        NovelRef(title="OK", url="https://other.com/n", latest_chapter_title=""),
        base_url="https://example.com",
    )
    assert not is_genre_list_noise(
        NovelRef(title="Truyện", url="https://example.com/n", latest_chapter_title=""),
        base_url="https://example.com",
    )
    # Syosetu: ranking ở yomou, truyện ở ncode — cùng syosetu.com, không phải ads.
    assert not is_genre_list_noise(
        NovelRef(title="短編", url="https://ncode.syosetu.com/n5099ms/", latest_chapter_title=""),
        base_url="https://yomou.syosetu.com",
    )


def test_scan_syncs_new_chapters_for_existing_novel(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(
            source_key="growing_novel",
            genre_key="g1",
            label="G1",
            list_url="https://example.com/list",
        )
        novel_repo = SqlAlchemyNovelRepository(db)
        saved_old = novel_repo.add(
            Novel(
                id=None,
                title="Truyện cũ",
                source_key="growing_novel",
                source_url="https://example.com/novel-a",
                last_chapter_index=3,
                total_chapters=3,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
                is_complete=True,
            )
        )
        for i in range(1, 4):
            from crawl.domain.entities import Chapter, ChapterStatus

            ch = Chapter(
                id=None,
                novel_id=saved_old.id,
                chapter_index=i,
                title=f"Ch {i}",
                source_url=f"u{i}",
            )
            ch.status = ChapterStatus.CRAWLED
            ch.raw_path = f"/tmp/fake-{i}.txt"
            SqlAlchemyChapterRepository(db).add(ch)

        source = _GrowingNovelSource(
            chapter_counts={
                "https://example.com/novel-a": 4,
                "https://example.com/novel-b": 3,
            }
        )
        use_case = _build_use_case(db, source)
        result = use_case.execute(genre.id)

        assert result.discovered == 1
        assert result.synced == 1

        old = novel_repo.get_by_source_url("growing_novel", "https://example.com/novel-a")
        assert old.last_chapter_index == 4
        assert old.total_chapters == 4
        assert old.lifecycle_status == NovelLifecycle.FULLY_CRAWLED

        chapters = SqlAlchemyChapterRepository(db).list_by_novel(old.id)
        assert len(chapters) == 4
    finally:
        db.close()


def test_rescan_without_new_chapters_does_not_rediscover(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    class _SingleExistingSource(_GrowingNovelSource):
        def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
            if page != 1:
                return []
            return [
                NovelRef(
                    title="Truyện cũ rescan",
                    url="https://example.com/novel-rescan",
                    latest_chapter_title="",
                )
            ]

    db = SessionLocal()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(
            source_key="growing_novel",
            genre_key="g2-rescan",
            label="G2 rescan",
            list_url="https://example.com/list-rescan",
        )
        novel_repo = SqlAlchemyNovelRepository(db)
        saved = novel_repo.add(
            Novel(
                id=None,
                title="Truyện cũ rescan",
                source_key="growing_novel",
                source_url="https://example.com/novel-rescan",
                last_chapter_index=3,
                total_chapters=3,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        # "Có chương mới" so theo URL chương đã lưu — truyện cũ phải có đủ row.
        from crawl.domain.entities import Chapter

        chapter_repo = SqlAlchemyChapterRepository(db)
        for i in range(1, 4):
            ch = Chapter(id=None, novel_id=saved.id, chapter_index=i, title=f"第{i}章",
                         source_url=f"https://example.com/novel-rescan/ch{i}")
            ch.mark_crawled(f"/tmp/scan_existing_sync_raw/rescan-{i}.txt")
            chapter_repo.add(ch)
        source = _SingleExistingSource(chapter_counts={"https://example.com/novel-rescan": 3})
        use_case = _build_use_case(db, source)
        result = use_case.execute(genre.id)

        assert result.discovered == 0
        assert result.synced == 0
        unchanged = novel_repo.get_by_source_url("growing_novel", "https://example.com/novel-rescan")
        assert unchanged.last_chapter_index == 3
    finally:
        db.close()
