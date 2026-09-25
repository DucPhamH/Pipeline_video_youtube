"""Bug thật user gặp: fallback chain có 12 model, chương 1 lỡ thử hết cả dãy mà
vẫn fail (vd rate-limit tạm thời dồn dập) — code cũ kẹt `current_idx` ở slot
CUỐI CÙNG (thường là model chết hẳn) cho MỌI chương sau đó, không bao giờ thử
lại các model đầu danh sách vẫn đang sống. Verify: chương sau vẫn được thử lại
từ slot 0, không bị kẹt ở slot chết của chương trước.

Phân biệt request theo NỘI DUNG (không phải đếm số lần gọi thô) vì job full
cũng tự kèm 1-2 lệnh gọi phụ auto-glossary (trước/sau khi dịch) tới CHÍNH slot
0 — đếm thô sẽ ăn nhầm ngân sách "fail lần đầu" của lệnh phụ đó.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def _make_flaky_handler(fail_first_n_for_chapter1: int):
    """Chỉ chương 1 (nội dung "Body1") fail đúng N lần đầu rồi từ đó luôn OK —
    mô phỏng lỗi TẠM THỜI (không phải model chết vĩnh viễn). Lệnh gọi phụ
    auto-glossary (không phải translate chương) luôn được trả lời OK, không
    tính vào ngân sách fail."""
    state = {"ch1_attempts": 0}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            system_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "system"), "")
            user_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")

            if "glossary" in system_msg.lower():
                payload = json.dumps([]).encode()  # lệnh phụ auto-glossary — luôn OK
                status = 200
            elif "Body1" in user_msg and state["ch1_attempts"] < fail_first_n_for_chapter1:
                state["ch1_attempts"] += 1
                payload = json.dumps({"error": {"message": "temporary failure"}}).encode()
                status = 400  # không phải 429/5xx -> raise ngay, không tự retry nội bộ
            else:
                payload = json.dumps({"choices": [{"message": {"content": f"[SLOT0-OK] {user_msg}"}}]}).encode()
                status = 200

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return _Handler


class _AlwaysFailHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        payload = json.dumps({"error": {"message": "dead model"}}).encode()
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _add_ai(client, label, port):
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": label, "kind": "local", "base_url": f"http://127.0.0.1:{port}/v1", "model": "m", "api_key": "", "requires_api_key": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait_job(client, job_id: int, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def test_fallback_retries_from_slot_zero_on_next_chapter_after_full_exhaustion(client):
    flaky_server, flaky_port = _start(_make_flaky_handler(fail_first_n_for_chapter1=1))
    dead_server, dead_port = _start(_AlwaysFailHandler)
    try:
        slot0_id = _add_ai(client, "Slot0 Flaky", flaky_port)
        slot1_id = _add_ai(client, "Slot1 Dead", dead_port)

        text = "# Ch1\n\nBody1.\n\n# Ch2\n\nBody2.\n"
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Reset Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
        )
        assert r.status_code == 201, r.text
        variant_id = r.json()["variants"][0]["id"]

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_ids": [slot0_id, slot1_id], "ai_mode": "fallback"},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        job = _wait_job(client, job_id)
        # Chương 1: slot0 fail 1 lần -> slot1 (chết) cũng fail -> hết dãy -> FAILED.
        # Chương 2: PHẢI được thử lại từ slot 0 (giờ đã sống) -> DONE.
        assert job["status"] == "completed", job  # có lỗi (1/2) nhưng vẫn completed
        assert job["failed_segments"] == 1

        segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
        by_chapter = {s["chapter_index"]: s for s in segs}
        assert by_chapter[1]["status"] == "failed"
        assert by_chapter[2]["status"] == "done"
        detail2 = client.get(f"/api/translate/segments/{by_chapter[2]['id']}").json()
        assert detail2["output_text"].startswith("[SLOT0-OK]")
    finally:
        flaky_server.shutdown()
        flaky_server.server_close()
        dead_server.shutdown()
        dead_server.server_close()
