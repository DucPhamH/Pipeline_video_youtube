"""P1: glossary inject + review edit + estimate + resume."""
import time


def test_glossary_review_estimate_resume(client):
    text = "# Ch1\n\nHero Li Ming walks.\n\n# Ch2\n\nMore text about Li Ming."
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Glossary Demo",
            "author": "A",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": text,
        },
    )
    assert r.status_code == 201, r.text
    work = r.json()
    work_id = work["id"]
    variant_id = work["variants"][0]["id"]

    r = client.post(
        f"/api/translate/works/{work_id}/glossary",
        json={"source_term": "Li Ming", "target_term": "Lý Minh", "protected": True},
    )
    assert r.status_code == 201, r.text
    term = r.json()
    assert term["protected"] is True

    r = client.get(f"/api/translate/works/{work_id}/glossary")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get(f"/api/translate/variants/{variant_id}/estimate")
    assert r.status_code == 200
    est = r.json()
    assert est["chapter_count"] == 2
    assert est["estimated_tokens"] > 0
    assert est["over_budget"] is False

    # estimate theo work (không cần variant đã tồn tại — dùng cho modal trước khi tạo variant)
    r = client.get(f"/api/translate/works/{work_id}/estimate")
    assert r.status_code == 200
    west = r.json()
    assert west["work_id"] == work_id
    assert west["variant_id"] is None
    assert west["chapter_count"] == est["chapter_count"]
    assert west["estimated_tokens"] == est["estimated_tokens"]

    # audio_cut chạy thêm 1 pass must_keep_beats (spec 4.3) -> estimate phải cao hơn full
    r = client.get(f"/api/translate/works/{work_id}/estimate", params={"mode": "audio_cut"})
    assert r.status_code == 200
    west_cut = r.json()
    assert west_cut["estimated_tokens"] > west["estimated_tokens"]

    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert status == "completed"

    segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
    assert len(segs) == 2
    # Mock applies protected replacement
    detail = client.get(f"/api/translate/segments/{segs[0]['id']}").json()
    assert "Lý Minh" in (detail["output_text"] or "")

    r = client.put(
        f"/api/translate/segments/{segs[0]['id']}",
        json={"output_text": "Bản sửa tay", "reviewed": True},
    )
    assert r.status_code == 200
    assert r.json()["reviewed"] is True
    assert r.json()["output_text"] == "Bản sửa tay"

    # Resume with nothing left to retry → 400
    r = client.post(f"/api/translate/jobs/{job_id}/resume")
    assert r.status_code == 400
