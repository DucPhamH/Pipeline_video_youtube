"""Job runner: lỗi bất ngờ → FAILED (không kẹt RUNNING), rollback session khi
segment lỗi, reset job kẹt lúc khởi động, cache upsert, cancel đọc status
tươi, run cũ sau Cancel→Resume tự thoát, cache_key đúng model/glossary thật,
poll job không nạp mọi segment, sửa tay cập nhật cache."""
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from translate.application.fingerprint import cache_key, glossary_hash
from translate.application.modes import mode_params_hash
from translate.domain.entities import PROMPT_VERSION, JobStatus


def _import(client, n_chapters: int = 2, body: str = "") -> dict:
    tag = uuid.uuid4().hex[:8]
    text = "\n\n".join(
        f"# Ch{i}\n\n{body or 'Body'} {tag} chapter {i}." for i in range(1, n_chapters + 1)
    )
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": f"Robust {tag}", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _wait(client, job_id: int, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def _expected_key(source_text: str, model: str, ghash: str) -> str:
    return cache_key(
        source_text=source_text,
        mode="full",
        lang_src="en",
        lang_tgt="vi",
        model=model,
        prompt_version=PROMPT_VERSION,
        glossary_hash_value=ghash,
        mode_params_hash_value=mode_params_hash({}),
    )


def test_unexpected_crash_marks_job_failed(client, monkeypatch):
    from translate.application import run_job as rj

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(rj, "_auto_seed_glossary_pre_translate", boom)
    work = _import(client)
    job_id = client.post(f"/api/translate/variants/{work['variants'][0]['id']}/jobs").json()["id"]
    job = _wait(client, job_id)
    assert job["status"] == "failed", job
    assert "kaboom" in (job["error"] or "")


def test_segment_error_after_broken_flush_rolls_back_and_continues(client, monkeypatch):
    from translate.infrastructure.persistence.models import GlossaryTermModel
    from translate.infrastructure.persistence.repositories import TranslationCacheRepository

    original = TranslationCacheRepository.put
    state = {"n": 0}

    def broken_first_put(self, key, text):
        state["n"] += 1
        if state["n"] == 1:
            # NOT NULL vi phạm lúc flush → session cần rollback trước khi dùng tiếp.
            self.db.add(GlossaryTermModel(work_id=1, source_term=None))
            self.db.flush()
        return original(self, key, text)

    monkeypatch.setattr(TranslationCacheRepository, "put", broken_first_put)
    work = _import(client)
    job_id = client.post(f"/api/translate/variants/{work['variants'][0]['id']}/jobs").json()["id"]
    job = _wait(client, job_id)
    assert job["status"] == "completed", job
    assert job["failed_segments"] == 1 and job["done_segments"] == 1, job


def test_startup_resets_interrupted_jobs_and_resume_works(client):
    from main import INTERRUPTED_BY_RESTART, _reset_interrupted_jobs
    from platform_.db import SessionLocal
    from translate.application.run_job import enqueue_job
    from translate.infrastructure.persistence.models import JobModel

    work = _import(client)
    db = SessionLocal()
    try:
        job = enqueue_job(db, variant_id=work["variants"][0]["id"])
        db.query(JobModel).filter(JobModel.id == job.id).update({JobModel.status: "running"})
        db.commit()
        _reset_interrupted_jobs(db)
    finally:
        db.close()

    got = client.get(f"/api/translate/jobs/{job.id}").json()
    assert got["status"] == "cancelled"
    assert got["error"] == INTERRUPTED_BY_RESTART
    r = client.post(f"/api/translate/jobs/{job.id}/resume")
    assert r.status_code == 202, r.text
    assert _wait(client, job.id)["status"] == "completed"


def test_cache_put_tolerates_concurrent_insert_of_same_key(client, monkeypatch):
    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.repositories import TranslationCacheRepository

    key = uuid.uuid4().hex
    a, b = SessionLocal(), SessionLocal()
    try:
        TranslationCacheRepository(b).put(key, "from b")
        b.commit()
        # Mô phỏng a đã tra trước khi b commit (thấy "chưa có").
        monkeypatch.setattr(a, "get", lambda *args, **kw: None)
        TranslationCacheRepository(a).put(key, "from a")
        a.commit()
    finally:
        a.close()
        b.close()
    check = SessionLocal()
    try:
        assert TranslationCacheRepository(check).get(key) == "from a"
    finally:
        check.close()


def test_get_status_sees_commits_from_other_sessions(client):
    from platform_.db import SessionLocal
    from translate.application.run_job import enqueue_job
    from translate.infrastructure.persistence.models import JobModel
    from translate.infrastructure.persistence.repositories import JobRepository

    work = _import(client)
    worker, other = SessionLocal(), SessionLocal()
    try:
        job = enqueue_job(worker, variant_id=work["variants"][0]["id"])
        repo = JobRepository(worker)
        assert repo.get(job.id).status == JobStatus.QUEUED  # nạp vào identity map
        other.query(JobModel).filter(JobModel.id == job.id).update({JobModel.status: "cancelled"})
        other.commit()
        assert repo.get_status(job.id) == JobStatus.CANCELLED
    finally:
        worker.close()
        other.close()


def test_stale_generation_counts_as_cancelled():
    from translate.application import run_job as rj

    class _Repo:
        def get_status(self, _job_id):
            return JobStatus.RUNNING

    job_id = 10_000_000 + int(uuid.uuid4().int % 1000)
    old = rj._next_generation(job_id)
    old_check = rj._job_stop_check(_Repo(), job_id, old)
    assert old_check() is False
    new = rj._next_generation(job_id)  # Resume → run mới
    assert old_check() is True
    assert rj._job_stop_check(_Repo(), job_id, new)() is False


class _FailHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        payload = b'{"error":{"message":"simulated invalid key"}}'
        self.send_response(400)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
        if "preparing a translation glossary BEFORE translating" in system:
            reply = json.dumps([{"source_term": "Ryu", "target_term": "Long"}])
        else:
            reply = "[OK]"
        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _add_ai(client, label: str, port: int, model: str) -> int:
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": label,
            "kind": "local",
            "base_url": f"http://127.0.0.1:{port}/v1",
            "model": model,
            "api_key": "",
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _segment_rows(client, job_id: int) -> list[tuple[str, str]]:
    rows = []
    for s in client.get(f"/api/translate/jobs/{job_id}/segments").json():
        detail = client.get(f"/api/translate/segments/{s['id']}").json()
        rows.append((detail["source_text"], s["cache_key"]))
    return rows


def test_fallback_caches_under_model_that_actually_translated(client):
    dead, dead_port = _serve(_FailHandler)
    live, live_port = _serve(_EchoHandler)
    try:
        ids = [
            _add_ai(client, "FB dead", dead_port, "dead-model"),
            _add_ai(client, "FB live", live_port, "live-model"),
        ]
        work = _import(client, n_chapters=3, body="No names")
        job = client.post(
            f"/api/translate/variants/{work['variants'][0]['id']}/jobs",
            json={"ai_provider_ids": ids, "ai_mode": "fallback"},
        ).json()
        assert _wait(client, job["id"])["status"] == "completed"
        ghash = glossary_hash([])
        for source_text, stored in _segment_rows(client, job["id"]):
            assert stored == _expected_key(source_text, "live-model", ghash)
    finally:
        dead.shutdown()
        live.shutdown()


def test_cache_keys_include_glossary_seeded_at_job_start(client):
    server, port = _serve(_EchoHandler)
    try:
        ai = _add_ai(client, "Seed single", port, "seed-model")
        work = _import(client, n_chapters=2, body="Ryu walks")
        job = client.post(
            f"/api/translate/variants/{work['variants'][0]['id']}/jobs",
            json={"ai_provider_id": ai},
        ).json()
        assert _wait(client, job["id"])["status"] == "completed"
        ghash = glossary_hash([("Ryu", "Long", False)])
        for source_text, stored in _segment_rows(client, job["id"]):
            assert stored == _expected_key(source_text, "seed-model", ghash)
    finally:
        server.shutdown()


def test_job_poll_counts_without_loading_segments(client, monkeypatch):
    from translate.infrastructure.persistence.repositories import SegmentRepository

    work = _import(client, n_chapters=3)
    job_id = client.post(f"/api/translate/variants/{work['variants'][0]['id']}/jobs").json()["id"]
    assert _wait(client, job_id)["status"] == "completed"

    def no_full_load(self, job_id):
        raise AssertionError("_job_out không được nạp toàn bộ segment")

    monkeypatch.setattr(SegmentRepository, "list_by_job", no_full_load)
    job = client.get(f"/api/translate/jobs/{job_id}").json()
    assert job["total_segments"] == 3
    assert job["done_segments"] == 3
    assert job["failed_segments"] == 0
    assert job["current_chapter"] is None


def test_manual_segment_edit_updates_translation_cache(client):
    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.repositories import TranslationCacheRepository

    work = _import(client, n_chapters=1)
    job_id = client.post(f"/api/translate/variants/{work['variants'][0]['id']}/jobs").json()["id"]
    assert _wait(client, job_id)["status"] == "completed"
    seg = client.get(f"/api/translate/jobs/{job_id}/segments").json()[0]

    r = client.put(
        f"/api/translate/segments/{seg['id']}",
        json={"output_text": "Bản sửa tay", "reviewed": True},
    )
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert TranslationCacheRepository(db).get(seg["cache_key"]) == "Bản sửa tay"
    finally:
        db.close()
