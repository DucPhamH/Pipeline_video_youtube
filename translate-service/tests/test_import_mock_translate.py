"""E2E: import TXT → mock job → export chứa marker dịch."""
import time


def test_import_mock_translate_export(client):
    text = "# Chapter One\n\nHello world.\n\n# Chapter Two\n\nSecond chapter body."
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Demo Novel",
            "author": "Tester",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": text,
        },
    )
    assert r.status_code == 201, r.text
    work = r.json()
    assert work["title"] == "Demo Novel"
    assert len(work["chapters"]) == 2
    assert len(work["variants"]) == 1
    variant_id = work["variants"][0]["id"]
    assert work["variants"][0]["mode"] == "full"
    assert work["lang_tgt"] == "vi"

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202, r.text
    job = r.json()
    job_id = job["id"]
    assert job["status"] == "queued"
    assert job["provider"] == "mock"

    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        r = client.get(f"/api/translate/jobs/{job_id}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)

    assert status == "completed", client.get(f"/api/translate/jobs/{job_id}").text

    r = client.get(f"/api/translate/jobs/{job_id}/segments")
    assert r.status_code == 200
    segs = r.json()
    assert len(segs) == 2
    assert all(s["status"] in ("done", "skipped_cache") for s in segs)

    r = client.get(f"/api/translate/variants/{variant_id}/export.txt")
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8")
    assert "[vi]" in body
    assert "Hello world" in body or "[vi] Hello world" in body
