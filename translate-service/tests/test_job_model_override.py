"""Model theo job: Settings giữ default; start/selection override snapshot vào job."""
import time


def _import(client, n=2):
    text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, n + 1))
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Job Model", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    return r.json()["variants"][0]["id"]


def _add_ai(client, label: str, model: str) -> int:
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": label,
            "kind": "mock",
            "model": model,
            "api_key": "",
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = "queued"
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    return status


def test_job_model_override_does_not_change_settings_default(client):
    """Settings Claude default=fable; job chọn haiku → job.model=haiku, AI vẫn fable."""
    ai_id = _add_ai(client, "Claude", "claude-fable")
    variant_id = _import(client)

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={
            "ai_selections": [{"ai_provider_id": ai_id, "model": "claude-haiku"}],
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["model"] == "claude-haiku"

    saved = next(p for p in client.get("/api/translate/ai-providers").json() if p["id"] == ai_id)
    assert saved["model"] == "claude-fable"

    assert _wait(client, job["id"]) == "completed"


def test_resume_keeps_job_model_while_refreshing_keys(client):
    """Resume trơn: giữ model snapshot; không kéo về default Settings."""
    ai_id = _add_ai(client, "Claude Keep", "claude-fable")
    variant_id = _import(client, n=3)

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={"ai_selections": [{"ai_provider_id": ai_id, "model": "claude-haiku"}]},
    )
    job_id = r.json()["id"]
    # Cancel sớm để còn pending
    client.post(f"/api/translate/jobs/{job_id}/cancel")
    j = client.get(f"/api/translate/jobs/{job_id}").json()
    assert j["model"] == "claude-haiku"

    # Đổi default trên Settings — resume không được kéo theo
    client.put(f"/api/translate/ai-providers/{ai_id}", json={"model": "claude-sonnet"})

    r = client.post(f"/api/translate/jobs/{job_id}/resume")
    assert r.status_code == 202, r.text
    assert r.json()["model"] == "claude-haiku"


def test_model_only_patch_keeps_ai_provider_link(client):
    """Đổi chỉ model (PATCH/resume) không được gỡ ai_provider_id."""
    ai_id = _add_ai(client, "Claude Link", "claude-fable")
    variant_id = _import(client, n=3)

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={"ai_selections": [{"ai_provider_id": ai_id, "model": "claude-haiku"}]},
    )
    job_id = r.json()["id"]
    client.post(f"/api/translate/jobs/{job_id}/cancel")

    r = client.patch(f"/api/translate/jobs/{job_id}/provider", json={"model": "claude-sonnet"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "claude-sonnet"
    assert body["ai_provider_id"] == ai_id

    r = client.post(f"/api/translate/jobs/{job_id}/resume", json={"model": "claude-opus"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["model"] == "claude-opus"
    assert body["ai_provider_id"] == ai_id


def test_pool_each_ai_own_model_override(client):
    a = _add_ai(client, "A", "model-a-default")
    b = _add_ai(client, "B", "model-b-default")
    variant_id = _import(client, n=4)

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={
            "ai_mode": "pool",
            "ai_selections": [
                {"ai_provider_id": a, "model": "model-a-job"},
                {"ai_provider_id": b, "model": "model-b-job"},
            ],
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    slots = job["provider_slots"]
    assert len(slots) == 2
    models = {s["model"] for s in slots}
    assert models == {"model-a-job", "model-b-job"}
