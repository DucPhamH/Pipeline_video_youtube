import json

import pytest

from ai.infrastructure import chat
from ai.infrastructure.persistence.models import AiProviderModel


def _row() -> AiProviderModel:
    return AiProviderModel(
        label="Multi",
        kind="custom",
        provider="openai",
        base_url="http://models.example/v1",
        model="m",
        api_key="sk-a",
        api_keys_json=json.dumps(["sk-a", "sk-b", "sk-c"]),
        requires_api_key=True,
    )


def test_key_index_uses_only_that_key(monkeypatch):
    used: list[str] = []
    monkeypatch.setattr(chat, "_once", lambda row, key, *a: used.append(key) or ("ok", "m", 0, 0))
    assert chat.complete(_row(), [{"role": "user", "content": "x"}], temperature=0.3, key_index=1) == "ok"
    assert used == ["sk-b"]


def test_key_index_429_does_not_spill_to_other_keys(monkeypatch):
    used: list[str] = []

    def busy(row, key, *a):
        used.append(key)
        raise chat._NextKey("Model từ chối (429)")

    monkeypatch.setattr(chat, "_once", busy)
    with pytest.raises(RuntimeError, match="429"):
        chat.complete(_row(), [{"role": "user", "content": "x"}], temperature=0.3, key_index=2)
    assert used == ["sk-c"]


def test_key_index_out_of_range(monkeypatch):
    with pytest.raises(ValueError):
        chat.complete(_row(), [{"role": "user", "content": "x"}], temperature=0.3, key_index=9)
