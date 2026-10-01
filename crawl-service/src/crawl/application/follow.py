"""Theo dõi truyện đang ra: kiểm tra mục lục định kỳ, cào chương mới, làm mượt,
rồi gửi lại sang dịch nếu người dùng bật. Bản dịch cũ nằm trong cache của
translate-service nên lượt dịch lại chỉ tốn cho chương mới. Nếu bật tự đọc,
callback khi dịch xong sẽ tạo audio."""
from __future__ import annotations

import datetime as dt
import logging
import threading
from dataclasses import dataclass

from sqlalchemy.orm import Session

from crawl.application.chapter_resolve import try_list_chapters
from crawl.application.send_to_translate import send_to_translate
from crawl.application.use_cases import (
    CrawlNovelUseCase,
    RawTextStorage,
    SmoothNovelUseCase,
    toc_has_unsaved_chapters,
)
from crawl.domain.entities import NovelLifecycle
from crawl.infrastructure.persistence.models import NovelFollowModel
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal
from platform_.locks import release, try_acquire
from platform_.settings_store import get_per_site_setting

logger = logging.getLogger("crawl.follow")

FOLLOW_INTERVAL = dt.timedelta(hours=6)
_FOLLOWABLE = (
    NovelLifecycle.FULLY_CRAWLED,
    NovelLifecycle.ERROR,
    NovelLifecycle.TRANSLATING,
    NovelLifecycle.READY_FOR_VIDEO,
)
_TRANSLATED = (NovelLifecycle.TRANSLATING, NovelLifecycle.READY_FOR_VIDEO)


@dataclass
class FollowCheck:
    novel_id: int
    title: str = ""
    new_chapters: int = 0
    sent_to_translate: bool = False
    variant_id: int | None = None
    error: str | None = None


def due_follows(db: Session, now: dt.datetime) -> list[int]:
    cutoff = now - FOLLOW_INTERVAL
    rows = db.query(NovelFollowModel).all()
    return [r.novel_id for r in rows if r.last_checked_at is None or r.last_checked_at <= cutoff]


def check_follow(
    db: Session, novel_id: int, *, source_resolver, now: dt.datetime | None = None
) -> FollowCheck:
    follow = db.get(NovelFollowModel, novel_id)
    if follow is None:
        return FollowCheck(novel_id, error="Truyện chưa được theo dõi")
    novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
    if novel is None:
        db.delete(follow)
        db.commit()
        return FollowCheck(novel_id, error="Truyện đã bị xoá")
    auto_audio = bool(follow.auto_audio)
    result = _check(db, novel_id, auto_translate=bool(follow.auto_translate), source_resolver=source_resolver)
    result.title = novel.title
    follow = db.get(NovelFollowModel, novel_id)
    if follow is not None:
        follow.last_checked_at = now or dt.datetime.utcnow()
        follow.last_new_chapters = result.new_chapters
        follow.last_error = result.error
        if auto_audio and result.variant_id and not result.error:
            follow.translate_variant_id = result.variant_id
        db.commit()
        novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
        if (
            auto_audio
            and result.sent_to_translate
            and novel is not None
            and novel.lifecycle_status == NovelLifecycle.READY_FOR_VIDEO
        ):
            on_follow_audio(db, novel_id)
    return result


def _check(db: Session, novel_id: int, *, auto_translate: bool, source_resolver) -> FollowCheck:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    novel = novel_repo.get_by_id(novel_id)
    assert novel is not None
    if novel.lifecycle_status not in _FOLLOWABLE:
        return FollowCheck(novel_id, error=f"Đang ở trạng thái {novel.lifecycle_status.value}, chưa kiểm tra")
    try:
        source = source_resolver(novel.source_key)
    except KeyError as exc:
        return FollowCheck(novel_id, error=f"Nguồn không còn hỗ trợ: {exc}")

    chapters, list_err = try_list_chapters(source, novel.source_url)
    if chapters is None:
        return FollowCheck(novel_id, error=list_err or "Không lấy được mục lục")
    if not toc_has_unsaved_chapters(chapters, chapter_repo.list_by_novel(novel_id)):
        return FollowCheck(novel_id)

    before = novel.lifecycle_status
    novel.start_follow_sync()
    novel_repo.update(novel)
    storage = RawTextStorage(config.raw_dir)
    crawl = CrawlNovelUseCase(
        novel_repo=novel_repo, chapter_repo=chapter_repo, storage=storage, source_resolver=source_resolver
    ).execute(novel_id, prefetched_chapters=chapters, incremental=True)
    out = FollowCheck(novel_id, new_chapters=crawl.chapters_crawled, error=crawl.error)
    if not crawl.success:
        return out
    if crawl.chapters_crawled == 0:
        if before in _TRANSLATED:
            novel = novel_repo.get_by_id(novel_id)
            assert novel is not None
            novel.lifecycle_status = before
            novel_repo.update(novel)
        return out

    SmoothNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=storage,
        get_opencc_mode=lambda sk: get_per_site_setting(db, "opencc_mode", sk) or "none",
    ).execute(novel_id)
    if auto_translate:
        try:
            sent = send_to_translate(db, novel_id=novel_id, require_cleaned=False)
            out.sent_to_translate = True
            out.variant_id = getattr(sent, "variant_id", None)
            out.error = sent.error
        except (ValueError, LookupError) as exc:
            out.error = str(exc)
    return out


def on_follow_audio(
    db: Session, novel_id: int, status: str = "ready_for_video", *, spawn: bool = True
) -> None:
    """Dịch xong và người dùng bật tự đọc. Pipeline đang giữ chuỗi thì để pipeline tạo audio."""
    if (status or "").strip().lower() != "ready_for_video":
        return
    follow = db.get(NovelFollowModel, novel_id)
    if follow is None or not follow.auto_audio or not follow.translate_variant_id:
        return
    from crawl.infrastructure.persistence.models import NovelPipelineModel

    pipe = db.get(NovelPipelineModel, novel_id)
    if pipe is not None and pipe.stage in ("translating", "speaking"):
        return
    if not try_acquire(f"follow-audio:{novel_id}"):
        return
    variant_id = int(follow.translate_variant_id)
    preset = follow.voice_preset or "nam_ke"
    if spawn:
        threading.Thread(
            target=_audio_thread,
            args=(novel_id, variant_id, preset),
            daemon=True,
            name=f"follow-audio-{novel_id}",
        ).start()
        return
    try:
        _listen(db, novel_id, variant_id, preset)
    finally:
        release(f"follow-audio:{novel_id}")


def _audio_thread(novel_id: int, variant_id: int, preset: str) -> None:
    db = SessionLocal()
    try:
        _listen(db, novel_id, variant_id, preset)
    except Exception:
        logger.exception("Lỗi khi tạo audio cho truyện theo dõi %s", novel_id)
    finally:
        db.close()
        release(f"follow-audio:{novel_id}")


def _listen(db: Session, novel_id: int, variant_id: int, preset: str) -> None:
    from crawl.application.pipeline import start_listen

    try:
        work_id = start_listen(variant_id, preset=preset, engine="edge")
    except Exception as exc:  # noqa: BLE001 — ghi lỗi lên dòng theo dõi
        follow = db.get(NovelFollowModel, novel_id)
        if follow is not None:
            follow.last_error = str(exc)[:500]
            db.commit()
        return
    follow = db.get(NovelFollowModel, novel_id)
    if follow is not None:
        follow.tts_work_id = work_id
        follow.last_error = None
        db.commit()
