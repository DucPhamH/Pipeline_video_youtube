import time

from tts.infrastructure.engines import mock as mock_engine


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/tts/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    return status


def _reading_job(work: dict) -> dict:
    job = work["readings"][0]["latest_job"]
    assert job is not None
    return job


def test_import_txt_mock_job_writes_audio_and_second_run_hits_cache(client):
    mock_engine.calls.clear()
    mock_engine.fail_remaining = 0
    text = "# Một\n\nAnh nói \"đi đi\" rồi đứng im.\n\n# Hai\n\nHết chương hai, không thoại."
    work = client.post(
        "/api/tts/works/import-txt",
        json={"title": "Cache Book", "author": "A", "lang": "vi", "text": text},
    )
    assert work.status_code == 200, work.text
    body = work.json()
    started = client.post(
        f"/api/tts/works/{body['id']}/readings",
        json={
            "engine": "mock",
            "voice": "vi-VN-HoaiMyNeural",
            "dialogue_voice": "vi-VN-NamMinhNeural",
        },
    )
    assert started.status_code == 200, started.text
    job = _reading_job(started.json())
    assert _wait(client, job["id"]) == "completed"
    voices = {c["voice"] for c in mock_engine.calls}
    assert "vi-VN-HoaiMyNeural" in voices
    assert "vi-VN-NamMinhNeural" in voices

    segs = client.get(f"/api/tts/jobs/{job['id']}/segments").json()
    assert len(segs) == 2
    assert all(s["status"] == "done" for s in segs)
    audio = client.get(f"/api/tts/segments/{segs[0]['id']}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/mpeg")
    assert audio.content[:3] == b"ID3"

    again = client.post(
        f"/api/tts/works/{body['id']}/readings",
        json={
            "engine": "mock",
            "voice": "vi-VN-HoaiMyNeural",
            "dialogue_voice": "vi-VN-NamMinhNeural",
        },
    )
    job2 = _reading_job(again.json())
    assert _wait(client, job2["id"]) == "completed"
    segs2 = client.get(f"/api/tts/jobs/{job2['id']}/segments").json()
    assert all(s["status"] == "skipped_cache" for s in segs2)


def test_failed_chapter_does_not_drop_the_rest_and_resume_finishes(client):
    mock_engine.calls.clear()
    mock_engine.fail_remaining = 1
    text = "# Một\n\nChương sẽ lỗi.\n\n# Hai\n\nChương này sống."
    work = client.post(
        "/api/tts/works/import-txt",
        json={"title": "Resume Book", "lang": "vi", "text": text},
    ).json()
    started = client.post(
        f"/api/tts/works/{work['id']}/readings",
        json={"engine": "mock", "preset_id": "nam_ke"},
    )
    assert started.status_code == 200, started.text
    job = _reading_job(started.json())
    assert _wait(client, job["id"]) == "failed"
    segs = client.get(f"/api/tts/jobs/{job['id']}/segments").json()
    assert {s["status"] for s in segs} == {"failed", "done"}

    mock_engine.fail_remaining = 0
    resumed = client.post(f"/api/tts/jobs/{job['id']}/resume")
    assert resumed.status_code == 200, resumed.text
    assert _wait(client, job["id"]) == "completed"


def test_preview_and_voice_list(client):
    voices = client.get("/api/tts/voices", params={"lang": "vi", "engine": "mock"})
    assert voices.status_code == 200
    ids = {v["id"] for v in voices.json()["voices"]}
    assert "vi-VN-HoaiMyNeural" in ids
    assert voices.json()["sample"]
    preview = client.post(
        "/api/tts/voices/preview",
        json={"engine": "mock", "voice": "vi-VN-HoaiMyNeural", "lang": "vi", "rate": "-15%"},
    )
    assert preview.status_code == 200
    assert preview.content[:3] == b"ID3"
