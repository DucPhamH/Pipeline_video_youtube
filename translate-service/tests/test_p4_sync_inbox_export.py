"""P4: fingerprint sync, export JSON, inbox."""
import time


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def test_fingerprint_sync_export_json_inbox(client):
    payload = {
        "external_id": "crawl:novel:p4-demo",
        "title": "P4 Novel",
        "author": "A",
        "lang_src": "zh",
        "lang_tgt_hint": "vi",
        "chapters": [
            {
                "index": 1,
                "title": "Ch1",
                "text": "原文一",
                "fingerprint": "fp-aaa",
            },
            {
                "index": 2,
                "title": "Ch2",
                "text": "原文二",
                "fingerprint": "fp-bbb",
            },
        ],
    }
    r = client.post("/api/translate/works/from-crawl", json=payload)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["created"] is True
    assert first["changed_chapter_indices"] == [1, 2]
    work_id = first["id"]
    full_id = first["variants"][0]["id"]

    r = client.post(f"/api/translate/variants/{full_id}/jobs")
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert _wait_job(client, job_id) == "completed"

    work = client.get(f"/api/translate/works/{work_id}").json()
    assert work["variants"][0]["status"] == "ready"

    # Re-handoff with chapter 2 changed
    payload["chapters"][1]["text"] = "原文二已改"
    payload["chapters"][1]["fingerprint"] = "fp-bbb-changed"
    r = client.post("/api/translate/works/from-crawl", json=payload)
    assert r.status_code == 200, r.text
    sync = r.json()
    assert sync["created"] is False
    assert sync["changed_chapter_indices"] == [2]
    assert sync["variants"][0]["status"] == "pending"

    # Same fingerprints → no change
    r = client.post("/api/translate/works/from-crawl", json=payload)
    assert r.json()["changed_chapter_indices"] == []

    # Re-run full after sync
    r = client.post(f"/api/translate/variants/{full_id}/jobs")
    job2 = r.json()["id"]
    assert _wait_job(client, job2) == "completed"

    r = client.get(f"/api/translate/variants/{full_id}/export.json")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["format"] == "tts_ready_v1"
    assert data["mode"] == "full"
    assert len(data["chapters"]) == 2
    assert data["chapters"][1]["text"].startswith("[vi]")

    r = client.get("/api/translate/inbox")
    assert r.status_code == 200
    inbox = r.json()
    assert "running" in inbox and "needs_review" in inbox and "ready_export" in inbox
    # Completed job with unreviewed segments → needs_review
    assert any(x["variant_id"] == full_id for x in inbox["needs_review"])
