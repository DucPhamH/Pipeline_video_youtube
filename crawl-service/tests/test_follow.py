import datetime as dt
from types import SimpleNamespace

from crawl.application import follow
from crawl.application.use_cases import CrawlNovelUseCase, RawTextStorage
from crawl.domain.entities import Novel, NovelLifecycle
from crawl.domain.value_objects import ChapterRef
from crawl.application import pipeline
from crawl.infrastructure.persistence.models import NovelFollowModel, NovelPipelineModel
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal

_TEXT = "这是一段用于测试的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3


class GrowingSource:
    key = "follow_test"

    def __init__(self, total: int):
        self.total = total

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return [
            ChapterRef(index=i, title=f"Chương {i}", url=f"{novel_url}#{i}") for i in range(1, self.total + 1)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        return _TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _translated_novel(db, url: str, source: GrowingSource) -> int:
    repo = SqlAlchemyNovelRepository(db)
    novel = repo.add(Novel(id=None, title=f"Theo dõi {url}", source_key="follow_test", source_url=url))
    CrawlNovelUseCase(
        novel_repo=repo,
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(config.raw_dir),
        source_resolver=lambda _k: source,
    ).execute(novel.id)
    novel = repo.get_by_id(novel.id)
    novel.mark_translating()
    repo.update(novel)
    return novel.id


def _must_not_send(*_a, **_k):
    raise AssertionError("không được gửi dịch")


def test_new_chapters_are_crawled_smoothed_and_resent(client, monkeypatch):  # noqa: ARG001
    sent: list[int] = []
    def fake_send(db, *, novel_id, require_cleaned):
        sent.append(novel_id)
        return SimpleNamespace(error=None, variant_id=9)

    monkeypatch.setattr(follow, "send_to_translate", fake_send)
    monkeypatch.setattr(pipeline, "start_listen", lambda *a, **k: 0)
    db = SessionLocal()
    try:
        source = GrowingSource(3)
        novel_id = _translated_novel(db, "u-follow-new", source)
        db.add(NovelFollowModel(novel_id=novel_id, auto_translate=True, auto_audio=True))
        db.commit()
        source.total = 5

        result = follow.check_follow(db, novel_id, source_resolver=lambda _k: source)

        assert result.new_chapters == 2
        assert result.sent_to_translate is True
        assert result.error is None
        assert sent == [novel_id]
        chapters = SqlAlchemyChapterRepository(db).list_by_novel(novel_id)
        assert len(chapters) == 5
        storage = RawTextStorage(config.raw_dir)
        assert all(storage.has_cleaned(c.raw_path) for c in chapters)
        row = db.get(NovelFollowModel, novel_id)
        assert row.last_new_chapters == 2 and row.last_checked_at is not None
        assert row.translate_variant_id == 9
    finally:
        db.close()


def test_no_new_chapters_keeps_translated_status(client, monkeypatch):  # noqa: ARG001
    monkeypatch.setattr(follow, "send_to_translate", _must_not_send)
    db = SessionLocal()
    try:
        source = GrowingSource(2)
        novel_id = _translated_novel(db, "u-follow-same", source)
        db.add(NovelFollowModel(novel_id=novel_id, auto_translate=True))
        db.commit()

        result = follow.check_follow(db, novel_id, source_resolver=lambda _k: source)

        assert result.new_chapters == 0 and result.error is None
        novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
        assert novel.lifecycle_status == NovelLifecycle.TRANSLATING
    finally:
        db.close()


def test_without_auto_translate_only_crawls(client, monkeypatch):  # noqa: ARG001
    monkeypatch.setattr(follow, "send_to_translate", _must_not_send)
    db = SessionLocal()
    try:
        source = GrowingSource(1)
        novel_id = _translated_novel(db, "u-follow-manual", source)
        db.add(NovelFollowModel(novel_id=novel_id, auto_translate=False))
        db.commit()
        source.total = 2

        result = follow.check_follow(db, novel_id, source_resolver=lambda _k: source)

        assert result.new_chapters == 1 and result.sent_to_translate is False
    finally:
        db.close()


def test_due_follows_respects_interval(client):  # noqa: ARG001
    db = SessionLocal()
    try:
        now = dt.datetime(2026, 10, 1, 12, 0)
        repo = SqlAlchemyNovelRepository(db)
        ids = [
            repo.add(Novel(id=None, title=f"due {i}", source_key="follow_test", source_url=f"u-due-{i}")).id
            for i in range(3)
        ]
        db.add_all(
            [
                NovelFollowModel(novel_id=ids[0], last_checked_at=None),
                NovelFollowModel(novel_id=ids[1], last_checked_at=now - dt.timedelta(hours=1)),
                NovelFollowModel(novel_id=ids[2], last_checked_at=now - dt.timedelta(hours=7)),
            ]
        )
        db.commit()
        due = set(follow.due_follows(db, now))
        assert ids[0] in due and ids[2] in due and ids[1] not in due
    finally:
        db.close()


def test_follow_api_roundtrip(client):
    db = SessionLocal()
    try:
        novel_id = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="API follow", source_key="follow_test", source_url="u-follow-api")
        ).id
    finally:
        db.close()

    resp = client.put(f"/api/crawl/novels/{novel_id}/follow", json={"auto_translate": True})
    assert resp.status_code == 200
    assert resp.json()["auto_translate"] is True
    items = client.get("/api/crawl/follows").json()["items"]
    assert any(i["novel_id"] == novel_id and i["title"] == "API follow" for i in items)

    assert client.delete(f"/api/crawl/novels/{novel_id}/follow").status_code == 204
    items = client.get("/api/crawl/follows").json()["items"]
    assert all(i["novel_id"] != novel_id for i in items)
    assert client.put("/api/crawl/novels/999999/follow", json={}).status_code == 404


def test_follow_audio_starts_when_translation_is_ready(client, monkeypatch):  # noqa: ARG001
    calls: list[tuple] = []

    def listen(variant_id, *, preset, engine):
        calls.append((variant_id, preset, engine))
        return 21

    monkeypatch.setattr(pipeline, "start_listen", listen)
    db = SessionLocal()
    try:
        novel_id = SqlAlchemyNovelRepository(db).add(
            Novel(id=None, title="Audio follow", source_key="follow_test", source_url="u-follow-audio")
        ).id
        db.add(
            NovelFollowModel(
                novel_id=novel_id,
                auto_audio=True,
                voice_preset="nu_ke_cham",
                translate_variant_id=9,
            )
        )
        db.commit()

        follow.on_follow_audio(db, novel_id, "translating", spawn=False)
        assert calls == []

        follow.on_follow_audio(db, novel_id, "ready_for_video", spawn=False)
        row = db.get(NovelFollowModel, novel_id)
        assert calls == [(9, "nu_ke_cham", "edge")]
        assert row.tts_work_id == 21

        calls.clear()
        db.add(NovelPipelineModel(novel_id=novel_id, stage="speaking", voice_preset="nam_ke", engine="edge"))
        db.commit()
        follow.on_follow_audio(db, novel_id, "ready_for_video", spawn=False)
        assert calls == []
    finally:
        db.close()
