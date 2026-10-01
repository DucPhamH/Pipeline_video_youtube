import io
import json
import threading
import time
import zipfile
from pathlib import Path

from platform_.db import SessionLocal
from tts.application import cast as cast_mod
from tts.application.pieces import split_roles
from tts.application.run_job import recover_interrupted, run_job
from tts.application.speak import SpeakParams, _key_lock, cache_key, render
from tts.infrastructure.engines import mock as mock_engine
from tts.infrastructure.persistence.models import JobModel, ReadingModel


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/tts/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    return status


def _translated_work(client, external_id: str, texts: list[str]) -> dict:
    res = client.post(
        "/api/tts/works/from-translate",
        json={
            "title": external_id,
            "lang": "vi",
            "external_id": external_id,
            "chapters": [{"index": i + 1, "title": f"Ch{i + 1}", "text": t} for i, t in enumerate(texts)],
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_textless_chapter_is_skipped_and_export_uses_done_chapters_of_failed_job(client):
    mock_engine.calls.clear()
    mock_engine.fail_remaining = 1
    work = _translated_work(client, "robust:empty", ["Robust chương lỗi.", "* * *\n……", "Robust chương sống."])
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nam_ke"})
    assert started.status_code == 200, started.text
    reading = started.json()["readings"][0]
    job_id = reading["latest_job"]["id"]
    assert _wait(client, job_id) == "failed"
    mock_engine.fail_remaining = 0
    segs = client.get(f"/api/tts/jobs/{job_id}/segments").json()
    assert [s["status"] for s in segs] == ["failed", "skipped", "done"]

    exported = client.get(f"/api/tts/readings/{reading['id']}/export.zip")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(exported.content)).namelist()
    assert names == ["0003-Ch3.mp3"]

    resumed = client.post(f"/api/tts/jobs/{job_id}/resume")
    assert resumed.status_code == 200, resumed.text
    assert _wait(client, job_id) == "completed"


def test_run_job_crash_marks_failed(client, monkeypatch):
    work = _translated_work(client, "robust:crash", ["Một chương."])
    monkeypatch.setattr("tts.application.run_job.launch", lambda _job_id: None)
    monkeypatch.setattr("tts.api.routers.launch", lambda _job_id: None)
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nam_ke"})
    job_id = started.json()["readings"][0]["latest_job"]["id"]

    def boom(**_kwargs):
        raise RuntimeError("hỏng")

    monkeypatch.setattr("tts.application.run_job.SpeakParams", boom)
    run_job(job_id)
    job = client.get(f"/api/tts/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "hỏng" in job["error"]


def test_recover_interrupted_jobs_on_startup(client, monkeypatch):
    work = _translated_work(client, "robust:recover", ["Một chương."])
    monkeypatch.setattr("tts.application.run_job.launch", lambda _job_id: None)
    monkeypatch.setattr("tts.api.routers.launch", lambda _job_id: None)
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nam_ke"})
    job_id = started.json()["readings"][0]["latest_job"]["id"]
    db = SessionLocal()
    try:
        db.get(JobModel, job_id).status = "running"
        db.commit()
    finally:
        db.close()
    assert recover_interrupted() >= 1
    db = SessionLocal()
    try:
        job = db.get(JobModel, job_id)
        assert job.status == "failed"
        assert job.error
        assert db.get(ReadingModel, job.reading_id).status == "failed"
    finally:
        db.close()


def test_dash_dialogue_lines():
    text = "Trời mưa.\n- Anh đi đâu? - Lan hỏi.\n— Về nhà.\nMột-hai ba."
    assert split_roles(text, dialogue=True) == [
        ("narrator", "Trời mưa."),
        ("dialogue", "Anh đi đâu?"),
        ("narrator", "Lan hỏi."),
        ("dialogue", "Về nhà."),
        ("narrator", "Một-hai ba."),
    ]


def test_tag_chapter_falls_back_to_regex_when_ai_drops_text(monkeypatch):
    source = 'Trời mưa rất to suốt đêm qua. Lan nói "đi đi" rồi quay lưng bước ra cửa.'
    monkeypatch.setattr(
        cast_mod,
        "complete",
        lambda *_a, **_k: json.dumps([{"speaker": "Lan", "text": "đi đi"}], ensure_ascii=False),
    )
    pieces = cast_mod.tag_chapter(source, [{"name": "Lan", "gender": "female", "voice": ""}], 1)
    assert [p["text"] for p in pieces] == ["Trời mưa rất to suốt đêm qua. Lan nói", "đi đi", "rồi quay lưng bước ra cửa."]
    assert pieces[1]["speaker"] == cast_mod.UNKNOWN_DIALOGUE
    params = SpeakParams("mock", "narr", "dlg", "+0%", "+0Hz", "+0%", "")
    voiced = cast_mod.voices_for_pieces(pieces, [], params)
    assert [v for v, _ in voiced] == ["narr", "dlg", "narr"]


def test_tag_chapter_keeps_ai_output_when_it_covers_source(monkeypatch):
    source = 'Trời mưa. "Đi đi." "Được."'
    monkeypatch.setattr(
        cast_mod,
        "complete",
        lambda *_a, **_k: json.dumps(
            [
                {"speaker": "narrator", "text": "Trời mưa."},
                {"speaker": "Lan", "text": "Đi đi."},
                {"speaker": "narrator", "text": "Được."},
            ],
            ensure_ascii=False,
        ),
    )
    pieces = cast_mod.tag_chapter(source, [{"name": "Lan"}], 1)
    assert [p["speaker"] for p in pieces] == ["narrator", "Lan", "narrator"]


def test_render_other_key_not_blocked_by_running_key(client):
    params = SpeakParams("mock", "vi-VN-HoaiMyNeural", "", "+3%", "+0Hz", "+0%", "")
    held = threading.Event()
    release = threading.Event()

    def hold():
        with _key_lock(cache_key("khác", params)):
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        start = time.time()
        path, _key, _cached = render("Nghe thử không bị chặn.", params)
        assert path.is_file()
        assert time.time() - start < 2
    finally:
        release.set()
        t.join()


def test_m4b_normalizes_parts_streams_file_and_cleans_up(client, monkeypatch):
    work = _translated_work(client, "robust:m4b", ["Chương một.", "Chương hai."])
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nu_ke_cham"})
    reading = started.json()["readings"][0]
    assert _wait(client, reading["latest_job"]["id"]) == "completed"

    import tts.application.export_audio as export_audio

    cmds: list[list[str]] = []

    class Proc:
        returncode = 0
        stderr = ""
        stdout = "1.5\n"

    def fake_run(cmd, timeout):
        cmds.append(cmd)
        assert timeout > 0
        if Path(cmd[0]).name != "ffprobe":
            Path(cmd[-1]).write_bytes(b"M4B")
        return Proc()

    monkeypatch.setattr(export_audio, "ffmpeg_bin", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(export_audio.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(export_audio, "_run", fake_run)
    res = client.get(f"/api/tts/readings/{reading['id']}/export.m4b")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "audio/mp4"
    assert res.content == b"M4B"
    transcodes = [c for c in cmds if "-ar" in c]
    assert len(transcodes) == 2
    concat = next(c for c in cmds if "concat" in c)
    assert concat[concat.index("-c:a") + 1] == "copy"
    exports = Path(concat[-1]).parent.parent
    assert not any(exports.iterdir())

    def slow(cmd, timeout):
        raise RuntimeError(f"ffmpeg quá thời gian ({timeout}s)")

    monkeypatch.setattr(export_audio, "_run", slow)
    res = client.get(f"/api/tts/readings/{reading['id']}/export.m4b")
    assert res.status_code == 504
    assert not any(exports.iterdir())
