"""Pool: slot 404 thì chương của nó chuyển sang slot còn sống."""
import json
import sqlite3
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from translate.application.fingerprint import cache_key, glossary_hash
from translate.application.modes import mode_params_hash
from translate.domain.entities import PROMPT_VERSION


class _DeadHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = b'{"error":{"message":"model_not_found"}}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _LiveHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        user = next((m["content"] for m in payload.get("messages", []) if m.get("role") == "user"), "")
        model = payload.get("model") or ""
        raw = json.dumps({"choices": [{"message": {"content": f"[LIVE:{model}] {user}"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve(handler) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 40
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            return status
        time.sleep(0.05)
    return status


def test_dead_pool_slot_hands_chapters_to_a_living_slot(client):
    dead, dead_port = _serve(_DeadHandler)
    live, live_port = _serve(_LiveHandler)
    try:
        ids = []
        for label, port in (("Dead", dead_port), ("Live", live_port)):
            r = client.post(
                "/api/translate/ai-providers",
                json={
                    "label": label,
                    "kind": "local",
                    "base_url": f"http://127.0.0.1:{port}/v1",
                    "model": label.lower(),
                    "api_key": "",
                    "requires_api_key": False,
                },
            )
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])

        text = "\n\n".join(f"# Ch{i}\n\nBody {i} unique." for i in range(1, 5))
        work = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Dead Slot", "lang_src": "en", "lang_tgt": "vi", "text": text},
        ).json()
        variant_id = work["variants"][0]["id"]
        job = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_ids": ids, "ai_mode": "pool"},
        ).json()
        assert _wait(client, job["id"]) == "completed", client.get(f"/api/translate/jobs/{job['id']}").text

        segs = client.get(f"/api/translate/jobs/{job['id']}/segments").json()
        assert len(segs) == 4
        assert all(s["status"] in ("done", "skipped_cache") for s in segs)
        for seg in segs:
            detail = client.get(f"/api/translate/segments/{seg['id']}").json()
            assert "[LIVE:live]" in (detail["output_text"] or "")
        db = Path(tempfile.gettempdir()) / "translate_service_test.sqlite3"
        slots = sqlite3.connect(db).execute(
            "select slot_index from segments where job_id = ?", (job["id"],)
        ).fetchall()
        assert slots and all(row[0] == 1 for row in slots)
        conn = sqlite3.connect(db)
        rows = conn.execute(
            """
            select s.source_text, s.cache_key, v.mode, v.lang_tgt, w.lang_src, v.mode_params
            from segments s
            join jobs j on j.id = s.job_id
            join variants v on v.id = j.variant_id
            join works w on w.id = v.work_id
            where s.job_id = ?
            """,
            (job["id"],),
        ).fetchall()
        conn.close()
        ghash = glossary_hash([])
        for source_text, stored, mode, lang_tgt, lang_src, raw_params in rows:
            params = json.loads(raw_params) if raw_params else {}
            expected = cache_key(
                source_text=source_text,
                mode=mode,
                lang_src=lang_src,
                lang_tgt=lang_tgt,
                model="live",
                prompt_version=PROMPT_VERSION,
                glossary_hash_value=ghash,
                mode_params_hash_value=mode_params_hash(params),
            )
            assert stored == expected
    finally:
        dead.shutdown()
        live.shutdown()
