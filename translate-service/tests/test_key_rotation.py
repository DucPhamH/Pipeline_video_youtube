"""Xoay key cùng 1 model (AiNiee-style): round-robin + failover 429 trong call;
snapshot keys trên job 1-AI; resume pool refresh key từ registry."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from translate.application.key_rotator import KeyRotator, looks_rate_limited


def test_key_rotator_round_robin_and_cooldown():
    r = KeyRotator(["a", "b", "c"])
    assert [r.next_key() for _ in range(3)] == ["a", "b", "c"]
    assert r.next_key() == "a"
    r.cooldown("b", 60)
    # b đang nghỉ → nhảy qua
    got = [r.next_key() for _ in range(4)]
    assert "b" not in got
    assert set(got) <= {"a", "c"}


def test_looks_rate_limited():
    assert looks_rate_limited(RuntimeError("429 rate_limit exceeded"))
    assert looks_rate_limited(Exception("Too Many Requests"))
    assert not looks_rate_limited(Exception("model_not_found 404"))


class _KeyGateHandler(BaseHTTPRequestHandler):
    """bad-key → 429; good-key → 200. Ghi lại thứ tự key đã gọi."""

    calls: list[str] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        auth = self.headers.get("Authorization") or ""
        key = auth.replace("Bearer ", "").strip()
        _KeyGateHandler.calls.append(key)
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if key != "good-key":
            payload = json.dumps({"error": {"message": "rate_limit exceeded", "code": "429"}}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        reply = json.dumps({"choices": [{"message": {"content": f"[ok:{key}]"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


def _start(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _wait(client, job_id: int, timeout: float = 20) -> str:
    deadline = time.time() + timeout
    status = "queued"
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    return status


def test_single_ai_snapshots_all_keys_and_rotates_on_429(client):
    """Không tick use_all_keys: vẫn snapshot mọi key; key đầu 429 → nhảy key sau."""
    server, port = _start(_KeyGateHandler)
    _KeyGateHandler.calls = []
    try:
        r = client.post(
            "/api/translate/ai-providers",
            json={
                "label": "Rotate Demo",
                "kind": "local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "m",
                "api_key": "bad-key",
                "api_keys": ["bad-key", "good-key"],
                "requires_api_key": True,
            },
        )
        assert r.status_code == 201, r.text
        ai_id = r.json()["id"]

        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Rotate", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nKey-rotation unique body XYZ.\n"},
        )
        variant_id = r.json()["variants"][0]["id"]

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_selections": [{"ai_provider_id": ai_id, "model": "m"}]},
        )
        assert r.status_code == 202, r.text
        job = r.json()
        assert job["ai_provider_id"] == ai_id

        from platform_.db import SessionLocal
        from translate.infrastructure.persistence.repositories import JobRepository

        db = SessionLocal()
        try:
            entity = JobRepository(db).get(job["id"])
            assert entity is not None
            assert set(entity.api_keys) == {"bad-key", "good-key"}, entity.api_keys
        finally:
            db.close()

        assert _wait(client, job["id"], timeout=45) == "completed"
        # Phải từng thử bad rồi good
        assert "good-key" in _KeyGateHandler.calls
        assert "bad-key" in _KeyGateHandler.calls
        segs = client.get(f"/api/translate/jobs/{job['id']}/segments").json()
        assert segs[0]["status"] in ("done", "skipped_cache")
        detail = client.get(f"/api/translate/segments/{segs[0]['id']}").json()
        assert "ok:good-key" in (detail.get("output_text") or "")
    finally:
        server.shutdown()
        server.server_close()


def test_resume_pool_refreshes_slot_keys_from_registry(client):
    ai_id = None
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": "Pool Refresh",
            "kind": "mock",
            "model": "m",
            "api_key": "key-old-aaaa",
            "api_keys": ["key-old-aaaa", "key-old-bbbb"],
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    ai_id = r.json()["id"]

    text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, 5))
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Pool Resume Keys", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    variant_id = r.json()["variants"][0]["id"]
    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={"ai_selections": [{"ai_provider_id": ai_id, "use_all_keys": True}], "ai_mode": "pool"},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    client.post(f"/api/translate/jobs/{job_id}/cancel")

    # Đổi key trong Settings
    client.put(
        f"/api/translate/ai-providers/{ai_id}",
        json={"api_keys": ["key-new-aaaa", "key-new-bbbb"], "api_key": "key-new-aaaa"},
    )

    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.repositories import JobProviderSlotRepository

    db = SessionLocal()
    try:
        slots_before = JobProviderSlotRepository(db).list_by_job(job_id)
        assert len(slots_before) == 2
        assert all("old" in (s.api_key or "") for s in slots_before)
    finally:
        db.close()

    r = client.post(f"/api/translate/jobs/{job_id}/resume")
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        slots = JobProviderSlotRepository(db).list_by_job(job_id)
        keys = {s.api_key for s in slots}
        assert keys == {"key-new-aaaa", "key-new-bbbb"}
        assert all(s.ai_provider_id == ai_id for s in slots)
    finally:
        db.close()
