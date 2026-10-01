def test_provider_hides_key_and_chat_uses_it(client):
    created = client.post(
        "/api/ai/providers",
        json={"label": "Local", "kind": "custom", "base_url": "http://models.example/v1", "model": "m", "api_key": "sk-secret-1234"},
    )
    assert created.status_code == 201
    body = created.json()
    assert "sk-secret" not in created.text
    assert body["api_key_hint"].endswith("1234")

    one = client.get(f"/api/ai/providers/{body['id']}")
    assert one.status_code == 200
    assert "sk-secret-1234" not in one.text

    listed = client.get("/api/ai/providers")
    assert listed.status_code == 200
    assert all("api_key" not in row or row.get("has_api_key") is not None for row in listed.json())
    assert "sk-secret-1234" not in listed.text


def test_mock_chat_echoes_user(client):
    providers = client.get("/api/ai/providers").json()
    mock = next(row for row in providers if row["kind"] == "mock")
    resp = client.post(
        "/api/ai/chat",
        json={
            "provider_id": mock["id"],
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "xin chào"},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "xin chào"


def test_import_keeps_id(client):
    resp = client.post(
        "/api/ai/providers/import",
        json={"id": 40, "label": "Cũ", "kind": "custom", "provider": "openai", "api_key": "sk-old"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 40
    again = client.post(
        "/api/ai/providers/import",
        json={"id": 40, "label": "Khác", "kind": "custom", "provider": "openai", "api_key": "sk-new"},
    )
    assert again.json()["label"] == "Cũ"


def test_import_does_not_duplicate_mock(client):
    resp = client.post(
        "/api/ai/providers/import",
        json={"id": 41, "label": "Mock (dev)", "kind": "mock", "provider": "mock"},
    )
    assert resp.status_code == 200
    mocks = [row for row in client.get("/api/ai/providers").json() if row["kind"] == "mock"]
    assert len(mocks) == 1
    assert resp.json()["id"] == mocks[0]["id"]
