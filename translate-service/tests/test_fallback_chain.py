"""AI dự phòng tuần tự (ai_mode=fallback) — AI ưu tiên cao chết thì tự chuyển
sang AI kế, không chạy song song như pool. Dùng HTTP server thật (1 luôn lỗi,
1 luôn thành công) để verify đúng hành vi failover, không chỉ mock."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class _AlwaysFailHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        # 400 (không phải 429/5xx) -> Translator raise ngay, không retry/backoff
        # 8 lần trong _chat() — test cần AI "chết" là chuyển AI ngay lập tức.
        payload = json.dumps({"error": {"message": "simulated invalid key", "code": "invalid_api_key"}}).encode()
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _AlwaysOkHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        user_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")
        reply = f"[BACKUP-AI-OK] {user_msg}"
        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _wait_job(client, job_id: int, timeout: float = 15) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def _add_ai(client, label, port):
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": label, "kind": "local", "base_url": f"http://127.0.0.1:{port}/v1", "model": "m", "api_key": "", "requires_api_key": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_fallback_chain_switches_to_backup_when_primary_dies(client):
    dead_server, dead_port = _start(_AlwaysFailHandler)
    ok_server, ok_port = _start(_AlwaysOkHandler)
    try:
        primary_id = _add_ai(client, "Primary (dies)", dead_port)
        backup_id = _add_ai(client, "Backup (ok)", ok_port)

        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Fallback Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nHello.\n"},
        )
        variant_id = r.json()["variants"][0]["id"]

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_ids": [primary_id, backup_id], "ai_mode": "fallback"},
        )
        assert r.status_code == 202, r.text
        job = r.json()
        job_id = job["id"]
        assert job["ai_mode"] == "fallback"
        assert len(job["provider_slots"]) == 2

        status = _wait_job(client, job_id)
        assert status == "completed", client.get(f"/api/translate/jobs/{job_id}").json()

        job_final = client.get(f"/api/translate/jobs/{job_id}").json()
        assert job_final["current_slot_index"] == 1  # đã "định cư" ở AI dự phòng

        segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
        detail = client.get(f"/api/translate/segments/{segs[0]['id']}").json()
        assert detail["output_text"].startswith("[BACKUP-AI-OK]")
    finally:
        dead_server.shutdown()
        dead_server.server_close()
        ok_server.shutdown()
        ok_server.server_close()


def test_pool_mode_is_still_default_when_ai_mode_omitted(client):
    """Không truyền ai_mode -> vẫn là 'pool' (backward-compatible), không phải fallback."""
    ok_server, ok_port = _start(_AlwaysOkHandler)
    try:
        a = _add_ai(client, "Pool A", ok_port)
        b = _add_ai(client, "Pool B", ok_port)
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Default Mode Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nBody.\n"},
        )
        variant_id = r.json()["variants"][0]["id"]
        r = client.post(f"/api/translate/variants/{variant_id}/jobs", json={"ai_provider_ids": [a, b]})
        assert r.status_code == 202, r.text
        assert r.json()["ai_mode"] == "pool"
    finally:
        ok_server.shutdown()
        ok_server.server_close()
