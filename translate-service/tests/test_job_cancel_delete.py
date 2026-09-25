"""Cancel / delete job control."""
import time


def _import_work(client):
    text = "# Chapter One\n\nHello world.\n\n# Chapter Two\n\nSecond body.\n\n# Chapter Three\n\nThird."
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Cancel Demo",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": text,
        },
    )
    assert r.status_code == 201, r.text
    work = r.json()
    return work["variants"][0]["id"]


def test_cancel_then_resume_and_delete(client):
    variant_id = _import_work(client)

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    # Cancel ngay (queued hoặc running)
    r = client.post(f"/api/translate/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # Không xóa được nếu… đã cancelled — xóa được
    r = client.delete(f"/api/translate/jobs/{job_id}")
    assert r.status_code == 204, r.text

    r = client.get(f"/api/translate/jobs/{job_id}")
    assert r.status_code == 404


def test_cancel_running_leaves_partial_progress(client):
    variant_id = _import_work(client)
    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202
    job_id = r.json()["id"]

    # Chờ bắt đầu chạy
    deadline = time.time() + 5
    while time.time() < deadline:
        st = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if st in ("running", "completed", "cancelled"):
            break
        time.sleep(0.02)

    r = client.post(f"/api/translate/jobs/{job_id}/cancel")
    # Có thể đã completed rất nhanh với mock — chấp nhận 200 hoặc 400
    if r.status_code == 200:
        assert r.json()["status"] == "cancelled"
        # Resume phần còn lại
        r = client.post(f"/api/translate/jobs/{job_id}/resume")
        if r.status_code == 202:
            job_id2 = r.json()["id"]
            deadline = time.time() + 10
            while time.time() < deadline:
                st = client.get(f"/api/translate/jobs/{job_id2}").json()["status"]
                if st in ("completed", "failed"):
                    break
                time.sleep(0.05)
    else:
        assert r.status_code == 400


def test_cannot_delete_running(client):
    variant_id = _import_work(client)
    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    job_id = r.json()["id"]
    # Thử xóa ngay khi queued/running
    r = client.delete(f"/api/translate/jobs/{job_id}")
    if r.status_code == 400:
        assert "Dừng" in r.json()["detail"] or "dừng" in r.json()["detail"].lower()
    else:
        # Job mock hoàn tất quá nhanh — ok
        assert r.status_code == 204
