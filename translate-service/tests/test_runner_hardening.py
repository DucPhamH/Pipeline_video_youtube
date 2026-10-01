"""Runner: pool worker chết không báo COMPLETED, cancel lan ra khỏi summarize,
summarize qua đường gọi có giãn cách, polish lỗi không cache, run cũ không đè
run mới, cache_key cùng model hiệu lực, glossary seed dừng được, reset lúc
khởi động báo crawl, EPUB TOC."""
import time
import uuid

import httpx
import pytest

from translate.application.fingerprint import cache_key, glossary_hash
from translate.application.modes import mode_params_hash
from translate.domain.entities import PROMPT_VERSION


def _import(client, n: int = 4) -> dict:
    tag = uuid.uuid4().hex[:8]
    text = "\n\n".join(f"# Ch{i}\n\nBody {tag} chapter {i}." for i in range(1, n + 1))
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": f"Hard {tag}", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _wait(client, job_id: int, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    return job


def _mock_ai(client, label: str) -> int:
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": label, "kind": "mock", "model": "mock", "api_key": "", "requires_api_key": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_pool_worker_crash_fails_its_segments_and_job(client, monkeypatch):
    from translate.application import run_job as rj

    original = rj._run_pool_worker_body

    def flaky(db, job_id, slot, generation=None):
        if slot.slot_index == 1:
            raise RuntimeError("setup exploded")
        return original(db, job_id, slot, generation)

    monkeypatch.setattr(rj, "_run_pool_worker_body", flaky)
    forks = []
    monkeypatch.setattr(rj, "_start_pending_forks", lambda db, **kw: forks.append(kw))
    ids = [_mock_ai(client, f"M{i}-{uuid.uuid4().hex[:4]}") for i in range(2)]
    work = _import(client, n=4)
    job = client.post(
        f"/api/translate/variants/{work['variants'][0]['id']}/jobs",
        json={"ai_provider_ids": ids, "ai_mode": "pool"},
    ).json()
    got = _wait(client, job["id"])
    assert got["status"] == "completed" and got["failed_segments"] == 2, got
    segs = client.get(f"/api/translate/jobs/{job['id']}/segments").json()
    crashed = [s for s in segs if s["status"] == "failed"]
    assert len(crashed) == 2
    assert all(s["error"].startswith("[worker_crashed]") for s in crashed)
    assert not forks  # có segment lỗi → không chạy fork


def test_final_tally_with_pending_segments_is_failed_not_completed(client, monkeypatch):
    from translate.application import run_job as rj

    # Worker "chết im lặng" không đụng segment nào (vd wrapper không bắt kịp).
    monkeypatch.setattr(rj, "_run_pool_worker", lambda job_id, slot, generation=None: None)
    forks = []
    monkeypatch.setattr(rj, "_start_pending_forks", lambda db, **kw: forks.append(kw))
    ids = [_mock_ai(client, f"P{i}-{uuid.uuid4().hex[:4]}") for i in range(2)]
    work = _import(client, n=2)
    job = client.post(
        f"/api/translate/variants/{work['variants'][0]['id']}/jobs",
        json={"ai_provider_ids": ids, "ai_mode": "pool"},
    ).json()
    got = _wait(client, job["id"])
    assert got["status"] == "failed", got
    assert "Chưa xong" in (got["error"] or "")
    assert not forks
    work_after = client.get(f"/api/translate/works/{work['id']}").json()
    assert work_after["variants"][0]["status"] == "failed"


def test_story_state_helper_reraises_cancel_but_swallows_errors():
    from translate.application.run_job import _story_state_or_previous
    from translate.infrastructure.providers.openai_compat import TranslationCancelled

    def cancelled():
        raise TranslationCancelled()

    def broken():
        raise RuntimeError("summarize 500")

    with pytest.raises(TranslationCancelled):
        _story_state_or_previous("prev", cancelled)
    assert _story_state_or_previous("prev", broken) == "prev"


def test_summarize_goes_through_paced_call_path(monkeypatch):
    from translate.application import run_job as rj
    from translate.application.key_rotator import KeyRotator
    from translate.infrastructure.providers.openai_compat import TranslationCancelled

    calls = []
    original = rj._call_with_shared_pacing

    def spy(**kw):
        calls.append(kw["api_key"])
        return original(**kw)

    monkeypatch.setattr(rj, "_call_with_shared_pacing", spy)
    kwargs = dict(
        provider="mock",
        base_url="",
        model="mock",
        requires_api_key=False,
        keys=["k1", "k2"],
        rotator=KeyRotator(["k1", "k2"]),
        previous_state="old",
        new_chapter_text="new chapter",
    )
    out = rj._summarize_paced(is_cancelled=lambda: False, **kwargs)
    assert "old" in out and calls == ["k1"]  # key xoay vòng, không cố định keys[0]
    rj._summarize_paced(is_cancelled=lambda: False, **kwargs)
    assert calls == ["k1", "k2"]
    with pytest.raises(TranslationCancelled):
        rj._summarize_paced(is_cancelled=lambda: True, **kwargs)


def _transport(handler):
    return httpx.MockTransport(handler)


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_polish_failure_returns_marked_unpolished_text():
    from translate.infrastructure.providers.openai_compat import OpenAICompatTranslator, polish_failed

    def handler(request):
        body = request.read().decode()
        if "literary editor" in body:
            return httpx.Response(400, text="bad polish")
        return _ok("translated body")

    t = OpenAICompatTranslator(base_url="http://x/v1", api_key="k", model="m", transport=_transport(handler))
    out = t.translate(text="src", lang_src="en", lang_tgt="vi", mode_params={"polish": True})
    assert out == "translated body" and polish_failed(out)
    ok = OpenAICompatTranslator(
        base_url="http://x/v1", api_key="k", model="m", transport=_transport(lambda r: _ok("fine"))
    ).translate(text="src", lang_src="en", lang_tgt="vi", mode_params={"polish": True})
    assert not polish_failed(ok)


def test_polish_filters_glossary_and_splits_oversized_chapter():
    import json

    from translate.infrastructure.providers.openai_compat import OpenAICompatTranslator

    systems = []

    def handler(request):
        payload = json.loads(request.read())
        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"]
        systems.append((system, user))
        if len(user) > 1500:
            return httpx.Response(400, text="Request too large for model")
        return _ok(user)

    glossary = [(f"src{i}", f"Tgt{i}", False) for i in range(60)]
    text = "\n\n".join(f"Đoạn {i} có Tgt3 xuất hiện." + " x" * 60 for i in range(20))
    t = OpenAICompatTranslator(base_url="http://x/v1", api_key="k", model="m", transport=_transport(handler))
    out = t._polish(text, lang_tgt="vi", glossary=glossary)
    assert "Đoạn 0" in out and "Đoạn 19" in out
    polish_calls = [s for s, u in systems if len(u) <= 1500]
    assert polish_calls and all("Tgt3" in s and "Tgt7" not in s for s in polish_calls)


def test_accept_output_marks_polish_failed_as_not_cacheable():
    from translate.application.run_job import _accept_output
    from translate.domain.entities import Segment, SegmentStatus, Variant, VariantStatus
    from translate.infrastructure.providers.openai_compat import PolishFailedText

    seg = Segment(id=1, job_id=1, chapter_index=1, status=SegmentStatus.PENDING, source_text="hello")
    variant = Variant(id=1, work_id=1, mode="full", status=VariantStatus.RUNNING, lang_tgt="vi")
    text, flags, cacheable = _accept_output(seg, PolishFailedText("xin chào"), variant=variant, lang_src="en")
    assert type(text) is str and text == "xin chào"
    assert flags == ["polish_failed"] and cacheable is False
    _, flags, cacheable = _accept_output(seg, "xin chào", variant=variant, lang_src="en")
    assert flags == [] and cacheable is True


def test_stale_run_cannot_finalize_over_new_run(client):
    from platform_.db import SessionLocal
    from translate.application import run_job as rj
    from translate.domain.entities import JobStatus, VariantStatus
    from translate.infrastructure.persistence.models import JobModel

    work = _import(client, n=1)
    db = SessionLocal()
    try:
        job = rj.enqueue_job(db, variant_id=work["variants"][0]["id"])
        db.query(JobModel).filter(JobModel.id == job.id).update({JobModel.status: "running"})
        db.commit()
        old = rj._next_generation(job.id)
        rj._next_generation(job.id)  # Resume → run mới
        kwargs = dict(
            job_id=job.id,
            variant_id=job.variant_id,
            status=JobStatus.COMPLETED,
            error=None,
            variant_status=VariantStatus.READY,
        )
        assert rj._finalize_job(db, generation=old, **kwargs) is False
        assert rj.JobRepository(db).get_status(job.id) == JobStatus.RUNNING
        assert rj._finalize_job(db, generation=rj._run_generation[job.id], **kwargs) is True
        assert rj.JobRepository(db).get_status(job.id) == JobStatus.COMPLETED
    finally:
        db.close()


def test_refresh_pending_cache_keys_uses_effective_model(client):
    from platform_.db import SessionLocal
    from translate.application import run_job as rj
    from translate.infrastructure.persistence.models import JobModel

    work = _import(client, n=1)
    db = SessionLocal()
    try:
        job = rj.enqueue_job(db, variant_id=work["variants"][0]["id"])
        db.query(JobModel).filter(JobModel.id == job.id).update({JobModel.model: ""})
        db.commit()
        db.expire_all()
        variant = rj.VariantRepository(db).get(job.variant_id)
        w = rj.WorkRepository(db).get(variant.work_id)
        rj._refresh_pending_cache_keys(db, job_id=job.id, variant=variant, work=w, slots=[])
        seg = rj.SegmentRepository(db).list_by_job(job.id)[0]
        expected = cache_key(
            source_text=seg.source_text,
            mode="full",
            lang_src="en",
            lang_tgt="vi",
            model="deepseek-chat",
            prompt_version=PROMPT_VERSION,
            glossary_hash_value=glossary_hash([]),
            mode_params_hash_value=mode_params_hash({}),
        )
        assert seg.cache_key == expected
    finally:
        db.close()


def test_glossary_aux_chat_is_paced_and_cancellable(monkeypatch):
    from translate.application import run_job as rj
    from translate.domain.entities import Job, JobStatus
    from translate.infrastructure.providers.openai_compat import TranslationCancelled

    seen = []
    original = rj._call_with_shared_pacing

    def spy(**kw):
        seen.append(kw["provider"])
        return original(**kw)

    monkeypatch.setattr(rj, "_call_with_shared_pacing", spy)
    job = Job(id=1, variant_id=1, status=JobStatus.RUNNING, provider="openai", model="m",
              base_url="http://127.0.0.1:9/v1", api_key="k")
    t0 = time.time()
    with pytest.raises(TranslationCancelled):
        rj._aux_chat(job, system="s", user="u", is_cancelled=lambda: True)
    assert seen == ["openai"] and time.time() - t0 < 2


def test_startup_reset_notifies_crawl(client, monkeypatch):
    import main
    from platform_.db import SessionLocal
    from translate.application.run_job import enqueue_job
    from translate.infrastructure.persistence.models import JobModel, WorkModel

    work = _import(client, n=1)
    db = SessionLocal()
    try:
        db.query(WorkModel).filter(WorkModel.id == work["id"]).update(
            {WorkModel.callback_url: "http://crawl.invalid/cb"}
        )
        job = enqueue_job(db, variant_id=work["variants"][0]["id"])
        db.query(JobModel).filter(JobModel.id == job.id).update({JobModel.status: "running"})
        db.commit()
        targets = main._reset_interrupted_jobs(db)
    finally:
        db.close()
    assert ("http://crawl.invalid/cb", None) in targets
    sent = []
    monkeypatch.setattr(main, "notify_crawl", lambda **kw: sent.append(kw))
    main._notify_interrupted(targets)
    assert any(s["callback_url"] == "http://crawl.invalid/cb" and s["status"] == "cancelled" for s in sent)


def test_epub_toc_href_resolution_and_single_h1_removed():
    from translate.infrastructure.parsers.epub import _html_to_title_and_text, _resolve_toc_href

    names = {"text/ch 1.xhtml", "nav/nav.xhtml"}
    assert _resolve_toc_href("../text/ch%201.xhtml#p1", names=names, base_dirs=["nav"]) == "text/ch 1.xhtml"
    assert _resolve_toc_href("text/ch%201.xhtml", names=names, base_dirs=[""]) == "text/ch 1.xhtml"
    title, body = _html_to_title_and_text(
        "<html><body><h1>Chương 1</h1><p>Mở đầu.</p><h1>Phần hai</h1><p>Tiếp.</p></body></html>"
    )
    assert title == "Chương 1"
    assert "Chương 1" not in body and "Phần hai" in body
