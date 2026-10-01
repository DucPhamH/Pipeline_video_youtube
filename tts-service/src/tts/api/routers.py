"""FastAPI routes — prefix /api/tts."""
from __future__ import annotations

import wave
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from platform_.config import config
from platform_.db import get_db
from tts.api.schemas import (
    ActiveJobOut,
    CastMemberOut,
    CastPutIn,
    ChapterOut,
    CloneOut,
    DetectIn,
    EnginesOut,
    FromTranslateIn,
    ImportTxtIn,
    JobOut,
    PresetOut,
    PreviewIn,
    ReadingIn,
    ReadingOut,
    SegmentOut,
    VoiceOut,
    VoicesOut,
    WorkListItem,
    WorkListOut,
    WorkOut,
)
from tts.application.cast import detect_cast, replace_cast
from tts.application.export_audio import ExportBusy, cleanup_export, export_m4b, export_zip
from tts.application.run_job import audio_file, launch, resume_job
from tts.application.speak import SpeakParams, render
from tts.application.voices import list_voices, presets_for, sample_for
from tts.application.works import from_translate, import_epub, import_txt, normalize_speak, start_reading
from tts.infrastructure.engines.vieneu import VieNeuNotInstalled, available as vieneu_available, gpu_ready
from tts.infrastructure.parsers.txt import ParsedChapter
from tts.infrastructure.persistence.models import (
    ChapterModel,
    ClonedVoiceModel,
    JobModel,
    ReadingModel,
    SegmentModel,
    WorkModel,
)

router = APIRouter(prefix="/api/tts")
_DONE = ("done", "skipped_cache", "skipped")  # skipped = chương rỗng, vẫn tính là xong


def _audio_type(path) -> str:
    return "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"


def _wav_seconds(data: bytes) -> float:
    with wave.open(BytesIO(data), "rb") as src:
        rate = src.getframerate() or 1
        return src.getnframes() / rate


def _job_out(job: JobModel) -> JobOut:
    segs = list(job.segments)
    return JobOut(
        id=job.id,
        reading_id=job.reading_id,
        status=job.status,
        engine=job.engine,
        voice=job.voice,
        dialogue_voice=job.dialogue_voice or "",
        rate=job.rate,
        pitch=job.pitch,
        volume=job.volume,
        style=job.style or "",
        male_voice=job.male_voice or "",
        female_voice=job.female_voice or "",
        use_cast=bool(job.use_cast),
        device=job.device or "cpu",
        error=job.error,
        done_segments=sum(1 for s in segs if s.status in _DONE),
        total_segments=len(segs),
        failed_segments=sum(1 for s in segs if s.status == "failed"),
        skipped_segments=sum(1 for s in segs if s.status == "skipped"),
    )


def _reading_out(reading: ReadingModel) -> ReadingOut:
    latest = max(reading.jobs, key=lambda j: j.id) if reading.jobs else None
    return ReadingOut(
        id=reading.id,
        work_id=reading.work_id,
        engine=reading.engine,
        voice=reading.voice,
        dialogue_voice=reading.dialogue_voice or "",
        rate=reading.rate,
        pitch=reading.pitch,
        volume=reading.volume,
        style=reading.style or "",
        male_voice=reading.male_voice or "",
        female_voice=reading.female_voice or "",
        use_cast=bool(reading.use_cast),
        device=reading.device or "cpu",
        status=reading.status,
        latest_job=_job_out(latest) if latest is not None else None,
    )


def _work_out(work: WorkModel, *, created: bool = True) -> WorkOut:
    readings = sorted(work.readings, key=lambda r: r.id, reverse=True)
    return WorkOut(
        id=work.id,
        title=work.title,
        author=work.author or "",
        lang=work.lang,
        source_type=work.source_type,
        external_id=work.external_id,
        chapters=[ChapterOut(index=c.index, title=c.title) for c in work.chapters],
        readings=[_reading_out(r) for r in readings],
        cast=[
            CastMemberOut(id=m.id, name=m.name, gender=m.gender, voice=m.voice or "")
            for m in work.cast_members
        ],
        created=created,
    )


def _work_or_404(db: Session, work_id: int) -> WorkModel:
    work = db.get(WorkModel, work_id)
    if work is None:
        raise HTTPException(404, "Work không tồn tại")
    return work


@router.get("/engines", response_model=EnginesOut)
def api_engines():
    return EnginesOut(vieneu=vieneu_available(), vieneu_gpu=vieneu_available() and gpu_ready())


@router.get("/voices", response_model=VoicesOut)
async def api_voices(lang: str = "", engine: str = "edge", db: Session = Depends(get_db)):
    if engine not in ("edge", "mock", "vieneu"):
        raise HTTPException(400, "engine phải là mock, edge hoặc vieneu")
    if engine == "vieneu" and not vieneu_available():
        raise HTTPException(503, "Chưa cài vieneu")
    try:
        voices = await list_voices(engine, lang)
    except VieNeuNotInstalled as exc:
        raise HTTPException(503, str(exc)) from exc
    items = [
        VoiceOut(id=v.id, label=v.label, locale=v.locale, gender=v.gender, styles=list(v.styles))
        for v in voices
    ]
    if engine == "vieneu":
        for row in db.query(ClonedVoiceModel).order_by(ClonedVoiceModel.id).all():
            items.append(
                VoiceOut(id=f"clone:{row.id}", label=row.label, locale="vi-VN", gender="Unknown", styles=[])
            )
    return VoicesOut(sample=sample_for(lang), voices=items)


@router.get("/presets", response_model=list[PresetOut])
def api_presets(lang: str = "vi"):
    return [
        PresetOut(
            id=p.id,
            voice=p.voice,
            dialogue_voice=p.dialogue_voice,
            rate=p.rate,
            pitch=p.pitch,
            volume=p.volume,
            style=p.style,
        )
        for p in presets_for(lang)
    ]


@router.post("/voices/preview")
def api_preview(body: PreviewIn):
    try:
        params = normalize_speak(
            lang=body.lang,
            engine=body.engine,
            voice=body.voice,
            dialogue_voice="",
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
            style=body.style,
            preset_id="",
            device=body.device,
        )
        path, _key, _cached = render(
            sample_for(body.lang),
            SpeakParams(
                engine=params["engine"],
                voice=params["voice"],
                dialogue_voice="",
                rate=params["rate"],
                pitch=params["pitch"],
                volume=params["volume"],
                style=params["style"],
                device=params["device"],
            ),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except VieNeuNotInstalled as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    return FileResponse(path, media_type=_audio_type(path), filename=f"preview{path.suffix or '.mp3'}")


@router.get("/works", response_model=WorkListOut)
def api_list_works(db: Session = Depends(get_db)):
    works = db.query(WorkModel).order_by(WorkModel.id.desc()).all()
    items: list[WorkListItem] = []
    for w in works:
        reading = max(w.readings, key=lambda r: r.id) if w.readings else None
        job = max(reading.jobs, key=lambda j: j.id) if reading is not None and reading.jobs else None
        segs = list(job.segments) if job is not None else []
        items.append(
            WorkListItem(
                id=w.id,
                title=w.title,
                author=w.author or "",
                lang=w.lang,
                source_type=w.source_type,
                chapter_count=len(w.chapters),
                latest_status=job.status if job is not None else (reading.status if reading else None),
                latest_done=sum(1 for s in segs if s.status in _DONE),
                latest_total=len(segs),
            )
        )
    return WorkListOut(items=items)


@router.get("/works/{work_id}", response_model=WorkOut)
def api_get_work(work_id: int, db: Session = Depends(get_db)):
    return _work_out(_work_or_404(db, work_id))


def _too_large() -> HTTPException:
    return HTTPException(413, f"File quá lớn (tối đa {config.tts_max_upload_mb} MB)")


async def _read_limited(file: UploadFile) -> bytes:
    """Đọc từng khúc, dừng ngay khi vượt TTS_MAX_UPLOAD_MB thay vì nạp hết vào RAM."""
    limit = config.max_upload_bytes()
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            return bytes(buf)
        buf.extend(chunk)
        if len(buf) > limit:
            raise _too_large()


@router.post("/works/import-txt", response_model=WorkOut)
def api_import_txt(body: ImportTxtIn, db: Session = Depends(get_db)):
    if len(body.text.encode("utf-8")) > config.max_upload_bytes():
        raise _too_large()
    try:
        work = import_txt(db, title=body.title, author=body.author, lang=body.lang, text=body.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _work_out(work)


@router.post("/works/import-epub", response_model=WorkOut)
async def api_import_epub(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    lang: str = Form("vi"),
    db: Session = Depends(get_db),
):
    data = await _read_limited(file)
    if not data:
        raise HTTPException(400, "File EPUB rỗng")
    try:
        work = import_epub(db, data=data, title=title, author=author, lang=lang)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Không đọc được EPUB: {exc}") from exc
    return _work_out(work)


@router.post("/works/from-translate", response_model=WorkOut)
def api_from_translate(body: FromTranslateIn, db: Session = Depends(get_db)):
    chapters = [ParsedChapter(index=c.index, title=c.title, text=c.text) for c in body.chapters]
    try:
        work, created = from_translate(
            db,
            title=body.title,
            author=body.author,
            lang=body.lang,
            external_id=body.external_id,
            chapters=chapters,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _work_out(work, created=created)


@router.put("/works/{work_id}/cast", response_model=WorkOut)
def api_put_cast(work_id: int, body: CastPutIn, db: Session = Depends(get_db)):
    work = _work_or_404(db, work_id)
    try:
        replace_cast(db, work, [m.model_dump() for m in body.members])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.refresh(work)
    return _work_out(work)


@router.post("/works/{work_id}/cast/detect", response_model=WorkOut)
def api_detect_cast(work_id: int, body: DetectIn, db: Session = Depends(get_db)):
    work = _work_or_404(db, work_id)
    try:
        detect_cast(db, work, body.provider_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — AI/mạng
        raise HTTPException(502, str(exc)[:500]) from exc
    db.refresh(work)
    return _work_out(work)


@router.post("/voices/clone", response_model=CloneOut)
async def api_clone_voice(
    file: UploadFile = File(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if len(data) < 1000:
        raise HTTPException(400, "File quá ngắn")
    if len(data) > 8_000_000:
        raise HTTPException(400, "File quá lớn")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            seconds = _wav_seconds(data)
        except wave.Error as exc:
            raise HTTPException(400, "Không đọc được wav") from exc
        if seconds < 3 or seconds > 8:
            raise HTTPException(400, "Clip cần dài 3–8 giây")
        ext = ".wav"
    elif data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        ext = ".mp3"
    else:
        raise HTTPException(400, "Chỉ nhận wav hoặc mp3")
    label = (name or "Giọng của tôi").strip()[:80] or "Giọng của tôi"
    row = ClonedVoiceModel(label=label, audio_path="")
    db.add(row)
    db.flush()
    rel = f"voices/{row.id}{ext}"
    path = config.resolved_audio_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    row.audio_path = rel
    db.commit()
    return CloneOut(id=f"clone:{row.id}", label=row.label)


@router.post("/works/{work_id}/readings", response_model=WorkOut)
def api_start_reading(work_id: int, body: ReadingIn, db: Session = Depends(get_db)):
    work = _work_or_404(db, work_id)
    try:
        params = normalize_speak(
            lang=work.lang,
            engine=body.engine,
            voice=body.voice,
            dialogue_voice=body.dialogue_voice,
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
            style=body.style,
            preset_id=body.preset_id,
            male_voice=body.male_voice,
            female_voice=body.female_voice,
            use_cast=body.use_cast,
            provider_id=body.provider_id,
            device=body.device,
        )
        _reading, job = start_reading(db, work, params)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    launch(job.id)
    db.refresh(work)
    return _work_out(work)


@router.get("/jobs/active", response_model=list[ActiveJobOut])
def api_active_jobs(db: Session = Depends(get_db)):
    """Mọi job queued/running (mới nhất trước). Phải khai báo trước /jobs/{job_id}."""
    jobs = (
        db.query(JobModel)
        .filter(JobModel.status.in_(("queued", "running")))
        .order_by(JobModel.id.desc())
        .all()
    )
    out: list[ActiveJobOut] = []
    for job in jobs:
        segs = list(job.segments)
        reading = job.reading
        work = reading.work if reading is not None else None
        out.append(
            ActiveJobOut(
                job_id=job.id,
                reading_id=job.reading_id,
                work_id=reading.work_id if reading is not None else 0,
                work_title=work.title if work is not None else "",
                status=job.status,
                done_segments=sum(1 for s in segs if s.status in _DONE),
                total_segments=len(segs),
                skipped_segments=sum(1 for s in segs if s.status == "skipped"),
            )
        )
    return out


@router.get("/jobs/{job_id}", response_model=JobOut)
def api_get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobModel, job_id)
    if job is None:
        raise HTTPException(404, "Job không tồn tại")
    return _job_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def api_cancel(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobModel, job_id)
    if job is None:
        raise HTTPException(404, "Job không tồn tại")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, "Job không đang chạy")
    job.status = "cancelled"
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/jobs/{job_id}/resume", response_model=JobOut)
def api_resume(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobModel, job_id)
    if job is None:
        raise HTTPException(404, "Job không tồn tại")
    try:
        job = resume_job(db, job)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _job_out(job)


@router.get("/jobs/{job_id}/segments", response_model=list[SegmentOut])
def api_segments(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobModel, job_id)
    if job is None:
        raise HTTPException(404, "Job không tồn tại")
    reading = db.get(ReadingModel, job.reading_id)
    titles = {}
    if reading is not None:
        rows = db.query(ChapterModel).filter(ChapterModel.work_id == reading.work_id).all()
        titles = {c.index: c.title for c in rows}
    return [
        SegmentOut(
            id=s.id,
            job_id=s.job_id,
            chapter_index=s.chapter_index,
            title=titles.get(s.chapter_index) or f"Chapter {s.chapter_index}",
            status=s.status,
            error=s.error,
            has_audio=bool(s.audio_path),
        )
        for s in job.segments
    ]


@router.get("/segments/{segment_id}/audio")
def api_segment_audio(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(SegmentModel, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment không tồn tại")
    try:
        path = audio_file(seg)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(
        path,
        media_type=_audio_type(path),
        filename=f"chapter-{seg.chapter_index}{path.suffix or '.mp3'}",
    )


@router.get("/readings/{reading_id}/export.zip")
def api_export_zip(reading_id: int, db: Session = Depends(get_db)):
    try:
        path = export_zip(db, reading_id)
    except ExportBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="reading-{reading_id}.zip"'},
        background=BackgroundTask(cleanup_export, path),
    )


@router.get("/readings/{reading_id}/export.m4b")
def api_export_m4b(reading_id: int, db: Session = Depends(get_db)):
    try:
        path = export_m4b(db, reading_id)
    except ExportBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        code = 503 if "chưa có" in msg else 504 if "quá thời gian" in msg else 400
        raise HTTPException(code, msg) from exc
    return FileResponse(
        path,
        media_type="audio/mp4",
        headers={"Content-Disposition": f'attachment; filename="reading-{reading_id}.m4b"'},
        background=BackgroundTask(cleanup_export, path),
    )
