"""AI provider registry — CRUD + local (no api_key) end-to-end."""
import time

from platform_.db import SessionLocal
from translate.application.run_job import enqueue_job
from translate.infrastructure.persistence.repositories import JobRepository


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def test_seeded_mock_provider_present(client):
    r = client.get("/api/translate/ai-providers")
    assert r.status_code == 200
    kinds = [p["kind"] for p in r.json()]
    assert "mock" in kinds


def test_crud_ai_provider(client):
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": "My DeepSeek",
            "kind": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-abcd1234",
            "requires_api_key": True,
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["has_api_key"] is True
    assert "sk-abcd1234" not in r.text

    r = client.put(
        f"/api/translate/ai-providers/{p['id']}",
        json={"label": "My DeepSeek (renamed)", "model": "deepseek-reasoner"},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "My DeepSeek (renamed)"
    assert r.json()["model"] == "deepseek-reasoner"
    # key preserved (not sent in PATCH)
    assert r.json()["has_api_key"] is True

    r = client.delete(f"/api/translate/ai-providers/{p['id']}")
    assert r.status_code == 204
    r = client.put(f"/api/translate/ai-providers/{p['id']}", json={"label": "x"})
    assert r.status_code == 404


def test_local_provider_ignores_leftover_global_settings_key(client):
    """ai_provider_id là nguồn authoritative — không được rơi xuống
    translate.openai_api_key toàn cục dù global settings có key khác."""
    r = client.put(
        "/api/translate/settings",
        json={
            "values": {
                "translate.provider": "openai",
                "translate.openai_api_key": "sk-leftover-global-key",
            }
        },
    )
    assert r.status_code == 200

    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": "Local no leak",
            "kind": "local",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5",
            "api_key": "",
            "requires_api_key": False,
        },
    )
    ai_provider_id = r.json()["id"]

    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Local No Leak Demo",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# Ch1\n\nHello.\n",
        },
    )
    variant_id = r.json()["variants"][0]["id"]

    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=variant_id, ai_provider_id=ai_provider_id)
        assert job.api_key == ""  # not "sk-leftover-global-key"
        assert job.provider == "openai"
    finally:
        db.close()

    # restore for other tests in this session
    client.put(
        "/api/translate/settings",
        json={"values": {"translate.provider": "mock", "translate.openai_api_key": ""}},
    )


def test_local_provider_blank_key_does_not_fall_back_to_mock(client):
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": "Local Ollama",
            "kind": "local",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5",
            "api_key": "",
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    ai_provider_id = r.json()["id"]

    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Local AI Demo",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# Ch1\n\nHello local.\n",
        },
    )
    variant_id = r.json()["variants"][0]["id"]

    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=variant_id, ai_provider_id=ai_provider_id)
        assert job.provider == "openai"  # not forced to mock despite blank api_key
        assert job.requires_api_key is False
        entity = JobRepository(db).get(job.id)
        assert entity is not None
        assert entity.provider == "openai"
    finally:
        db.close()
