"""Zip mp3 từng chương, hoặc một file m4b nếu máy có ffmpeg."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from platform_.config import config
from tts.application.speak import absolute_audio
from tts.infrastructure.persistence.models import ChapterModel, JobModel, ReadingModel, SegmentModel, WorkModel

_DONE = ("done", "skipped_cache")
_SAMPLE_RATE = 24000
_PROBE_TIMEOUT = 60
_PART_TIMEOUT = 600
_CONCAT_TIMEOUT = 1800
_AAC_BITRATE = "64k"
# Đổi khi đổi thông số transcode để bỏ cache AAC cũ.
_AAC_VERSION = f"aac-{_SAMPLE_RATE}-{_AAC_BITRATE}-mono-v1"


class ExportBusy(RuntimeError):
    """Reading này đang được xuất (bấm hai lần)."""


_busy_guard = threading.Lock()
_busy: set[int] = set()


@contextmanager
def _export_slot(reading_id: int):
    with _busy_guard:
        if reading_id in _busy:
            raise ExportBusy("Đang xuất file cho lần đọc này — đợi xong rồi thử lại")
        _busy.add(reading_id)
    try:
        yield
    finally:
        with _busy_guard:
            _busy.discard(reading_id)


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def chapter_metadata(durations_ms: list[float], titles: list[str]) -> str:
    """Mốc chương từ độ dài cộng dồn (ms, nhận số lẻ).

    Làm tròn trên tổng cộng dồn chứ không trên từng chương — sách nghìn chương cắt mỗi
    chương 1 ms sẽ lệch cả giây ở cuối.
    """
    lines = [";FFMETADATA1"]
    total = 0.0
    start = 0
    for duration, title in zip(durations_ms, titles, strict=True):
        total += max(float(duration), 0.0)
        end = max(int(round(total)), start + 1)
        safe = title.replace("=", " ").replace("\n", " ")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start}")
        lines.append(f"END={end}")
        lines.append(f"title={safe}")
        start = end
    return "\n".join(lines) + "\n"


def clean_exports() -> None:
    """Lúc khởi động: thư mục tạm của lần xuất bị ngắt giữa chừng không còn ai dọn."""
    root = config.resolved_audio_dir() / "exports"
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _latest_exportable_job(db: Session, reading_id: int) -> JobModel:
    """Job mới nhất đã dừng (xong, lỗi vài chương hoặc huỷ) mà còn chương đọc xong."""
    jobs = (
        db.query(JobModel)
        .filter(JobModel.reading_id == reading_id, JobModel.status.notin_(("queued", "running")))
        .order_by(JobModel.id.desc())
        .all()
    )
    for job in jobs:
        if any(s.status in _DONE and s.audio_path for s in job.segments):
            return job
    raise LookupError("Chưa có lần đọc xong để xuất")


def _ready_segments(db: Session, job: JobModel) -> list[tuple[SegmentModel, str, Path]]:
    reading = db.get(ReadingModel, job.reading_id)
    titles = {}
    if reading is not None:
        rows = db.query(ChapterModel).filter(ChapterModel.work_id == reading.work_id).all()
        titles = {c.index: c.title for c in rows}
    ready = []
    for seg in sorted(job.segments, key=lambda s: s.chapter_index):
        if seg.status not in _DONE or not seg.audio_path:
            continue
        ready.append((seg, titles.get(seg.chapter_index) or f"Chapter {seg.chapter_index}", absolute_audio(seg.audio_path)))
    if not ready:
        raise LookupError("Không có chương đã đọc")
    return ready


def _export_dir() -> Path:
    root = config.resolved_audio_dir() / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=root))


def cleanup_export(path: Path) -> None:
    """Xoá thư mục tạm chứa file xuất (gọi sau khi gửi xong)."""
    shutil.rmtree(path.parent, ignore_errors=True)


def export_zip(db: Session, reading_id: int) -> Path:
    with _export_slot(reading_id):
        return _export_zip(db, reading_id)


def _export_zip(db: Session, reading_id: int) -> Path:
    job = _latest_exportable_job(db, reading_id)
    ready = _ready_segments(db, job)
    folder = _export_dir()
    out = folder / "book.zip"
    try:
        # mp3/wav đã nén sẵn — lưu thẳng, không deflate.
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
            for seg, title, path in ready:
                safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in title)[:40] or "chapter"
                zf.write(path, arcname=f"{seg.chapter_index:04d}-{safe}{path.suffix or '.mp3'}")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return out


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{Path(cmd[0]).name} quá thời gian ({timeout}s)") from exc


def _duration_ms(ffprobe: str, path: Path) -> float:
    """Độ dài file theo container (format=duration) — đúng con số concat demuxer dùng để
    dời timestamp file kế tiếp. Đo trên part AAC đã transcode, không phải mp3 gốc: AAC
    thêm khung priming/padding nên độ dài khác bản gốc vài chục ms mỗi chương."""
    proc = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        _PROBE_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe lỗi")
    try:
        return max(float(proc.stdout.strip().splitlines()[0]) * 1000, 1.0)
    except (ValueError, IndexError) as exc:
        raise RuntimeError("Không đọc được độ dài audio") from exc


def _normalize_part(ffmpeg: str, src: Path, dst: Path) -> None:
    """Đưa mọi chương (mp3/wav, sample rate khác nhau) về cùng một dạng AAC để ghép copy."""
    proc = _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(_SAMPLE_RATE),
            "-c:a",
            "aac",
            "-b:a",
            _AAC_BITRATE,
            str(dst),
        ],
        _PART_TIMEOUT,
    )
    if proc.returncode != 0 or not dst.is_file():
        raise RuntimeError((proc.stderr or "ffmpeg lỗi")[-500:])


def export_m4b(db: Session, reading_id: int) -> Path:
    with _export_slot(reading_id):
        return _export_m4b(db, reading_id)


def _export_m4b(db: Session, reading_id: int) -> Path:
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("ffmpeg chưa có trên máy")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe chưa có trên máy")
    job = _latest_exportable_job(db, reading_id)
    ready = _ready_segments(db, job)
    reading = db.get(ReadingModel, job.reading_id)
    work = db.get(WorkModel, reading.work_id) if reading is not None else None
    folder = _export_dir()
    try:
        return _build_m4b(ffmpeg, ffprobe, folder, ready, work)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _part_key(seg: SegmentModel, src: Path) -> str:
    base = seg.cache_key or hashlib.sha256(str(src).encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{base}\0{_AAC_VERSION}".encode("utf-8")).hexdigest()


def _cached_part(ffmpeg: str, seg: SegmentModel, src: Path) -> Path:
    """AAC của chương, cache theo cache key của segment — xuất lại M4B không transcode lại."""
    root = config.resolved_audio_dir() / "cache" / "aac"
    root.mkdir(parents=True, exist_ok=True)
    part = root / f"{_part_key(seg, src)}.m4a"
    if part.is_file() and part.stat().st_size > 0:
        return part
    tmp = part.with_name(f"{part.stem}.{threading.get_ident()}.part.m4a")
    try:
        _normalize_part(ffmpeg, src, tmp)
        tmp.replace(part)
    finally:
        tmp.unlink(missing_ok=True)
    return part


def _build_m4b(ffmpeg: str, ffprobe: str, folder: Path, ready, work: WorkModel | None) -> Path:
    parts = [_cached_part(ffmpeg, seg, path) for seg, _title, path in ready]
    concat = folder / "list.txt"
    lines = []
    for part in parts:
        escaped = str(part).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Mốc chương = cộng dồn độ dài từng part đúng như concat sẽ thấy (xem _duration_ms).
    durations = [_duration_ms(ffprobe, part) for part in parts]
    meta = folder / "chapters.txt"
    meta.write_text(
        chapter_metadata(durations, [title for _seg, title, _path in ready]),
        encoding="utf-8",
    )
    out = folder / "book.m4b"
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-i",
        str(meta),
        "-map",
        "0:a",
        "-map_metadata",
        "1",
        "-c:a",
        "copy",
        "-f",
        "mp4",
        str(out),
    ]
    proc = _run(cmd, _CONCAT_TIMEOUT)
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError((proc.stderr or "ffmpeg lỗi")[-500:])
    if work is not None and work.cover_path:
        try:
            cover_path = absolute_audio(work.cover_path)
        except ValueError:
            cover_path = None
        if cover_path is not None and cover_path.is_file():
            covered = folder / "covered.m4b"
            try:
                attach = _run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(out),
                        "-i",
                        str(cover_path),
                        "-map",
                        "0",
                        "-map",
                        "1",
                        "-c",
                        "copy",
                        "-disposition:v:0",
                        "attached_pic",
                        "-f",
                        "mp4",
                        str(covered),
                    ],
                    _CONCAT_TIMEOUT,
                )
            except RuntimeError:
                attach = None
            if attach is not None and attach.returncode == 0 and covered.is_file():
                out.unlink(missing_ok=True)
                return covered
    return out
