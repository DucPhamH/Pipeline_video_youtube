import httpx
import pytest

from platform_.config import config
from translate.application.run_job import _api_key_hint
from translate.infrastructure import ai_registry
from translate.infrastructure.providers.openai_compat import build_translator


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(config, "ai_api_base_url", "http://ai.test")
    return monkeypatch


def test_load_provider_exposes_key_slots_not_keys(gateway):
    def fake_get(url, **_):
        return httpx.Response(
            200,
            json={"id": 7, "label": "DS", "kind": "deepseek", "provider": "openai",
                  "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
                  "requires_api_key": True, "key_count": 3},
            request=httpx.Request("GET", url),
        )

    gateway.setattr(ai_registry.httpx, "get", fake_get)
    prov = ai_registry.load_ai_provider(None, 7)
    assert prov.api_keys == ["@key:0", "@key:1", "@key:2"]
    assert prov.api_key == "@key:0"
    assert _api_key_hint("@key:1") == "key 2"


def test_translator_sends_its_key_slot(gateway):
    sent = {}

    def fake_post(url, json, **_):
        sent.update(json)
        return httpx.Response(200, json={"content": "dịch xong"}, request=httpx.Request("POST", url))

    gateway.setattr(ai_registry.httpx, "post", fake_post)
    t = build_translator(provider="openai", base_url="x", api_key="@key:2", model="m2", gateway_provider_id=7)
    assert t._chat(system="sys", user="user") == "dịch xong"
    assert sent["provider_id"] == 7
    assert sent["key_index"] == 2
    assert sent["model"] == "m2"


def test_local_registry_closed_in_gateway_mode(client, gateway):
    assert client.get("/api/translate/ai-providers").status_code == 410
    resp = client.post("/api/translate/chat", json={"provider_id": 1, "messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 410


def test_upstream_5xx_stays_http_status_error(gateway):
    def fake_post(url, json, **_):
        return httpx.Response(502, json={"detail": "Model từ chối (503)"}, request=httpx.Request("POST", url))

    gateway.setattr(ai_registry.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError) as err:
        ai_registry.gateway_chat(7, system="s", user="u", api_key="@key:0")
    assert err.value.response.status_code == 503


def test_upstream_429_is_rate_limited(gateway):
    from translate.application.key_rotator import looks_rate_limited

    def fake_post(url, json, **_):
        return httpx.Response(502, json={"detail": "Model từ chối (429)"}, request=httpx.Request("POST", url))

    gateway.setattr(ai_registry.httpx, "post", fake_post)
    with pytest.raises(RuntimeError) as err:
        ai_registry.gateway_chat(7, system="s", user="u", api_key="@key:0")
    assert looks_rate_limited(err.value)
