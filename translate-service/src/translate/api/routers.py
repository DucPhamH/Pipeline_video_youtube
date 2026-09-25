"""FastAPI routes — prefix /api/translate."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from platform_.db import get_db
from platform_.settings_store import get_all, set_setting
from translate.api.schemas import (
    AiProviderAddKeyIn,
    AiProviderIn,
    AiProviderOut,
    AiProviderPatchIn,
    EstimateOut,
    FromCrawlIn,
    FromCrawlOut,
    GlossaryTermIn,
    GlossaryTermOut,
    ImportTxtIn,
    InboxOut,
    JobModelPatchIn,
    JobOut,
    JobProviderPatchIn,
    JobProviderSlotOut,
    JobResumeIn,
    JobStartIn,
    ModelsOut,
    SegmentDetailOut,
    SegmentOut,
    SegmentPutIn,
    SettingsOut,
    SettingsPutIn,
    StyleProfileOut,
    VariantCloneIn,
    VariantCreateIn,
    VariantOut,
    WorkListOut,
    WorkOut,
    ChapterSourceOut,
)
from translate.application.export_json import export_variant_json
from translate.application.export_txt import export_variant_txt
from translate.application.from_crawl import HandoffChapterIn as HandoffChapterApp
from translate.application.from_crawl import from_crawl
from translate.application.import_txt import import_txt
from translate.application.inbox import build_inbox
from translate.application.modes import STYLE_PROFILES
from translate.application.run_job import (
    SUGGESTED_BASE_URLS,
    SUGGESTED_MODELS,
    _api_key_hint,
    cancel_job,
    delete_job,
    enqueue_job,
    estimate_variant,
    estimate_work,
    pause_job,
    resume_job,
    set_job_provider,
    start_job_thread,
)
from translate.application.variants import clone_variant, create_variant
from translate.application.works import delete_work
from translate.domain.entities import AiProvider, GlossaryTerm, SegmentStatus
from translate.infrastructure.persistence.repositories import (
    AiProviderRepository,
    JobProviderSlotRepository,
    ChapterSourceRepository,
    GlossaryRepository,
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)

router = APIRouter(prefix="/api/translate", tags=["translate"])


def _job_out(db: Session, job_id: int) -> JobOut:
    job = JobRepository(db).get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    segs = SegmentRepository(db).list_by_job(job_id)
    done = sum(
        1 for s in segs if s.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE)
    )
    failed = sum(1 for s in segs if s.status == SegmentStatus.FAILED)
    current = next(
        (s.chapter_index for s in segs if s.status == SegmentStatus.PENDING),
        None,
    )
    slots = JobProviderSlotRepository(db).list_by_job(job_id)
    attempted = [s.slot_index for s in segs if s.status != SegmentStatus.PENDING]
    current_slot_index = max(attempted) if attempted else (0 if slots else None)
    return JobOut(
        id=job.id,  # type: ignore[arg-type]
        variant_id=job.variant_id,
        status=job.status.value,
        provider=job.provider,
        model=job.model,
        base_url=job.base_url or "",
        has_api_key=bool((job.api_key or "").strip()),
        api_key_hint=_api_key_hint(job.api_key),
        prompt_version=job.prompt_version,
        error=job.error,
        done_segments=done,
        total_segments=len(segs),
        failed_segments=failed,
        current_chapter=current,
        ai_provider_id=job.ai_provider_id,
        ai_mode=job.ai_mode,
        current_slot_index=current_slot_index,
        provider_slots=[
            JobProviderSlotOut(
                slot_index=s.slot_index,
                label=s.label,
                provider=s.provider,
                model=s.model,
                requires_api_key=s.requires_api_key,
                has_api_key=bool((s.api_key or "").strip()),
            )
            for s in slots
        ],
    )


def _provider_for_kind(kind: str) -> str:
    return "mock" if kind == "mock" else "openai"


def _clean_keys(keys: list[str] | None, fallback: str) -> list[str]:
    """Dedupe, giữ thứ tự; rỗng -> [fallback] nếu fallback có giá trị."""
    seen: set[str] = set()
    out: list[str] = []
    for k in keys or []:
        k2 = str(k).strip()
        if k2 and k2 not in seen:
            seen.add(k2)
            out.append(k2)
    if not out and fallback.strip():
        out = [fallback.strip()]
    return out


def _ai_provider_out(p: AiProvider) -> AiProviderOut:
    keys = p.api_keys or ([p.api_key] if p.api_key else [])
    return AiProviderOut(
        id=p.id,  # type: ignore[arg-type]
        label=p.label,
        kind=p.kind,
        provider=p.provider,
        base_url=p.base_url,
        model=p.model,
        requires_api_key=p.requires_api_key,
        has_api_key=bool((p.api_key or "").strip()),
        api_key_hint=_api_key_hint(p.api_key),
        api_key_hints=[_api_key_hint(k) for k in keys],
        key_count=len(keys) or 1,
        sort_order=p.sort_order,
    )


def _work_out(db: Session, work_id: int) -> WorkOut:
    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    variant_repo = VariantRepository(db)
    job_repo = JobRepository(db)
    work = work_repo.get(work_id)
    if work is None:
        raise HTTPException(404, "Work not found")
    chapters = chapter_repo.list_by_work(work_id)
    variants = variant_repo.list_by_work(work_id)
    variant_outs: list[VariantOut] = []
    for v in variants:
        latest = job_repo.latest_for_variant(v.id)  # type: ignore[arg-type]
        variant_outs.append(
            VariantOut(
                id=v.id,  # type: ignore[arg-type]
                work_id=v.work_id,
                mode=v.mode,
                status=v.status.value,
                lang_tgt=v.lang_tgt,
                mode_params=v.mode_params or {},
                source_variant_id=v.source_variant_id,
                latest_job_id=latest.id if latest else None,
            )
        )
    return WorkOut(
        id=work.id,  # type: ignore[arg-type]
        external_id=work.external_id,
        title=work.title,
        author=work.author,
        lang_src=work.lang_src,
        lang_tgt=work.lang_tgt,
        source_type=work.source_type.value,
        status=work.status.value,
        missing_cleaned=work.missing_cleaned,
        unreviewed_chapters=work.unreviewed_chapters,
        chapters=[
            ChapterSourceOut(
                id=c.id,  # type: ignore[arg-type]
                index=c.index,
                title=c.title,
                fingerprint=c.fingerprint,
                text_preview=(c.text or "")[:200],
            )
            for c in chapters
        ],
        variants=variant_outs,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/works/import-txt", response_model=WorkOut, status_code=201)
def api_import_txt(body: ImportTxtIn, db: Session = Depends(get_db)):
    try:
        result = import_txt(
            db,
            title=body.title,
            author=body.author,
            lang_src=body.lang_src,
            lang_tgt=body.lang_tgt or "vi",
            text=body.text,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _work_out(db, result.work.id)  # type: ignore[arg-type]


@router.post("/works/from-crawl", response_model=FromCrawlOut)
def api_from_crawl(body: FromCrawlIn, db: Session = Depends(get_db)):
    try:
        result = from_crawl(
            db,
            external_id=body.external_id,
            title=body.title,
            author=body.author,
            lang_src=body.lang_src,
            lang_tgt_hint=body.lang_tgt_hint or "vi",
            chapters=[
                HandoffChapterApp(
                    index=c.index,
                    title=c.title,
                    text=c.text,
                    fingerprint=c.fingerprint,
                )
                for c in body.chapters
            ],
            callback_url=body.callback_url,
            missing_cleaned=body.missing_cleaned,
            unreviewed=body.unreviewed,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    base = _work_out(db, result.work.id)  # type: ignore[arg-type]
    return FromCrawlOut(
        **base.model_dump(),
        created=result.created,
        changed_chapter_indices=result.changed_chapter_indices,
    )


@router.get("/works", response_model=WorkListOut)
def api_list_works(db: Session = Depends(get_db)):
    works = WorkRepository(db).list_all()
    return WorkListOut(items=[_work_out(db, w.id) for w in works if w.id is not None])  # type: ignore[misc]


@router.get("/inbox", response_model=InboxOut)
def api_inbox(db: Session = Depends(get_db)):
    return InboxOut(**build_inbox(db))


@router.get("/works/{work_id}", response_model=WorkOut)
def api_get_work(work_id: int, db: Session = Depends(get_db)):
    return _work_out(db, work_id)


@router.delete("/works/{work_id}", status_code=204)
def api_delete_work(work_id: int, db: Session = Depends(get_db)):
    try:
        delete_work(db, work_id=work_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(status_code=204)


@router.post("/works/{work_id}/variants", response_model=VariantOut, status_code=201)
def api_create_variant(work_id: int, body: VariantCreateIn, db: Session = Depends(get_db)):
    try:
        v = create_variant(
            db,
            work_id=work_id,
            mode=body.mode,
            mode_params=body.mode_params,
            lang_tgt=body.lang_tgt,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return VariantOut(
        id=v.id,  # type: ignore[arg-type]
        work_id=v.work_id,
        mode=v.mode,
        status=v.status.value,
        lang_tgt=v.lang_tgt,
        mode_params=v.mode_params or {},
        source_variant_id=v.source_variant_id,
        latest_job_id=None,
    )


@router.post("/variants/{variant_id}/clone", response_model=VariantOut, status_code=201)
def api_clone_variant(variant_id: int, body: VariantCloneIn | None = None, db: Session = Depends(get_db)):
    opts = body or VariantCloneIn()
    try:
        v = clone_variant(
            db,
            variant_id=variant_id,
            mode=opts.mode,
            mode_params=opts.mode_params,
            lang_tgt=opts.lang_tgt,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return VariantOut(
        id=v.id,  # type: ignore[arg-type]
        work_id=v.work_id,
        mode=v.mode,
        status=v.status.value,
        lang_tgt=v.lang_tgt,
        source_variant_id=v.source_variant_id,
        mode_params=v.mode_params or {},
        latest_job_id=None,
    )


@router.get("/style-profiles", response_model=list[StyleProfileOut])
def api_style_profiles():
    return [
        StyleProfileOut(id=pid, label=meta["label"], instruction=meta["instruction"])
        for pid, meta in STYLE_PROFILES.items()
    ]


@router.get("/works/{work_id}/glossary", response_model=list[GlossaryTermOut])
def api_list_glossary(work_id: int, db: Session = Depends(get_db)):
    if WorkRepository(db).get(work_id) is None:
        raise HTTPException(404, "Work not found")
    terms = GlossaryRepository(db).list_by_work(work_id)
    return [
        GlossaryTermOut(
            id=t.id,  # type: ignore[arg-type]
            work_id=t.work_id,
            source_term=t.source_term,
            target_term=t.target_term,
            protected=t.protected,
            notes=t.notes,
        )
        for t in terms
    ]


@router.post("/works/{work_id}/glossary", response_model=GlossaryTermOut, status_code=201)
def api_add_glossary(work_id: int, body: GlossaryTermIn, db: Session = Depends(get_db)):
    if WorkRepository(db).get(work_id) is None:
        raise HTTPException(404, "Work not found")
    src = body.source_term.strip()
    if not src:
        raise HTTPException(400, "source_term bắt buộc")
    try:
        term = GlossaryRepository(db).add(
            GlossaryTerm(
                id=None,
                work_id=work_id,
                source_term=src,
                target_term=body.target_term.strip(),
                protected=body.protected,
                notes=body.notes or "",
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — unique constraint
        db.rollback()
        raise HTTPException(400, f"Không thêm được term: {exc}") from exc
    return GlossaryTermOut(
        id=term.id,  # type: ignore[arg-type]
        work_id=term.work_id,
        source_term=term.source_term,
        target_term=term.target_term,
        protected=term.protected,
        notes=term.notes,
    )


@router.put("/works/{work_id}/glossary/{term_id}", response_model=GlossaryTermOut)
def api_put_glossary(
    work_id: int, term_id: int, body: GlossaryTermIn, db: Session = Depends(get_db)
):
    repo = GlossaryRepository(db)
    term = repo.get(term_id)
    if term is None or term.work_id != work_id:
        raise HTTPException(404, "Glossary term not found")
    term.source_term = body.source_term.strip()
    term.target_term = body.target_term.strip()
    term.protected = body.protected
    term.notes = body.notes or ""
    if not term.source_term:
        raise HTTPException(400, "source_term bắt buộc")
    repo.update(term)
    db.commit()
    return GlossaryTermOut(
        id=term.id,  # type: ignore[arg-type]
        work_id=term.work_id,
        source_term=term.source_term,
        target_term=term.target_term,
        protected=term.protected,
        notes=term.notes,
    )


@router.delete("/works/{work_id}/glossary/{term_id}", status_code=204)
def api_delete_glossary(work_id: int, term_id: int, db: Session = Depends(get_db)):
    repo = GlossaryRepository(db)
    term = repo.get(term_id)
    if term is None or term.work_id != work_id:
        raise HTTPException(404, "Glossary term not found")
    repo.delete(term_id)
    db.commit()
    return Response(status_code=204)


@router.get("/variants/{variant_id}/estimate", response_model=EstimateOut)
def api_estimate(variant_id: int, db: Session = Depends(get_db)):
    try:
        data = estimate_variant(db, variant_id=variant_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return EstimateOut(**data)


@router.get("/works/{work_id}/estimate", response_model=EstimateOut)
def api_estimate_work(work_id: int, mode: str = "full", db: Session = Depends(get_db)):
    try:
        data = estimate_work(db, work_id=work_id, mode=mode)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return EstimateOut(**data)


@router.get("/models", response_model=ModelsOut)
def api_list_models(db: Session = Depends(get_db)):
    values = get_all(db)
    default = str(values.get("translate.openai_model") or "deepseek-chat")
    suggested = list(dict.fromkeys([default, *SUGGESTED_MODELS]))
    key = str(values.get("translate.openai_api_key") or "")
    return ModelsOut(
        default=default,
        suggested=suggested,
        default_provider=str(values.get("translate.provider") or "mock"),
        default_base_url=str(values.get("translate.openai_base_url") or ""),
        has_default_api_key=bool(key.strip()),
        suggested_base_urls=SUGGESTED_BASE_URLS,
    )


@router.post("/variants/{variant_id}/jobs", response_model=JobOut, status_code=202)
def api_start_job(
    variant_id: int,
    body: JobStartIn | None = None,
    db: Session = Depends(get_db),
):
    opts = body or JobStartIn()
    try:
        job = enqueue_job(
            db,
            variant_id=variant_id,
            model=opts.model,
            provider=opts.provider,
            base_url=opts.base_url,
            api_key=opts.api_key,
            ai_provider_id=opts.ai_provider_id,
            ai_provider_ids=opts.ai_provider_ids,
            ai_selections=(
                [s.model_dump() for s in opts.ai_selections] if opts.ai_selections else None
            ),
            ai_mode=opts.ai_mode,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    start_job_thread(job.id)
    return _job_out(db, job.id)  # type: ignore[arg-type]


@router.post("/jobs/{job_id}/resume", response_model=JobOut, status_code=202)
def api_resume_job(
    job_id: int,
    body: JobResumeIn | None = None,
    db: Session = Depends(get_db),
):
    opts = body or JobResumeIn()
    try:
        job = resume_job(
            db,
            job_id=job_id,
            model=opts.model,
            provider=opts.provider,
            base_url=opts.base_url,
            api_key=opts.api_key,
            ai_provider_id=opts.ai_provider_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    start_job_thread(job.id)
    return _job_out(db, job.id)  # type: ignore[arg-type]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def api_cancel_job(job_id: int, db: Session = Depends(get_db)):
    try:
        job = cancel_job(db, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _job_out(db, job.id)  # type: ignore[arg-type]


@router.post("/jobs/{job_id}/pause", response_model=JobOut)
def api_pause_job(job_id: int, db: Session = Depends(get_db)):
    try:
        job = pause_job(db, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _job_out(db, job.id)  # type: ignore[arg-type]


@router.delete("/jobs/{job_id}", status_code=204)
def api_delete_job(job_id: int, db: Session = Depends(get_db)):
    try:
        delete_job(db, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(status_code=204)


@router.patch("/jobs/{job_id}/provider", response_model=JobOut)
@router.patch("/jobs/{job_id}/model", response_model=JobOut)
def api_patch_job_provider(
    job_id: int,
    body: JobProviderPatchIn | JobModelPatchIn,
    db: Session = Depends(get_db),
):
    try:
        job = set_job_provider(
            db,
            job_id=job_id,
            model=body.model,
            provider=getattr(body, "provider", None),
            base_url=getattr(body, "base_url", None),
            api_key=getattr(body, "api_key", None),
            ai_provider_id=getattr(body, "ai_provider_id", None),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _job_out(db, job.id)  # type: ignore[arg-type]


@router.get("/jobs/{job_id}", response_model=JobOut)
def api_get_job(job_id: int, db: Session = Depends(get_db)):
    return _job_out(db, job_id)


@router.get("/jobs/{job_id}/segments", response_model=list[SegmentOut])
def api_list_segments(job_id: int, db: Session = Depends(get_db)):
    if JobRepository(db).get(job_id) is None:
        raise HTTPException(404, "Job not found")
    segs = SegmentRepository(db).list_by_job(job_id)
    return [
        SegmentOut(
            id=s.id,  # type: ignore[arg-type]
            job_id=s.job_id,
            chapter_index=s.chapter_index,
            status=s.status.value,
            cache_key=s.cache_key,
            error=s.error,
            output_preview=(s.output_text or "")[:200],
            reviewed=s.reviewed,
        )
        for s in segs
    ]


@router.get("/segments/{segment_id}", response_model=SegmentDetailOut)
def api_get_segment(segment_id: int, db: Session = Depends(get_db)):
    seg = SegmentRepository(db).get(segment_id)
    if seg is None:
        raise HTTPException(404, "Segment not found")
    return SegmentDetailOut(
        id=seg.id,  # type: ignore[arg-type]
        job_id=seg.job_id,
        chapter_index=seg.chapter_index,
        status=seg.status.value,
        source_text=seg.source_text,
        output_text=seg.output_text,
        error=seg.error,
        reviewed=seg.reviewed,
    )


@router.put("/segments/{segment_id}", response_model=SegmentDetailOut)
def api_put_segment(segment_id: int, body: SegmentPutIn, db: Session = Depends(get_db)):
    repo = SegmentRepository(db)
    seg = repo.get(segment_id)
    if seg is None:
        raise HTTPException(404, "Segment not found")
    seg.output_text = body.output_text
    seg.reviewed = body.reviewed
    if seg.status == SegmentStatus.FAILED and body.output_text.strip():
        seg.status = SegmentStatus.DONE
        seg.error = None
    repo.update(seg)
    db.commit()
    return SegmentDetailOut(
        id=seg.id,  # type: ignore[arg-type]
        job_id=seg.job_id,
        chapter_index=seg.chapter_index,
        status=seg.status.value,
        source_text=seg.source_text,
        output_text=seg.output_text,
        error=seg.error,
        reviewed=seg.reviewed,
    )


@router.get("/variants/{variant_id}/export.txt")
def api_export_txt(variant_id: int, db: Session = Depends(get_db)):
    if VariantRepository(db).get(variant_id) is None:
        raise HTTPException(404, "Variant not found")
    try:
        data = export_variant_txt(db, variant_id=variant_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="variant-{variant_id}.txt"'},
    )


@router.get("/variants/{variant_id}/export.json")
def api_export_json(variant_id: int, db: Session = Depends(get_db)):
    if VariantRepository(db).get(variant_id) is None:
        raise HTTPException(404, "Variant not found")
    try:
        data = export_variant_json(db, variant_id=variant_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        content=data,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="variant-{variant_id}.json"'},
    )


@router.get("/settings", response_model=SettingsOut)
def api_get_settings(db: Session = Depends(get_db)):
    return SettingsOut(values=get_all(db))


@router.put("/settings", response_model=SettingsOut)
def api_put_settings(body: SettingsPutIn, db: Session = Depends(get_db)):
    for key, value in body.values.items():
        set_setting(db, key, value)
    return SettingsOut(values=get_all(db))


@router.get("/ai-providers", response_model=list[AiProviderOut])
def api_list_ai_providers(db: Session = Depends(get_db)):
    return [_ai_provider_out(p) for p in AiProviderRepository(db).list_all()]


@router.post("/ai-providers", response_model=AiProviderOut, status_code=201)
def api_add_ai_provider(body: AiProviderIn, db: Session = Depends(get_db)):
    repo = AiProviderRepository(db)
    api_keys = _clean_keys(body.api_keys, body.api_key)
    p = repo.add(
        AiProvider(
            id=None,
            label=body.label.strip() or body.kind,
            kind=body.kind,
            provider=_provider_for_kind(body.kind),
            base_url=body.base_url.strip(),
            model=body.model.strip(),
            api_key=api_keys[0] if api_keys else body.api_key,
            api_keys=api_keys,
            requires_api_key=body.requires_api_key,
            sort_order=repo.count(),
        )
    )
    db.commit()
    return _ai_provider_out(p)


@router.put("/ai-providers/{provider_id}", response_model=AiProviderOut)
def api_update_ai_provider(
    provider_id: int, body: AiProviderPatchIn, db: Session = Depends(get_db)
):
    repo = AiProviderRepository(db)
    p = repo.get(provider_id)
    if p is None:
        raise HTTPException(404, "AI provider not found")
    if body.label is not None:
        p.label = body.label.strip() or p.label
    if body.kind is not None:
        p.kind = body.kind
        p.provider = _provider_for_kind(body.kind)
    if body.base_url is not None:
        p.base_url = body.base_url.strip()
    if body.model is not None:
        p.model = body.model.strip()
    if body.api_keys is not None:
        p.api_keys = _clean_keys(body.api_keys, body.api_key if body.api_key is not None else p.api_key)
        if p.api_keys:
            p.api_key = p.api_keys[0]
    elif body.api_key is not None:
        p.api_key = body.api_key
        if p.api_key and p.api_key not in p.api_keys:
            p.api_keys = [p.api_key, *[k for k in p.api_keys if k != p.api_key]]
    if body.requires_api_key is not None:
        p.requires_api_key = body.requires_api_key
    repo.update(p)
    db.commit()
    return _ai_provider_out(p)


@router.delete("/ai-providers/{provider_id}", status_code=204)
def api_delete_ai_provider(provider_id: int, db: Session = Depends(get_db)):
    if not AiProviderRepository(db).delete(provider_id):
        raise HTTPException(404, "AI provider not found")
    db.commit()
    return Response(status_code=204)


@router.post("/ai-providers/{provider_id}/keys", response_model=AiProviderOut, status_code=201)
def api_add_ai_provider_key(
    provider_id: int, body: AiProviderAddKeyIn, db: Session = Depends(get_db)
):
    """Thêm 1 key — KHÔNG dùng PUT full-replace vì key là secret, client chỉ
    có hint bị che, không thể gửi lại nguyên vẹn các key cũ. Server tự đọc
    danh sách hiện có rồi append."""
    repo = AiProviderRepository(db)
    p = repo.get(provider_id)
    if p is None:
        raise HTTPException(404, "AI provider not found")
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "api_key rỗng")
    keys = p.api_keys or ([p.api_key] if p.api_key else [])
    if key not in keys:
        keys.append(key)
    p.api_keys = keys
    if not p.api_key:
        p.api_key = key
    repo.update(p)
    db.commit()
    return _ai_provider_out(p)


@router.delete("/ai-providers/{provider_id}/keys/{index}", response_model=AiProviderOut)
def api_delete_ai_provider_key(provider_id: int, index: int, db: Session = Depends(get_db)):
    repo = AiProviderRepository(db)
    p = repo.get(provider_id)
    if p is None:
        raise HTTPException(404, "AI provider not found")
    keys = p.api_keys or ([p.api_key] if p.api_key else [])
    if index < 0 or index >= len(keys):
        raise HTTPException(404, "Key index không tồn tại")
    keys.pop(index)
    p.api_keys = keys
    p.api_key = keys[0] if keys else ""
    repo.update(p)
    db.commit()
    return _ai_provider_out(p)
