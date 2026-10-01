from platform_.db import SessionLocal
from tts.infrastructure.persistence.models import JobModel, ReadingModel, SegmentModel, WorkModel


def test_active_jobs_lists_only_queued_and_running(client):
    db = SessionLocal()
    try:
        work = WorkModel(title="Active Book", lang="vi")
        db.add(work)
        db.flush()
        reading = ReadingModel(work_id=work.id, voice="vi-VN-HoaiMyNeural", status="running")
        db.add(reading)
        db.flush()
        running = JobModel(reading_id=reading.id, voice="v", status="running")
        queued = JobModel(reading_id=reading.id, voice="v", status="queued")
        finished = JobModel(reading_id=reading.id, voice="v", status="completed")
        db.add_all([running, queued, finished])
        db.flush()
        db.add_all(
            [
                SegmentModel(job_id=running.id, chapter_index=1, status="done"),
                SegmentModel(job_id=running.id, chapter_index=2, status="skipped"),
                SegmentModel(job_id=running.id, chapter_index=3, status="pending"),
            ]
        )
        db.commit()
        ids = (running.id, queued.id, finished.id, work.id, reading.id)
    finally:
        db.close()
    running_id, queued_id, finished_id, work_id, reading_id = ids

    res = client.get("/api/tts/jobs/active")
    assert res.status_code == 200, res.text
    rows = {r["job_id"]: r for r in res.json()}
    assert running_id in rows and queued_id in rows
    assert finished_id not in rows
    row = rows[running_id]
    assert row["work_id"] == work_id
    assert row["reading_id"] == reading_id
    assert row["work_title"] == "Active Book"
    assert row["status"] == "running"
    assert (row["done_segments"], row["total_segments"], row["skipped_segments"]) == (2, 3, 1)
    assert rows[queued_id]["total_segments"] == 0

    listed = {w["id"]: w for w in client.get("/api/tts/works").json()["items"]}
    # Job mới nhất của reading mới nhất là `finished` (id lớn nhất).
    assert listed[work_id]["latest_status"] == "completed"
    assert listed[work_id]["latest_total"] == 0

    db = SessionLocal()
    try:
        for jid in (running_id, queued_id):
            db.get(JobModel, jid).status = "cancelled"
        db.commit()
    finally:
        db.close()
    assert all(r["job_id"] not in (running_id, queued_id) for r in client.get("/api/tts/jobs/active").json())
