from fastapi.testclient import TestClient

import main


def test_health_reports_ffmpeg(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main.shutil, "which", lambda name: None)
    assert client.get("/api/tts/health").json() == {"status": "ok", "ffmpeg": False}
    monkeypatch.setattr(main.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert client.get("/api/health").json()["ffmpeg"] is True
