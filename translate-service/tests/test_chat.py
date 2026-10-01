def test_chat_uses_saved_mock_provider_and_ignores_a_key_field(client):
    providers = client.get("/api/translate/ai-providers").json()
    mock = next(p for p in providers if p["kind"] == "mock")
    response = client.post(
        "/api/translate/chat",
        json={
            "provider_id": mock["id"],
            "api_key": "sk-should-not-be-used",
            "messages": [
                {"role": "system", "content": "json"},
                {"role": "user", "content": '[{"name":"Lan"}]'},
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"content": '[{"name":"Lan"}]'}
    assert "sk-should-not-be-used" not in response.text


def test_chat_unknown_provider(client):
    response = client.post(
        "/api/translate/chat",
        json={"provider_id": 999999, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 400
