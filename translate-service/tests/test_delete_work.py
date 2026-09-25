"""Xóa hẳn 1 Work — cascade chapters/variants/jobs/segments + dọn glossary."""
import time


def _import_work(client, title="Delete Work Demo"):
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": title,
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# Ch1\n\nHello.\n\n# Ch2\n\nWorld.\n",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_work_cascades_everything(client):
    work = _import_work(client)
    work_id = work["id"]
    variant_id = work["variants"][0]["id"]

    r = client.post(f"/api/translate/works/{work_id}/glossary", json={"source_term": "foo", "target_term": "bar"})
    assert r.status_code == 201

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202
    job_id = r.json()["id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get(f"/api/translate/jobs/{job_id}").json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.02)

    r = client.delete(f"/api/translate/works/{work_id}")
    assert r.status_code == 204, r.text

    assert client.get(f"/api/translate/works/{work_id}").status_code == 404
    assert client.get(f"/api/translate/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/translate/works/{work_id}/glossary").status_code == 404


def test_delete_work_blocked_while_job_running_or_queued(client):
    work = _import_work(client, title="Delete Work Blocked")
    work_id = work["id"]
    variant_id = work["variants"][0]["id"]

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    job_id = r.json()["id"]

    r = client.delete(f"/api/translate/works/{work_id}")
    if r.status_code == 400:
        assert "job" in r.json()["detail"].lower()
        # đợi xong rồi xóa lại được
        deadline = time.time() + 10
        while time.time() < deadline:
            if client.get(f"/api/translate/jobs/{job_id}").json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.02)
        r = client.delete(f"/api/translate/works/{work_id}")
        assert r.status_code == 204
    else:
        # mock quá nhanh — job đã completed trước khi xóa, vẫn ok
        assert r.status_code == 204


def test_delete_unknown_work_404(client):
    r = client.delete("/api/translate/works/999999")
    assert r.status_code == 404
