"""Per-job provider config (model + base_url + api_key)."""
import time

from platform_.db import SessionLocal
from translate.application.run_job import enqueue_job, set_job_provider
from translate.infrastructure.persistence.repositories import JobRepository, SegmentRepository


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def test_start_with_full_provider_config(client):
    r = client.get("/api/translate/models")
    assert r.status_code == 200
    info = r.json()
    assert "suggested_base_urls" in info
    assert "default_base_url" in info

    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Cred Job",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# Ch1\n\nHello credentials.\n",
        },
    )
    variant_id = r.json()["variants"][0]["id"]

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={
            "provider": "openai",
            "model": "my-custom-model",
            "base_url": "https://example.com/v1",
            "api_key": "sk-secret-abcd1234",
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["model"] == "my-custom-model"
    assert job["base_url"] == "https://example.com/v1"
    assert job["has_api_key"] is True
    assert job["api_key_hint"].endswith("1234")
    assert "sk-secret" not in r.text

    db = SessionLocal()
    try:
        entity = JobRepository(db).get(job["id"])
        assert entity is not None
        assert entity.api_key == "sk-secret-abcd1234"
        assert entity.base_url == "https://example.com/v1"
    finally:
        db.close()

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={
            "provider": "mock",
            "model": "mock-model",
            "base_url": "",
            "api_key": "",
        },
    )
    assert r.status_code == 202
    assert r.json()["provider"] == "mock"
    assert _wait_job(client, r.json()["id"]) == "completed"


def test_patch_provider_updates_key_and_cache(client):
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Patch Cred",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# X\n\nBody.\n",
        },
    )
    variant_id = r.json()["variants"][0]["id"]

    db = SessionLocal()
    try:
        job = enqueue_job(
            db,
            variant_id=variant_id,
            provider="openai",
            model="m1",
            base_url="https://a.example/v1",
            api_key="key-aaaa",
        )
        job_id = job.id
        assert job_id is not None
        key1 = SegmentRepository(db).list_by_job(job_id)[0].cache_key

        updated = set_job_provider(
            db,
            job_id=job_id,
            model="m2",
            base_url="https://b.example/v1",
            api_key="key-bbbb",
        )
        assert updated.model == "m2"
        assert updated.base_url == "https://b.example/v1"
        assert updated.api_key == "key-bbbb"
        key2 = SegmentRepository(db).list_by_job(job_id)[0].cache_key
        assert key1 != key2
    finally:
        db.close()

    r = client.patch(
        f"/api/translate/jobs/{job_id}/provider",
        json={"model": "m3", "api_key": "key-cccc"},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "m3"
    assert r.json()["has_api_key"] is True
    assert "key-cccc" not in r.text
