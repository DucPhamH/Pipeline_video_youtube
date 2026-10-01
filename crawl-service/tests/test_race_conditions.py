"""Chứng minh + verify fix cho race condition khi 2 request gần như đồng
thời thao tác cùng 1 entity (bấm 2 lần liên tiếp trước khi lần đầu kịp
xong). Test dùng 2 DB session RIÊNG (giống 2 request HTTP thật, mỗi request
có 1 Session qua Depends(get_db)) — không dựa vào may rủi thread timing.
"""
import pytest

from crawl.domain.entities import Chapter, Novel
from crawl.domain.ports import DuplicateError
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)


def test_concurrent_add_same_novel_url_raises_duplicate_error_not_raw_db_error(client):  # noqa: ARG001
    """2 request 'Thêm truyện' cùng URL, cả 2 đều check 'chưa tồn tại'
    TRƯỚC KHI request nào insert xong (đúng kịch bản double-click) -> request
    thứ 2 insert vi phạm UniqueConstraint("source_key", "source_url").

    Repository phải bắt IntegrityError của DB và raise lại thành
    DuplicateError (domain-friendly) — KHÔNG để lộ raw
    sqlalchemy.exc.IntegrityError ra ngoài (sẽ thành HTTP 500 chung chung
    nếu use case không biết cách xử lý nó)."""
    from platform_.db import SessionLocal

    db1, db2 = SessionLocal(), SessionLocal()
    try:
        repo1, repo2 = SqlAlchemyNovelRepository(db1), SqlAlchemyNovelRepository(db2)

        assert repo1.get_by_source_url("race_test", "u-race-novel") is None
        assert repo2.get_by_source_url("race_test", "u-race-novel") is None

        repo1.add(Novel(id=None, title="A", source_key="race_test", source_url="u-race-novel"))

        with pytest.raises(DuplicateError):
            repo2.add(Novel(id=None, title="B", source_key="race_test", source_url="u-race-novel"))

        # Session vẫn dùng được bình thường sau khi bắt lỗi (đã rollback đúng cách).
        assert repo2.get_by_source_url("race_test", "u-race-novel") is not None
    finally:
        db1.close()
        db2.close()


def test_concurrent_crawl_same_novel_duplicate_chapter_raises_duplicate_error(client):  # noqa: ARG001
    """2 request 'Thử lại' cùng 1 novel_id gần như đồng thời -> cả 2 vòng
    lặp crawl đều cố insert Chapter cùng chapter_index -> phải thành
    DuplicateError, không phải raw IntegrityError."""
    from platform_.db import SessionLocal

    db1, db2 = SessionLocal(), SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db1)
        novel = novel_repo.add(
            Novel(id=None, title="X", source_key="race_test", source_url="u-race-chapters")
        )

        chap_repo1 = SqlAlchemyChapterRepository(db1)
        chap_repo2 = SqlAlchemyChapterRepository(db2)

        chap_repo1.add(Chapter(id=None, novel_id=novel.id, chapter_index=1, title="C1", source_url="u1"))
        with pytest.raises(DuplicateError):
            chap_repo2.add(
                Chapter(id=None, novel_id=novel.id, chapter_index=1, title="C1-dup", source_url="u1")
            )
    finally:
        db1.close()
        db2.close()


class _RaceInjectingNovelRepo:
    """Bọc quanh 1 NovelRepository thật — ngay sau khi trả lời
    get_by_source_url() (bước "check"), CHÈN NGAY 1 bản ghi cạnh tranh qua
    session khác trước khi use case kịp "act" (add). Mô phỏng đúng khoảnh
    khắc race: request khác vừa commit xong đúng giữa lúc check và act của
    request này — thứ mà 2 request chạy tuần tự bình thường không bao giờ
    tái hiện được."""

    def __init__(self, real_repo, inject_fn):
        self._real = real_repo
        self._inject_fn = inject_fn
        self._injected = False

    def get_by_source_url(self, source_key, source_url):
        result = self._real.get_by_source_url(source_key, source_url)
        if result is None and not self._injected:
            self._injected = True
            self._inject_fn(source_key, source_url)
        return result

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_add_novel_use_case_gracefully_handles_duplicate_race(client):
    """Verify tầng use-case (không chỉ repository): khi 'act' (add) đụng
    phải 1 bản ghi vừa được request khác chèn đúng giữa lúc 'check' và
    'act', AddManualNovelUseCase phải trả về JSON lỗi rõ ràng
    (success:false) — KHÔNG để DuplicateError/IntegrityError lọt ra ngoài
    thành HTTP 500."""
    import tempfile
    from pathlib import Path

    from platform_.db import SessionLocal

    from crawl.application.use_cases import AddManualNovelUseCase, CrawlNovelUseCase, RawTextStorage
    from crawl.infrastructure.persistence.repositories import SqlAlchemyChapterRepository as ChapRepo
    from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository as NovelRepo
    from crawl.infrastructure.sources.registry import get_source

    # Thư mục fixture RIÊNG, tự tạo mới mỗi lần chạy test — KHÔNG dùng chung
    # demo_novel/derive_test_novel với các test khác, vì DB dùng chung
    # session-scope: chạy cả bộ test, demo_novel có thể đã bị test khác
    # đăng ký từ trước, khiến nhánh "existing" thường bắt được trước khi
    # tới nhánh race muốn test ở đây.
    # Nằm TRONG fixtures_dir — demo_local từ chối đọc đường dẫn ngoài thư mục đó.
    from platform_.config import config as _cfg

    novel_dir = Path(tempfile.mkdtemp(prefix="race_test_novel_", dir=_cfg.fixtures_dir))
    (novel_dir / "chapter_001.txt").write_text(
        "这是专门为本测试新建的临时章节内容,与其他测试完全隔离,汉字比例足够高。" * 2,
        encoding="utf-8",
    )
    novel_url = str(novel_dir)

    db, other_db = SessionLocal(), SessionLocal()
    try:
        other_repo = NovelRepo(other_db)

        def inject(source_key, source_url):
            other_repo.add(
                Novel(id=None, title="Injected by race", source_key=source_key, source_url=source_url)
            )

        racy_novel_repo = _RaceInjectingNovelRepo(NovelRepo(db), inject)
        crawl_novel_use_case = CrawlNovelUseCase(
            racy_novel_repo, ChapRepo(db), RawTextStorage(Path("/tmp/x")), get_source
        )
        use_case = AddManualNovelUseCase(
            novel_repo=racy_novel_repo,
            crawl_novel_use_case=crawl_novel_use_case,
            source_resolver=get_source,
        )

        result = use_case.execute("demo_local", novel_url)

        assert result.success is False
        # Race có thể bắt ở resolve (existing) hoặc add (DuplicateError).
        assert "đồng thời" in result.error or "đã có trong hệ thống" in result.error
    finally:
        db.close()
        other_db.close()
        import shutil

        shutil.rmtree(novel_dir, ignore_errors=True)
