from ai.infrastructure import chat


def test_chat_records_usage_by_provider_and_caller(client, monkeypatch):
    created = client.post(
        "/api/ai/providers",
        json={"label": "Paid", "kind": "custom", "base_url": "http://models.example/v1", "model": "m1", "api_key": "sk-x"},
    ).json()
    monkeypatch.setattr(chat, "_once", lambda row, key, msgs, temp, model: ("xin chào", model or row.model, 120, 30))

    for caller in ("translate", "translate", "write"):
        resp = client.post(
            "/api/ai/chat",
            json={"provider_id": created["id"], "caller": caller, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    usage = client.get("/api/ai/usage", params={"days": 7}).json()
    assert usage["total"]["calls"] == 3
    assert usage["total"]["prompt_tokens"] == 360
    assert usage["total"]["completion_tokens"] == 90
    by_caller = {r["key"]: r["calls"] for r in usage["by_caller"]}
    assert by_caller == {"translate": 2, "write": 1}
    provider = next(r for r in usage["by_provider"] if r["key"] == str(created["id"]))
    assert provider["label"] == "Paid"
    assert len(usage["by_day"]) == 1


def test_failed_chat_records_nothing(client, monkeypatch):
    created = client.post(
        "/api/ai/providers",
        json={"label": "Down", "kind": "custom", "base_url": "http://models.example/v1", "model": "m", "api_key": "sk-y"},
    ).json()

    def down(*_a):
        raise RuntimeError("Model từ chối (401)")

    monkeypatch.setattr(chat, "_once", down)
    before = client.get("/api/ai/usage").json()["total"]["calls"]
    resp = client.post(
        "/api/ai/chat", json={"provider_id": created["id"], "messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 502
    assert client.get("/api/ai/usage").json()["total"]["calls"] == before
