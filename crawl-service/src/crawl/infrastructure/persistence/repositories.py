"""Implement các Repository Protocol khai báo ở domain/ports.py bằng
SQLAlchemy — map 2 chiều ORM model <-> domain entity."""
import time

from sqlalchemy import func, tuple_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from crawl.domain.entities import Chapter, ChapterStatus, Genre, GenreRunStatus, Novel, NovelLifecycle
from crawl.domain.ports import DuplicateError
from crawl.infrastructure.persistence.models import ChapterModel, GenreModel, NovelModel
from platform_.db import is_sqlite_locked


def _is_unique_violation(exc: IntegrityError) -> bool:
    """UNIQUE (trùng bản ghi) khác FK/NOT NULL — chỉ UNIQUE mới là DuplicateError."""
    msg = str(getattr(exc, "orig", exc) or exc).lower()
    return "unique" in msg or "duplicate key" in msg


def _retry_locked(op_name: str, fn, *, retries: int = 10):
    delay = 0.05
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except OperationalError as exc:
            last = exc
            if not is_sqlite_locked(exc):
                raise
            if attempt >= retries - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 2.0)
    assert last is not None
    raise last


def _genre_to_entity(m: GenreModel) -> Genre:
    return Genre(
        id=m.id, source_key=m.source_key, genre_key=m.genre_key,
        label=m.label, list_url=m.list_url, enabled=m.enabled,
        last_run_status=GenreRunStatus(m.last_run_status),
        last_run_started_at=m.last_run_started_at,
        last_run_finished_at=m.last_run_finished_at,
        last_run_discovered=m.last_run_discovered,
        last_run_rejected=m.last_run_rejected,
        last_run_errors=m.last_run_errors,
        last_run_messages=m.last_run_messages,
    )


def _novel_to_entity(m: NovelModel) -> Novel:
    return Novel(
        id=m.id, title=m.title, source_key=m.source_key, source_url=m.source_url,
        genre_id=m.genre_id, is_manual=m.is_manual, last_chapter_index=m.last_chapter_index,
        is_complete=m.is_complete, total_chapters=m.total_chapters,
        lifecycle_status=NovelLifecycle(m.lifecycle_status), error_message=m.error_message,
        author=getattr(m, "author", "") or "",
        cover_url=getattr(m, "cover_url", "") or "",
        content_fingerprint=getattr(m, "content_fingerprint", "") or "",
        created_at=m.created_at, updated_at=m.updated_at,
    )


def _chapter_to_entity(m: ChapterModel) -> Chapter:
    return Chapter(
        id=m.id, novel_id=m.novel_id, chapter_index=m.chapter_index, title=m.title,
        source_url=m.source_url, raw_path=m.raw_path, status=ChapterStatus(m.status),
        error_message=m.error_message, queued_for_translate=m.queued_for_translate,
        reviewed=m.reviewed, created_at=m.created_at,
        toc_order=getattr(m, "toc_order", None),
    )


class SqlAlchemyGenreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, genre_id: int) -> Genre | None:
        m = self.db.get(GenreModel, genre_id)
        return _genre_to_entity(m) if m else None

    def list_enabled(self) -> list[Genre]:
        rows = self.db.query(GenreModel).filter(GenreModel.enabled.is_(True)).all()
        return [_genre_to_entity(m) for m in rows]

    def list_all(self) -> list[Genre]:
        return [_genre_to_entity(m) for m in self.db.query(GenreModel).all()]

    def list_by_source_key(self, source_key: str) -> list[Genre]:
        rows = self.db.query(GenreModel).filter_by(source_key=source_key).all()
        return [_genre_to_entity(m) for m in rows]

    def _filtered_query(
        self,
        *,
        source_key: str | None,
        search: str | None,
        enabled: bool | None,
        last_run_status: str | None,
        allowed_keys: set[tuple[str, str]] | None,
    ):
        q = self.db.query(GenreModel)
        if source_key:
            q = q.filter(GenreModel.source_key == source_key)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                (GenreModel.label.ilike(pattern)) | (GenreModel.genre_key.ilike(pattern))
            )
        if enabled is not None:
            q = q.filter(GenreModel.enabled.is_(enabled))
        if last_run_status:
            q = q.filter(GenreModel.last_run_status == last_run_status)
        if allowed_keys is not None:
            q = q.filter(tuple_(GenreModel.source_key, GenreModel.genre_key).in_(allowed_keys))
        return q

    def list_filtered(
        self,
        *,
        source_key: str | None = None,
        search: str | None = None,
        enabled: bool | None = None,
        last_run_status: str | None = None,
        allowed_keys: set[tuple[str, str]] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Genre]:
        q = self._filtered_query(
            source_key=source_key,
            search=search,
            enabled=enabled,
            last_run_status=last_run_status,
            allowed_keys=allowed_keys,
        ).order_by(GenreModel.label, GenreModel.id)
        if limit is not None:
            q = q.offset(offset).limit(limit)
        return [_genre_to_entity(m) for m in q.all()]

    def count_filtered(
        self,
        *,
        source_key: str | None = None,
        search: str | None = None,
        enabled: bool | None = None,
        last_run_status: str | None = None,
        allowed_keys: set[tuple[str, str]] | None = None,
    ) -> int:
        return self._filtered_query(
            source_key=source_key,
            search=search,
            enabled=enabled,
            last_run_status=last_run_status,
            allowed_keys=allowed_keys,
        ).count()

    def update(self, genre: Genre) -> None:
        def _do() -> None:
            m = self.db.get(GenreModel, genre.id)
            if m is None:
                return
            m.enabled = genre.enabled
            m.last_run_status = genre.last_run_status.value
            m.last_run_started_at = genre.last_run_started_at
            m.last_run_finished_at = genre.last_run_finished_at
            m.last_run_discovered = genre.last_run_discovered
            m.last_run_rejected = genre.last_run_rejected
            m.last_run_errors = genre.last_run_errors
            m.last_run_messages = genre.last_run_messages
            try:
                self.db.commit()
            except OperationalError:
                self.db.rollback()
                raise

        _retry_locked("genre.update", _do)

    def update_run_state(self, genre: Genre) -> None:
        """Chỉ ghi các cột last_run_* — lượt quét chạy hàng phút, không được
        ghi đè `enabled` người dùng vừa đổi trong lúc đó (bản `genre` trong
        tay use case đọc từ lúc bắt đầu quét)."""
        def _do() -> None:
            m = self.db.get(GenreModel, genre.id)
            if m is None:
                return
            # Đọc lại từ DB — tránh identity map trả object cũ.
            self.db.refresh(m)
            m.last_run_status = genre.last_run_status.value
            m.last_run_started_at = genre.last_run_started_at
            m.last_run_finished_at = genre.last_run_finished_at
            m.last_run_discovered = genre.last_run_discovered
            m.last_run_rejected = genre.last_run_rejected
            m.last_run_errors = genre.last_run_errors
            m.last_run_messages = genre.last_run_messages
            try:
                self.db.commit()
            except OperationalError:
                self.db.rollback()
                raise

        _retry_locked("genre.update_run_state", _do)

    def get_or_create(
        self,
        source_key: str,
        genre_key: str,
        label: str,
        list_url: str,
        enabled: bool = True,
    ) -> Genre:
        m = (
            self.db.query(GenreModel)
            .filter_by(source_key=source_key, genre_key=genre_key)
            .one_or_none()
        )
        if m is None:
            m = GenreModel(
                source_key=source_key, genre_key=genre_key, label=label, list_url=list_url,
                enabled=enabled,
            )
            self.db.add(m)
        else:
            # Đồng bộ label/URL khi seed đổi — không để select hiện nhãn cũ.
            m.label = label
            m.list_url = list_url
        self.db.commit()
        self.db.refresh(m)
        return _genre_to_entity(m)


class SqlAlchemyNovelRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, novel_id: int) -> Novel | None:
        m = self.db.get(NovelModel, novel_id)
        return _novel_to_entity(m) if m else None

    def get_fresh(self, novel_id: int) -> Novel | None:
        """Như get_by_id nhưng đọc lại từ DB (bỏ qua identity map của session)."""
        m = self.db.get(NovelModel, novel_id, populate_existing=True)
        return _novel_to_entity(m) if m else None

    def get_by_source_url(self, source_key: str, source_url: str) -> Novel | None:
        m = (
            self.db.query(NovelModel)
            .filter_by(source_key=source_key, source_url=source_url)
            .one_or_none()
        )
        return _novel_to_entity(m) if m else None

    def _filtered_query(
        self,
        status: str | None,
        source_key: str | None,
        search: str | None,
        is_manual: bool | None = None,
        genre_id: int | None = None,
    ):
        q = self.db.query(NovelModel)
        if status:
            q = q.filter(NovelModel.lifecycle_status == status)
        if source_key:
            q = q.filter(NovelModel.source_key == source_key)
        if search:
            q = q.filter(NovelModel.title.ilike(f"%{search}%"))
        if is_manual is not None:
            q = q.filter(NovelModel.is_manual.is_(is_manual))
        if genre_id is not None:
            q = q.filter(NovelModel.genre_id == genre_id)
        return q

    def list_all(
        self,
        status: str | None = None,
        source_key: str | None = None,
        search: str | None = None,
        is_manual: bool | None = None,
        genre_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Novel]:
        q = self._filtered_query(status, source_key, search, is_manual, genre_id).order_by(
            NovelModel.updated_at.desc(), NovelModel.created_at.desc()
        )
        if limit is not None:
            q = q.offset(offset).limit(limit)
        return [_novel_to_entity(m) for m in q.all()]

    def count_all(
        self,
        status: str | None = None,
        source_key: str | None = None,
        search: str | None = None,
        is_manual: bool | None = None,
        genre_id: int | None = None,
    ) -> int:
        return self._filtered_query(status, source_key, search, is_manual, genre_id).count()

    def get_by_fingerprint(self, fingerprint: str) -> Novel | None:
        if not fingerprint:
            return None
        m = (
            self.db.query(NovelModel)
            .filter(NovelModel.content_fingerprint == fingerprint)
            .order_by(NovelModel.id.asc())
            .first()
        )
        return _novel_to_entity(m) if m else None

    def add(self, novel: Novel) -> Novel:
        def _do() -> Novel:
            m = NovelModel(
                title=novel.title, source_key=novel.source_key, source_url=novel.source_url,
                genre_id=novel.genre_id, is_manual=novel.is_manual,
                last_chapter_index=novel.last_chapter_index, is_complete=novel.is_complete,
                total_chapters=novel.total_chapters, lifecycle_status=novel.lifecycle_status.value,
                error_message=novel.error_message,
                author=novel.author or "",
                cover_url=novel.cover_url or "",
                content_fingerprint=novel.content_fingerprint or "",
            )
            self.db.add(m)
            try:
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                if not _is_unique_violation(exc):
                    raise
                raise DuplicateError(
                    f"Novel (source_key={novel.source_key}, source_url={novel.source_url}) đã tồn tại"
                ) from exc
            except OperationalError:
                self.db.rollback()
                raise
            self.db.refresh(m)
            return _novel_to_entity(m)

        return _retry_locked("novel.add", _do)

    def update(self, novel: Novel, *, commit: bool = True) -> None:
        def _do() -> None:
            m = self.db.get(NovelModel, novel.id)
            if m is None:
                return
            # `title` đồng bộ vì site có thể đổi/chuẩn hoá lại tiêu đề khi
            # gặp lại truyện đã biết (`_try_sync_existing_novel`/
            # `_try_reevaluate_rejected` gán `existing.title = candidate.title`
            # rồi gọi update() — thiếu dòng này thì đổi tên bị ÂM THẦM mất,
            # bug thật phát hiện lúc review 17/9/2026, chưa có test nào bắt được
            # vì test hiện tại luôn dùng title giống hệt nhau).
            m.title = novel.title
            m.author = novel.author or ""
            m.cover_url = novel.cover_url or ""
            m.content_fingerprint = novel.content_fingerprint or ""
            m.last_chapter_index = novel.last_chapter_index
            m.is_complete = novel.is_complete
            m.total_chapters = novel.total_chapters
            m.lifecycle_status = novel.lifecycle_status.value
            m.error_message = novel.error_message
            if commit:
                try:
                    self.db.commit()
                except OperationalError:
                    self.db.rollback()
                    raise
            else:
                self.db.flush()

        if commit:
            _retry_locked("novel.update", _do)
        else:
            _do()

    def commit(self) -> None:
        def _do() -> None:
            try:
                self.db.commit()
            except OperationalError:
                self.db.rollback()
                raise

        _retry_locked("novel.commit", _do)
    def delete(self, novel_id: int) -> bool:
        m = self.db.get(NovelModel, novel_id)
        if m is None:
            return False
        self.db.delete(m)
        self.db.commit()
        return True


class SqlAlchemyChapterRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, chapter_id: int) -> Chapter | None:
        m = self.db.get(ChapterModel, chapter_id)
        return _chapter_to_entity(m) if m else None

    def list_by_novel(self, novel_id: int) -> list[Chapter]:
        return self.list_by_novel_filtered(novel_id)

    def _filtered_query(
        self,
        novel_id: int,
        *,
        status: str | None,
        search: str | None,
        reviewed: bool | None,
    ):
        q = self.db.query(ChapterModel).filter_by(novel_id=novel_id)
        if status:
            q = q.filter(ChapterModel.status == status)
        if search:
            q = q.filter(ChapterModel.title.ilike(f"%{search}%"))
        if reviewed is not None:
            q = q.filter(ChapterModel.reviewed.is_(reviewed))
        return q

    def list_by_novel_filtered(
        self,
        novel_id: int,
        *,
        status: str | None = None,
        search: str | None = None,
        reviewed: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Chapter]:
        q = self._filtered_query(
            novel_id, status=status, search=search, reviewed=reviewed
        ).order_by(
            func.coalesce(ChapterModel.toc_order, ChapterModel.chapter_index),
            ChapterModel.chapter_index,
        )
        if limit is not None:
            q = q.offset(offset).limit(limit)
        return [_chapter_to_entity(m) for m in q.all()]

    def count_by_novel_filtered(
        self,
        novel_id: int,
        *,
        status: str | None = None,
        search: str | None = None,
        reviewed: bool | None = None,
    ) -> int:
        return self._filtered_query(
            novel_id, status=status, search=search, reviewed=reviewed
        ).count()

    def count_status_by_novels(self, novel_ids: list[int]) -> dict[int, dict[str, int]]:
        """{novel_id: {status: số chương}} — 1 query GROUP BY cho cả trang list."""
        if not novel_ids:
            return {}
        rows = (
            self.db.query(ChapterModel.novel_id, ChapterModel.status, func.count(ChapterModel.id))
            .filter(ChapterModel.novel_id.in_(novel_ids))
            .group_by(ChapterModel.novel_id, ChapterModel.status)
            .all()
        )
        out: dict[int, dict[str, int]] = {}
        for novel_id, status, n in rows:
            out.setdefault(novel_id, {})[status] = int(n)
        return out

    def add(self, chapter: Chapter, *, commit: bool = True) -> Chapter:
        def _do() -> Chapter:
            m = ChapterModel(
                novel_id=chapter.novel_id, chapter_index=chapter.chapter_index, title=chapter.title,
                source_url=chapter.source_url, raw_path=chapter.raw_path, status=chapter.status.value,
                error_message=chapter.error_message, queued_for_translate=chapter.queued_for_translate,
                reviewed=chapter.reviewed, toc_order=chapter.toc_order,
            )
            self.db.add(m)
            try:
                if commit:
                    self.db.commit()
                else:
                    self.db.flush()
            except IntegrityError as exc:
                self.db.rollback()
                if not _is_unique_violation(exc):
                    raise
                raise DuplicateError(
                    f"Chapter (novel_id={chapter.novel_id}, chapter_index={chapter.chapter_index}) đã tồn tại"
                ) from exc
            except OperationalError:
                self.db.rollback()
                raise
            self.db.refresh(m)
            return _chapter_to_entity(m)

        if commit:
            return _retry_locked("chapter.add", _do)
        return _do()

    def update(self, chapter: Chapter, *, commit: bool = True) -> None:
        def _do() -> None:
            m = self.db.get(ChapterModel, chapter.id)
            if m is None:
                return
            m.title = chapter.title
            m.source_url = chapter.source_url
            m.raw_path = chapter.raw_path
            m.status = chapter.status.value
            m.error_message = chapter.error_message
            m.queued_for_translate = chapter.queued_for_translate
            m.reviewed = chapter.reviewed
            m.toc_order = chapter.toc_order
            if commit:
                try:
                    self.db.commit()
                except OperationalError:
                    self.db.rollback()
                    raise
            else:
                self.db.flush()

        if commit:
            _retry_locked("chapter.update", _do)
        else:
            _do()

    def commit(self) -> None:
        def _do() -> None:
            try:
                self.db.commit()
            except OperationalError:
                self.db.rollback()
                raise

        _retry_locked("chapter.commit", _do)
    def delete(self, chapter_id: int) -> bool:
        m = self.db.get(ChapterModel, chapter_id)
        if m is None:
            return False
        self.db.delete(m)
        self.db.commit()
        return True
