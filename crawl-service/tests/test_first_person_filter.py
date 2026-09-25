"""Verify tính năng lọc phong cách trần thuật qua option `crawl.narration_filter`
("any"/"first_person"/"third_person"), đánh giá trên chương mẫu THẬT
(không đoán qua tiêu đề)."""
from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.domain.entities import Genre
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)

_FIRST_PERSON_TEXT = "我走在路上，我看见前方有一道光，我心里很害怕，我不知道该怎么办。我不知道。" * 2
_THIRD_PERSON_TEXT = "他走在路上，他看见前方有一道光，他心里很害怕，他不知道该怎么办。他不知道。" * 2


class _FakeSource:
    """Source giả: 1 truyện duy nhất, hoàn thành, nội dung chương do test
    quyết định (first/third person) để kiểm tra filter."""

    key = "fake_fp_test"
    name = "fake first-person test source"

    def __init__(self, sample_text: str):
        self.sample_text = sample_text

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page != 1:
            return []
        # URL truyện phải PHỤ THUỘC genre_list_url (khác nhau giữa các test)
        # — Novel unique theo (source_key, source_url) TOÀN CỤC, không theo
        # genre, nên URL cố định sẽ khiến test sau bị "Library mode" bỏ qua
        # vì tưởng đã discovered từ test chạy trước đó (DB dùng chung session).
        return [
            NovelRef(
                title="Test Novel", url=f"{genre_list_url}/novel-url", latest_chapter_title="第五章 大结局"
            )
        ]

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=i, title=f"第{i}章" + (" 大结局" if i == 5 else ""), url=f"ch{i}")
            for i in range(1, 6)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        return self.sample_text

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _build_use_case(db, source, narration_filter: str) -> CrawlGenreUseCase:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    crawl_novel_use_case = CrawlNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(__import__("pathlib").Path("/tmp/fp_filter_test_raw")),
        source_resolver=lambda _key: source,
    )
    return CrawlGenreUseCase(
        novel_repo=novel_repo,
        genre_repo=SqlAlchemyGenreRepository(db),
        crawl_novel_use_case=crawl_novel_use_case,
        source_resolver=lambda _key: source,
        get_scan_window=lambda source_key: 5,
        get_max_chapters_per_story=lambda source_key: 50,
        get_narration_filter=lambda source_key: narration_filter,
    )


def _make_genre(db) -> Genre:
    return SqlAlchemyGenreRepository(db).get_or_create(
        source_key="fake_fp_test", genre_key="test", label="Test", list_url="test-url"
    )


def test_first_person_story_accepted_when_filter_on(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        genre = _make_genre(db)
        use_case = _build_use_case(db, _FakeSource(_FIRST_PERSON_TEXT), narration_filter="first_person")
        result = use_case.execute(genre.id)
        assert result.discovered == 1
        assert result.rejected == 0
    finally:
        db.close()


def test_third_person_story_rejected_when_filter_on(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(
            source_key="fake_fp_test", genre_key="test2", label="Test2", list_url="test-url-2"
        )
        use_case = _build_use_case(db, _FakeSource(_THIRD_PERSON_TEXT), narration_filter="first_person")
        result = use_case.execute(genre.id)
        assert result.discovered == 0
        assert result.rejected == 1

        novels = SqlAlchemyNovelRepository(db).list_all(status="rejected")
        assert any("ngôi thứ nhất" in (n.error_message or "") for n in novels)
    finally:
        db.close()


def test_third_person_story_accepted_when_filter_off(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(
            source_key="fake_fp_test", genre_key="test3", label="Test3", list_url="test-url-3"
        )
        use_case = _build_use_case(db, _FakeSource(_THIRD_PERSON_TEXT), narration_filter="any")
        result = use_case.execute(genre.id)
        assert result.discovered == 1
        assert result.rejected == 0
    finally:
        db.close()
