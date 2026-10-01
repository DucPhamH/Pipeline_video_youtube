import json


def test_mock_stream_splits_the_reply(client):
    providers = client.get("/api/ai/providers").json()
    mock = next(row for row in providers if row["kind"] == "mock")
    text = "một câu đủ dài để phải cắt thành nhiều mảnh chữ khi stream"
    resp = client.post(
        "/api/ai/chat/stream",
        json={"provider_id": mock["id"], "caller": "write", "messages": [{"role": "user", "content": text}]},
    )
    assert resp.status_code == 200, resp.text
    deltas = []
    done = False
    for line in resp.text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = json.loads(line.split(":", 1)[1])
        if payload.get("delta"):
            deltas.append(payload["delta"])
        if payload.get("done"):
            done = True
    assert done
    assert len(deltas) > 1
    assert "".join(deltas) == text
