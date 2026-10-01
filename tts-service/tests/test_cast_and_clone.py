"""Gán nhân vật bằng AI giả, và lưu clip giọng. Không tải VieNeu."""
import json
import wave
from io import BytesIO

from platform_.config import config
from tts.infrastructure.engines import mock as mock_engine
from tts.infrastructure.engines.vieneu import gender_from_label

from test_speak_job import _reading_job, _wait


def _wav(seconds: float) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def test_gender_from_label():
    assert gender_from_label("Bắc (Nam miền Bắc)") == "Male"
    assert gender_from_label("Nữ miền Nam") == "Female"
    assert gender_from_label("Minh Quân") == "Unknown"


def test_vieneu_gpu_rejected_when_cuda_missing(client, monkeypatch):
    monkeypatch.setattr("tts.infrastructure.engines.vieneu.gpu_ready", lambda: False)
    monkeypatch.setattr("tts.api.routers.gpu_ready", lambda: False)
    work = client.post(
        "/api/tts/works/import-txt",
        json={"title": "GPU", "lang": "vi", "text": "Một câu."},
    ).json()
    response = client.post(
        f"/api/tts/works/{work['id']}/readings",
        json={"engine": "vieneu", "voice": "Adam", "device": "gpu"},
    )
    assert response.status_code == 400
    assert "CUDA" in response.json()["detail"]
    engines = client.get("/api/tts/engines").json()
    assert engines["vieneu_gpu"] is False


def test_vieneu_voices_503_when_package_missing(client, monkeypatch):
    monkeypatch.setattr("tts.api.routers.vieneu_available", lambda: False)
    response = client.get("/api/tts/voices?engine=vieneu&lang=vi")
    assert response.status_code == 503
    assert "vieneu" in response.json()["detail"]


def test_clone_stores_a_short_wav(client):
    ok = client.post(
        "/api/tts/voices/clone",
        files={"file": ("me.wav", _wav(4), "audio/wav")},
        data={"name": "Tôi"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["id"] == "clone:1"
    assert ok.json()["label"] == "Tôi"
    assert (config.resolved_audio_dir() / "voices" / "1.wav").is_file()

    short = client.post(
        "/api/tts/voices/clone",
        files={"file": ("me.wav", _wav(1), "audio/wav")},
        data={"name": "Ngắn"},
    )
    assert short.status_code == 400


def test_cast_switches_voice_and_resume_does_not_retag(client, monkeypatch):
    calls = {"n": 0}

    def fake(_provider_id, messages):
        calls["n"] += 1
        system = messages[0]["content"]
        if "Nhân vật đã biết" in system:
            return json.dumps(
                [
                    {"speaker": "narrator", "text": "Trời mưa."},
                    {"speaker": "Lan", "text": "Đi đi."},
                    {"speaker": "Minh", "text": "Được."},
                ],
                ensure_ascii=False,
            )
        return json.dumps(
            [
                {"name": "Lan", "gender": "female"},
                {"name": "Minh", "gender": "male"},
            ],
            ensure_ascii=False,
        )

    monkeypatch.setattr("tts.application.cast.complete", fake)
    mock_engine.calls.clear()
    mock_engine.fail_remaining = 1
    work = client.post(
        "/api/tts/works/import-txt",
        json={"title": "Cast", "lang": "vi", "text": "Trời mưa. Đi đi. Được."},
    ).json()
    detected = client.post(f"/api/tts/works/{work['id']}/cast/detect", json={"provider_id": 1})
    assert detected.status_code == 200, detected.text
    names = {row["name"]: row["gender"] for row in detected.json()["cast"]}
    assert names == {"Lan": "female", "Minh": "male"}

    edited = client.put(
        f"/api/tts/works/{work['id']}/cast",
        json={
            "members": [
                {"name": "Lan", "gender": "female", "voice": ""},
                {"name": "Minh", "gender": "male", "voice": ""},
            ]
        },
    )
    assert edited.status_code == 200, edited.text

    started = client.post(
        f"/api/tts/works/{work['id']}/readings",
        json={
            "engine": "mock",
            "voice": "vi-VN-HoaiMyNeural",
            "use_cast": True,
            "provider_id": 1,
            "male_voice": "vi-VN-HoaiMyNeural",
            "female_voice": "vi-VN-NamMinhNeural",
        },
    )
    assert started.status_code == 200, started.text
    job = _reading_job(started.json())
    assert _wait(client, job["id"]) == "failed"
    tagged = calls["n"]
    assert tagged == 2

    mock_engine.calls.clear()
    mock_engine.fail_remaining = 0
    resumed = client.post(f"/api/tts/jobs/{job['id']}/resume")
    assert resumed.status_code == 200, resumed.text
    assert _wait(client, job["id"]) == "completed"
    assert calls["n"] == tagged
    by_text = {row["text"]: row["voice"] for row in mock_engine.calls}
    assert by_text["Trời mưa."] == "vi-VN-HoaiMyNeural"
    assert by_text["Đi đi."] == "vi-VN-NamMinhNeural"
    assert by_text["Được."] == "vi-VN-HoaiMyNeural"
