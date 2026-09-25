"""Job gắn với 1 AI đã lưu (ai_provider_id) — resume trơn (không truyền gì)
phải tự lấy credential MỚI NHẤT của registry, không kẹt ở snapshot cũ lúc tạo
job. Đây đúng là bug user gặp: sửa key sai trong Settings rồi bấm 'Dịch lại'
vẫn dùng key cũ."""
from platform_.db import SessionLocal
from translate.application.run_job import enqueue_job, resume_job
from translate.infrastructure.persistence.repositories import (
    AiProviderRepository,
    JobRepository,
)
from translate.domain.entities import AiProvider


def test_plain_resume_refetches_current_registry_key(client):
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": "Groq Test",
            "kind": "custom",
            "base_url": "https://api.groq.example/v1",
            "model": "some-model",
            "api_key": "sk-wrong-key-typo",
            "requires_api_key": True,
        },
    )
    assert r.status_code == 201, r.text
    ai_provider_id = r.json()["id"]

    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Resume Refresh Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nBody.\n"},
    )
    variant_id = r.json()["variants"][0]["id"]

    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=variant_id, ai_provider_id=ai_provider_id)
        assert job.ai_provider_id == ai_provider_id
        job_entity = JobRepository(db).get(job.id)
        assert job_entity.api_key == "sk-wrong-key-typo"

        # Người dùng phát hiện gõ sai key -> vào Settings sửa lại đúng key
        AiProviderRepository(db).update(
            AiProvider(
                id=ai_provider_id,
                label="Groq Test",
                kind="custom",
                provider="openai",
                base_url="https://api.groq.example/v1",
                model="some-model",
                api_key="sk-correct-key",
                requires_api_key=True,
            )
        )
        db.commit()

        # Segment fail giả lập (như thật sự bị 401 khi chạy) rồi bấm "Dịch lại"
        # KHÔNG truyền override gì — đúng luồng nút Dịch lại trên UI hiện tại.
        from translate.domain.entities import SegmentStatus
        from translate.infrastructure.persistence.repositories import SegmentRepository

        seg_repo = SegmentRepository(db)
        segs = seg_repo.list_by_job(job.id)
        for seg in segs:
            seg.status = SegmentStatus.FAILED
            seg.error = "401 Invalid API Key"
            seg_repo.update(seg)
        db.commit()

        resumed = resume_job(db, job_id=job.id)
        assert resumed.api_key == "sk-correct-key"  # đã refresh, không còn kẹt ở key cũ
        assert resumed.ai_provider_id == ai_provider_id
    finally:
        db.close()


def test_explicit_raw_override_detaches_from_registry(client):
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": "Groq A", "kind": "custom", "base_url": "https://a.example/v1", "model": "m", "api_key": "key-a"},
    )
    ai_provider_id = r.json()["id"]

    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Detach Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nBody.\n"},
    )
    variant_id = r.json()["variants"][0]["id"]

    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=variant_id, ai_provider_id=ai_provider_id)
        assert job.ai_provider_id == ai_provider_id

        from translate.domain.entities import SegmentStatus
        from translate.infrastructure.persistence.repositories import SegmentRepository

        seg_repo = SegmentRepository(db)
        for seg in seg_repo.list_by_job(job.id):
            seg.status = SegmentStatus.FAILED
            seg_repo.update(seg)
        db.commit()

        # User tự tay override provider (không qua registry) -> tách khỏi registry
        resumed = resume_job(db, job_id=job.id, api_key="manual-override-key")
        assert resumed.api_key == "manual-override-key"
        assert resumed.ai_provider_id is None
    finally:
        db.close()
