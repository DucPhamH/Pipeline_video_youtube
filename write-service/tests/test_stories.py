import json
import re
import time


def _fake_ask(db, provider_id, *, system, user):
    del db, provider_id
    if "OUTLINE" in system:
        match = re.search(r"SỐ CHƯƠNG:\s*(\d+)", user)
        count = int(match.group(1)) if match else 4
        return json.dumps(
            [{"title": f"Chương {i}", "beat": f"Việc {i}"} for i in range(1, count + 1)],
            ensure_ascii=False,
        )
    match = re.search(r"CHƯƠNG (\d+)", user)
    index = match.group(1) if match else "1"
    marker = "ĐOẠN CUỐI CHƯƠNG TRƯỚC:"
    prev = user.split(marker, 1)[1].strip()[:80] if marker in user else ""
    return f"Nội dung chương {index}. {prev}".strip()


def _create(client, **extra):
    body = {
        "title": "Mưa ở làng",
        "premise": "Hai người gặp nhau một mùa mưa.",
        "ending": "Họ ở lại làng.",
        "chapter_count": 4,
        "provider_id": 1,
        "characters": [{"name": "Lan", "role": "người kể"}],
    }
    body.update(extra)
    response = client.post("/api/write/stories", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_story_and_reject_short_book(client):
    story = _create(client)
    assert story["chapter_count"] == 4
    assert [c["index"] for c in story["chapters"]] == [1, 2, 3, 4]
    assert story["chapters"][0]["text"] == ""
    listed = client.get("/api/write/stories").json()["items"]
    assert listed[0]["id"] == story["id"]
    assert listed[0]["filled_count"] == 0
    bad = client.post(
        "/api/write/stories",
        json={"title": "Ngắn", "premise": "Một câu.", "chapter_count": 2, "provider_id": 1},
    )
    assert bad.status_code == 422


def test_outline_then_write_keeps_text_when_setup_changes(client, monkeypatch):
    monkeypatch.setattr("write.application.stories.ask", _fake_ask)
    story = _create(client)
    outlined = client.post(f"/api/write/stories/{story['id']}/outline").json()
    assert outlined["chapters"][0]["beat"] == "Việc 1"
    again = client.post(f"/api/write/stories/{story['id']}/outline")
    assert again.status_code == 409
    written = client.post(
        f"/api/write/stories/{story['id']}/chapters/1/write",
        json={"force": False},
    ).json()
    assert written["chapters"][0]["text"].startswith("Nội dung chương 1")
    refused = client.post(
        f"/api/write/stories/{story['id']}/chapters/1/write",
        json={"force": False},
    )
    assert refused.status_code == 409
    patched = client.patch(
        f"/api/write/stories/{story['id']}",
        json={"premise": "Gợi ý khác, vẫn một mùa mưa."},
    ).json()
    assert patched["chapters"][0]["text"].startswith("Nội dung chương 1")
    assert patched["premise"].startswith("Gợi ý khác")


def test_second_chapter_sees_previous_tail(client, monkeypatch):
    monkeypatch.setattr("write.application.stories.ask", _fake_ask)
    story = _create(client)
    client.post(f"/api/write/stories/{story['id']}/outline")
    client.patch(
        f"/api/write/stories/{story['id']}/chapters/1",
        json={"text": "Lan đứng ngoài hiên nhìn mưa."},
    )
    written = client.post(f"/api/write/stories/{story['id']}/chapters/2/write", json={}).json()
    assert "Lan đứng ngoài hiên" in written["chapters"][1]["text"]


def test_write_all_fills_empty_chapters(client, monkeypatch):
    monkeypatch.setattr("write.application.stories.ask", _fake_ask)
    story = _create(client)
    client.post(f"/api/write/stories/{story['id']}/outline")
    started = client.post(f"/api/write/stories/{story['id']}/write")
    assert started.status_code == 200
    deadline = time.time() + 5
    body = started.json()
    while body["status"] != "idle" and time.time() < deadline:
        time.sleep(0.05)
        body = client.get(f"/api/write/stories/{story['id']}").json()
    assert body["status"] == "idle"
    assert all(chapter["text"] for chapter in body["chapters"])


def _force_status(story_id, status):
    from platform_.db import SessionLocal
    from write.infrastructure.persistence.models import StoryModel

    db = SessionLocal()
    db.get(StoryModel, story_id).status = status
    db.commit()
    db.close()


def test_stop_without_live_thread_goes_idle(client):
    story = _create(client)
    _force_status(story["id"], "writing")
    body = client.post(f"/api/write/stories/{story['id']}/stop").json()
    assert body["status"] == "idle"
    _force_status(story["id"], "stopping")
    body = client.post(f"/api/write/stories/{story['id']}/stop").json()
    assert body["status"] == "idle"


def test_restart_recovers_stuck_stories(client):
    from platform_.db import SessionLocal
    from write.application.stories import INTERRUPTED, recover_interrupted

    writing = _create(client)
    stopping = _create(client)
    _force_status(writing["id"], "writing")
    _force_status(stopping["id"], "stopping")
    db = SessionLocal()
    try:
        assert recover_interrupted(db) == 2
    finally:
        db.close()
    for story in (writing, stopping):
        body = client.get(f"/api/write/stories/{story['id']}").json()
        assert body["status"] == "idle"
        assert body["write_error"] == INTERRUPTED


def test_stop_keeps_finished_chapter(client, monkeypatch):
    story = _create(client)
    story_id = story["id"]

    def stop_during_ask(db, provider_id, *, system, user):
        del db, provider_id, system, user
        from platform_.db import SessionLocal
        from write.infrastructure.persistence.models import StoryModel

        other = SessionLocal()
        row = other.get(StoryModel, story_id)
        row.status = "stopping"
        other.commit()
        other.close()
        return "Chương đã viết xong trước khi dừng."

    monkeypatch.setattr("write.application.stories.ask", stop_during_ask)
    from platform_.db import SessionLocal
    from write.application.stories import run_write_all
    from write.infrastructure.persistence.models import StoryModel

    db = SessionLocal()
    row = db.get(StoryModel, story_id)
    row.status = "writing"
    db.commit()
    db.close()
    run_write_all(story_id)
    body = client.get(f"/api/write/stories/{story_id}").json()
    assert body["status"] == "idle"
    assert body["chapters"][0]["text"].startswith("Chương đã viết xong")
    assert body["chapters"][1]["text"] == ""


def test_stream_chapter_joins_deltas_and_refuses_a_second_time(client, monkeypatch):
    def chunks(provider_id, messages, *, temperature=0.8):
        del provider_id, messages, temperature
        yield "Nội dung "
        yield "chương chảy."

    monkeypatch.setattr("write.application.stories.iter_content", chunks)
    story = _create(client)
    client.patch(f"/api/write/stories/{story['id']}/chapters/1", json={"beat": "mưa"})
    resp = client.post(f"/api/write/stories/{story['id']}/chapters/1/stream", json={"force": False})
    assert resp.status_code == 200, resp.text
    assert resp.text.count("data:") >= 3
    saved = client.get(f"/api/write/stories/{story['id']}").json()
    assert saved["chapters"][0]["text"] == "Nội dung chương chảy."
    again = client.post(f"/api/write/stories/{story['id']}/chapters/1/stream", json={"force": False})
    assert again.status_code == 409
