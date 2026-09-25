"""P3: modes, clone variant, mode-aware mock output + cache.

Fork-from-full (spec 4.3): mọi variant khác `full` phải chờ variant `full`
cùng Work dịch xong sạch rồi mới tự chạy (auto-chain trong run_job()) — test ở
đây đi đúng luồng: request start job đầu tiên trên variant non-full sẽ 400 +
tự kích hoạt full, rồi variant đó tự chạy tiếp sau khi full xong.
"""
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


def _wait_variant_ready(client, work_id: int, variant_id: int, timeout: float = 10) -> str:
    """Chờ variant có latest_job_id (tự start qua auto-chain hoặc trực tiếp) rồi chờ job đó xong."""
    deadline = time.time() + timeout
    job_id = None
    while time.time() < deadline:
        w = client.get(f"/api/translate/works/{work_id}").json()
        v = next(x for x in w["variants"] if x["id"] == variant_id)
        if v["latest_job_id"] is not None:
            job_id = v["latest_job_id"]
            break
        time.sleep(0.05)
    assert job_id is not None, f"variant {variant_id} chưa có job nào (auto-chain fork lỗi?)"
    return _wait_job(client, job_id, timeout=timeout)


def test_create_clone_mode_variants(client):
    text = "# Ch1\n\nHello hero walks into the city.\n"
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Mode Demo",
            "author": "A",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": text,
        },
    )
    assert r.status_code == 201, r.text
    work = r.json()
    work_id = work["id"]
    full_id = work["variants"][0]["id"]
    assert work["variants"][0]["mode_params"] == {}

    r = client.get("/api/translate/style-profiles")
    assert r.status_code == 200
    profiles = r.json()
    assert any(p["id"] == "web_novel_vn_shorts" for p in profiles)

    r = client.post(
        f"/api/translate/works/{work_id}/variants",
        json={"mode": "pov", "mode_params": {"target_pov": "first_person"}},
    )
    assert r.status_code == 201, r.text
    pov = r.json()
    assert pov["mode"] == "pov"
    assert pov["mode_params"]["target_pov"] == "first_person"
    assert pov["source_variant_id"] == full_id  # fork-from-full — không dịch lại từ nguồn

    r = client.post(
        f"/api/translate/variants/{full_id}/clone",
        json={
            "mode": "audio_cut",
            "mode_params": {"target_minutes": 5, "max_chars": 800},
        },
    )
    assert r.status_code == 201, r.text
    cut = r.json()
    assert cut["mode"] == "audio_cut"
    assert cut["mode_params"]["max_chars"] == 800
    assert cut["id"] != full_id
    assert cut["source_variant_id"] == full_id

    # full chưa dịch xong -> start job cho pov bị từ chối, nhưng tự kích hoạt full
    r = client.post(f"/api/translate/variants/{pov['id']}/jobs")
    assert r.status_code == 400, r.text
    assert "Đầy đủ" in r.json()["detail"]

    assert _wait_variant_ready(client, work_id, full_id) == "completed"
    # pov/audio_cut tự chạy tiếp (auto-chain) — không cần bấm lại
    assert _wait_variant_ready(client, work_id, pov["id"]) == "completed"
    assert _wait_variant_ready(client, work_id, cut["id"]) == "completed"

    w = client.get(f"/api/translate/works/{work_id}").json()
    pov_job_id = next(v for v in w["variants"] if v["id"] == pov["id"])["latest_job_id"]
    cut_job_id = next(v for v in w["variants"] if v["id"] == cut["id"])["latest_job_id"]

    segs = client.get(f"/api/translate/jobs/{pov_job_id}/segments").json()
    detail = client.get(f"/api/translate/segments/{segs[0]['id']}").json()
    out = detail["output_text"] or ""
    assert "[fork+pov]" in out  # đã dịch (fork), không dịch lại -> không có [vi+pov]
    assert "(pov:first_person)" in out

    cut_segs = client.get(f"/api/translate/jobs/{cut_job_id}/segments").json()
    cut_detail = client.get(f"/api/translate/segments/{cut_segs[0]['id']}").json()
    assert "[fork+audio_cut]" in (cut_detail["output_text"] or "")

    # Bad mode
    r = client.post(
        f"/api/translate/works/{work_id}/variants",
        json={"mode": "nope"},
    )
    assert r.status_code == 400


def test_mode_params_change_cache_key(client):
    text = "# Ch1\n\nSame source for two style clones.\n"
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Cache Mode",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": text,
        },
    )
    work = r.json()
    work_id = work["id"]
    full_id = work["variants"][0]["id"]

    a = client.post(
        f"/api/translate/works/{work_id}/variants",
        json={
            "mode": "style_clone",
            "mode_params": {"style_profile_id": "web_novel_vn_shorts"},
        },
    ).json()
    b = client.post(
        f"/api/translate/works/{work_id}/variants",
        json={
            "mode": "style_clone",
            "mode_params": {"style_profile_id": "audiobook_narration"},
        },
    ).json()
    assert a["source_variant_id"] == full_id
    assert b["source_variant_id"] == full_id

    # Cả 2 đều fork từ cùng 1 full — request đầu tiên tự start full
    assert client.post(f"/api/translate/variants/{a['id']}/jobs").status_code == 400
    assert client.post(f"/api/translate/variants/{b['id']}/jobs").status_code == 400

    assert _wait_variant_ready(client, work_id, full_id) == "completed"
    assert _wait_variant_ready(client, work_id, a["id"]) == "completed"
    assert _wait_variant_ready(client, work_id, b["id"]) == "completed"

    w = client.get(f"/api/translate/works/{work_id}").json()
    ja = next(v for v in w["variants"] if v["id"] == a["id"])["latest_job_id"]
    jb = next(v for v in w["variants"] if v["id"] == b["id"])["latest_job_id"]

    sa = client.get(f"/api/translate/jobs/{ja}/segments").json()[0]
    sb = client.get(f"/api/translate/jobs/{jb}/segments").json()[0]
    assert sa["cache_key"] != sb["cache_key"]
    assert sa["status"] in ("done", "skipped_cache")
    assert sb["status"] in ("done", "skipped_cache")
