import time
from types import SimpleNamespace

from crawl.application import pipeline
from crawl.domain.entities import Novel
from crawl.infrastructure.persistence.models import NovelPipelineModel
from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository
from platform_.db import SessionLocal


def _novel(db, url: str) -> int:
    repo = SqlAlchemyNovelRepository(db)
    novel = repo.add(Novel(id=None, title=f"Pipeline {url}", source_key="pipeline_test", source_url=url))
    novel.mark_fully_crawled()
    repo.update(novel)
    return novel.id


def _patch_send(monkeypatch):
    monkeypatch.setattr(
        pipeline, "smooth_novel", lambda db, novel_id: SimpleNamespace(success=True, error=None)
    )

    def fake_send(db, *, novel_id, require_cleaned, start_job):
        return SimpleNamespace(work_id=4, variant_id=9, error=None)

    monkeypatch.setattr(pipeline, "send_to_translate", fake_send)


def test_audio_starts_only_after_translation_is_ready(client, monkeypatch):  # noqa: ARG001
    _patch_send(monkeypatch)
    started: dict = {}
    monkeypatch.setattr(
        pipeline,
        "_fetch_book",
        lambda variant_id: {
            "title": "T",
            "author": "A",
            "lang_tgt": "vi",
            "chapters": [
                {"index": 1, "title": "C1", "text": "xin chào"},
                {"index": 2, "title": "trống", "text": "  "},
            ],
        },
    )

    def start(**kwargs):
        started.update(kwargs)
        return 15

    monkeypatch.setattr(pipeline, "_start_tts", start)
    db = SessionLocal()
    try:
        novel_id = _novel(db, "u-pipe-ready")
        pipeline.begin(db, novel_id, voice_preset="nam_ke", engine="mock")
        pipeline.on_translate_status(db, novel_id, "ready_for_video", spawn=False)
        assert db.get(NovelPipelineModel, novel_id).stage == "smoothing"
        assert started == {}

        pipeline.execute(db, novel_id)
        row = db.get(NovelPipelineModel, novel_id)
        assert row.stage == "translating"
        assert row.translate_variant_id == 9
        assert started == {}

        pipeline.on_translate_status(db, novel_id, "ready_for_video", spawn=False)
        row = db.get(NovelPipelineModel, novel_id)
        assert row.stage == "done"
        assert row.tts_work_id == 15
        assert started["preset"] == "nam_ke"
        assert started["engine"] == "mock"
        assert started["external_id"] == "translate:variant:9"
        assert [c["text"] for c in started["chapters"]] == ["xin chào"]
    finally:
        db.close()


def test_failed_translation_marks_pipeline_error(client, monkeypatch):  # noqa: ARG001
    _patch_send(monkeypatch)
    db = SessionLocal()
    try:
        novel_id = _novel(db, "u-pipe-fail")
        pipeline.begin(db, novel_id, voice_preset="nu_ke_cham", engine="edge")
        pipeline.execute(db, novel_id)
        pipeline.on_translate_status(db, novel_id, "failed", "hết quota", spawn=False)
        row = db.get(NovelPipelineModel, novel_id)
        assert row.stage == "error"
        assert row.error == "hết quota"
    finally:
        db.close()


def test_pipeline_api_reaches_translating_and_rejects_a_second_run(client, monkeypatch):
    _patch_send(monkeypatch)
    db = SessionLocal()
    try:
        novel_id = _novel(db, "u-pipe-api")
    finally:
        db.close()

    first = client.post(
        f"/api/crawl/novels/{novel_id}/pipeline",
        json={"voice_preset": "doi_thoai", "engine": "mock"},
    )
    assert first.status_code == 202
    assert first.json()["stage"] == "smoothing"

    row = {}
    for _ in range(50):
        items = client.get("/api/crawl/pipelines").json()["items"]
        row = next(item for item in items if item["novel_id"] == novel_id)
        if row["stage"] == "translating":
            break
        time.sleep(0.05)
    assert row["stage"] == "translating"
    assert row["voice_preset"] == "doi_thoai"

    again = client.post(f"/api/crawl/novels/{novel_id}/pipeline", json={})
    assert again.status_code == 409

    missing = client.post("/api/crawl/novels/999999/pipeline", json={})
    assert missing.status_code == 404
