"""Nhiều AI chia nhau dịch 1 job (pool, round-robin theo chương)."""
import time

from platform_.db import SessionLocal
from translate.application.run_job import enqueue_job, resume_job, set_job_provider


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def _add_ai(client, label: str) -> int:
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": label, "kind": "mock", "base_url": "", "model": "mock", "api_key": "", "requires_api_key": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_pool_job_round_robins_across_providers(client):
    ai_a = _add_ai(client, "Pool AI A")
    ai_b = _add_ai(client, "Pool AI B")

    text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, 6))  # 5 chương
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Pool Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    variant_id = r.json()["variants"][0]["id"]

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={"ai_provider_ids": [ai_a, ai_b]},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    job_id = job["id"]
    assert len(job["provider_slots"]) == 2
    assert {s["label"] for s in job["provider_slots"]} == {"Pool AI A", "Pool AI B"}

    assert _wait_job(client, job_id) == "completed"

    segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
    assert len(segs) == 5
    assert all(s["status"] in ("done", "skipped_cache") for s in segs)
    # round-robin: chương lẻ/chẵn xen kẽ 2 slot khác nhau
    by_chapter = sorted(segs, key=lambda s: s["chapter_index"])
    detail0 = client.get(f"/api/translate/segments/{by_chapter[0]['id']}").json()
    detail1 = client.get(f"/api/translate/segments/{by_chapter[1]['id']}").json()
    assert detail0["output_text"] != detail1["output_text"]  # 2 AI khác nhau xử lý


def test_pool_rejects_provider_override_on_patch_and_resume(client):
    ai_a = _add_ai(client, "Pool Guard A")
    ai_b = _add_ai(client, "Pool Guard B")

    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Pool Guard Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nBody.\n"},
    )
    variant_id = r.json()["variants"][0]["id"]

    # Gọi thẳng application layer (không qua thread nền) để job chắc chắn còn
    # QUEUED khi test guard — patch/resume trên pool job phải từ chối đổi provider.
    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=variant_id, ai_provider_ids=[ai_a, ai_b])
        job_id = job.id

        try:
            set_job_provider(db, job_id=job_id, model="other-model")
            assert False, "phải raise ValueError"
        except ValueError as exc:
            assert "pool" in str(exc).lower()

        try:
            resume_job(db, job_id=job_id, model="other-model")
            assert False, "phải raise ValueError"
        except ValueError as exc:
            assert "pool" in str(exc).lower()
    finally:
        db.close()
