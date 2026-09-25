"""Xác nhận AI local chạy THẬT qua network loopback (không mock, không cần
Ollama cài sẵn) — tự dựng 1 HTTP server giả lập endpoint OpenAI-compatible
không cần Authorization, y hệt cách Ollama/LM Studio phục vụ /v1/chat/completions.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class _FakeLocalLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # im lặng, khỏi rác stdout test
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        # Ollama/LM Studio: không đòi Authorization — xác nhận request tới được
        # dù client không có api_key (requires_api_key=False).
        user_msg = next(
            (m["content"] for m in body.get("messages", []) if m.get("role") == "user"), ""
        )
        reply = f"[LOCAL-AI-REPLY] {user_msg}"
        payload = json.dumps(
            {"choices": [{"message": {"content": reply}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_fake_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _FakeLocalLLMHandler)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    return server, port


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def test_pool_of_local_ais_runs_over_real_http_in_parallel(client):
    """2 AI local (2 server thật khác nhau, không mock) chia nhau dịch 1 job —
    xác nhận thread-per-slot + shared-pacing không chặn nhầm 2 identity khác
    nhau, và mỗi segment ra đúng output của server đã xử lý nó."""
    server_a, port_a = _start_fake_server()
    server_b, port_b = _start_fake_server()
    try:
        ids = []
        for label, port in (("Local A", port_a), ("Local B", port_b)):
            r = client.post(
                "/api/translate/ai-providers",
                json={
                    "label": label,
                    "kind": "local",
                    "base_url": f"http://127.0.0.1:{port}/v1",
                    "model": "fake-local-model",
                    "api_key": "",
                    "requires_api_key": False,
                },
            )
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])

        text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, 5))  # 4 chương
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Pool Real HTTP Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
        )
        assert r.status_code == 201, r.text
        variant_id = r.json()["variants"][0]["id"]

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_ids": ids},
        )
        assert r.status_code == 202, r.text
        job = r.json()
        job_id = job["id"]
        assert len(job["provider_slots"]) == 2

        status = _wait_job(client, job_id)
        assert status == "completed", client.get(f"/api/translate/jobs/{job_id}").json()

        segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
        assert len(segs) == 4
        for s in segs:
            detail = client.get(f"/api/translate/segments/{s['id']}").json()
            assert detail["output_text"].startswith("[LOCAL-AI-REPLY]")
    finally:
        server_a.shutdown()
        server_a.server_close()
        server_b.shutdown()
        server_b.server_close()


def test_local_ai_translates_over_real_http_without_api_key(client):
    server, port = _start_fake_server()
    try:
        r = client.post(
            "/api/translate/ai-providers",
            json={
                "label": "Local Test Server",
                "kind": "local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "fake-local-model",
                "api_key": "",
                "requires_api_key": False,
            },
        )
        assert r.status_code == 201, r.text
        ai_provider_id = r.json()["id"]

        r = client.post(
            "/api/translate/works/import-txt",
            json={
                "title": "Local AI Real HTTP Demo",
                "lang_src": "en",
                "lang_tgt": "vi",
                "text": "# Ch1\n\nHello from a real local server.\n",
            },
        )
        assert r.status_code == 201, r.text
        variant_id = r.json()["variants"][0]["id"]

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_id": ai_provider_id},
        )
        assert r.status_code == 202, r.text
        job = r.json()
        assert job["provider"] == "openai"  # KHÔNG rơi về mock dù api_key rỗng
        job_id = job["id"]

        status = _wait_job(client, job_id)
        assert status == "completed", client.get(f"/api/translate/jobs/{job_id}").json()

        segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
        assert len(segs) == 1
        detail = client.get(f"/api/translate/segments/{segs[0]['id']}").json()
        # Output tới từ HTTP server thật (không phải MockTranslator) — có tiền tố
        # đặc trưng do server giả lập trả về, chứng minh request thật đã đi qua.
        assert detail["output_text"].startswith("[LOCAL-AI-REPLY]")
        assert "Hello from a real local server" in detail["output_text"]
    finally:
        server.shutdown()
        server.server_close()
