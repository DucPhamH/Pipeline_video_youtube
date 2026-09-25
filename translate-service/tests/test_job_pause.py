"""Pause job — resumable stop, distinct verb from cancel but same mechanics."""
import time


def _import_work(client, title="Pause Demo"):
    text = "# Chapter One\n\nHello world.\n\n# Chapter Two\n\nSecond body.\n\n# Chapter Three\n\nThird."
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": title, "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    return r.json()["variants"][0]["id"]


def test_pause_then_resume(client):
    variant_id = _import_work(client)

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    r = client.post(f"/api/translate/jobs/{job_id}/pause")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"  # no new status — same machinery as cancel
    assert "tạm dừng" in (r.json()["error"] or "").lower()

    r = client.post(f"/api/translate/jobs/{job_id}/resume")
    assert r.status_code == 202, r.text

    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert status == "completed"


def test_pause_completed_job_rejected(client):
    variant_id = _import_work(client, title="Pause Completed")
    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    job_id = r.json()["id"]

    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get(f"/api/translate/jobs/{job_id}").json()["status"] == "completed":
            break
        time.sleep(0.02)

    r = client.post(f"/api/translate/jobs/{job_id}/pause")
    assert r.status_code == 400
