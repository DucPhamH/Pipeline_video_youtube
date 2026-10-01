"""Một lượt chat tới API kiểu OpenAI. Key không rời service này."""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator

import httpx

from ai.infrastructure.persistence.models import AiProviderModel

_TOO_LARGE = (
    "request too large",
    "reduce your message size",
    "reduce max_tokens",
    "context_length_exceeded",
    "maximum context length",
    "finish_reason=length",
)


class _NextKey(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _stored_keys(row: AiProviderModel) -> list[str]:
    try:
        items = json.loads(row.api_keys_json or "[]")
    except (ValueError, TypeError):
        items = []
    keys = [str(x).strip() for x in items if str(x).strip()] if isinstance(items, list) else []
    primary = (row.api_key or "").strip()
    if primary and primary not in keys:
        keys.insert(0, primary)
    return keys


def _too_large(text: str) -> bool:
    msg = text.lower()
    return any(marker in msg for marker in _TOO_LARGE)


Usage = Callable[[str, int, int], None]


def _once(
    row: AiProviderModel, key: str, messages: list[dict[str, str]], temperature: float, model: str
) -> tuple[str, str, int, int]:
    """Trả (nội dung, model đã dùng, prompt_tokens, completion_tokens)."""
    url = f"{(row.base_url or '').rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    used_model = model or row.model or "deepseek-chat"
    payload = {
        "model": used_model,
        "messages": messages,
        "temperature": temperature,
    }
    with httpx.Client(timeout=180) as client:
        resp = client.post(url, headers=headers, json=payload)
    if resp.status_code == 429 or resp.status_code >= 500:
        detail = (resp.text or "")[:300]
        if _too_large(detail):
            raise RuntimeError(detail)
        raise _NextKey(f"Model từ chối ({resp.status_code})")
    if resp.status_code >= 400:
        detail = (resp.text or "")[:300]
        if _too_large(detail):
            raise RuntimeError(detail)
        raise RuntimeError(f"Model từ chối ({resp.status_code})")
    data = resp.json()
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("finish_reason=length")
    content = str(choice["message"].get("content") or "").strip()
    if not content:
        raise _NextKey("model trả về content rỗng")
    usage = data.get("usage") or {}
    return content, used_model, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)


def complete(
    row: AiProviderModel,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    model: str = "",
    key_index: int | None = None,
    on_usage: Usage | None = None,
) -> str:
    if row.provider == "mock" or row.kind == "mock":
        for msg in reversed(messages):
            if msg.get("role") == "user" and (msg.get("content") or "").strip():
                return msg["content"].strip()
        raise ValueError("Thiếu nội dung")

    if not (row.base_url or "").strip():
        raise RuntimeError("Nhà AI chưa có base URL")
    keys = _stored_keys(row)
    if row.requires_api_key and not keys:
        raise RuntimeError("Nhà AI chưa có API key")
    if key_index is not None:
        if not keys and key_index == 0:
            keys = [""]
        elif 0 <= key_index < len(keys):
            keys = [keys[key_index]]
        else:
            raise ValueError("key_index không tồn tại")
    if not keys:
        keys = [""]

    last = ""
    for key in keys:
        for attempt in range(2):
            try:
                content, used_model, prompt_tokens, completion_tokens = _once(
                    row, key, messages, temperature, model
                )
                if on_usage is not None:
                    on_usage(used_model, prompt_tokens, completion_tokens)
                return content
            except _NextKey as exc:
                last = exc.detail
                if attempt == 0 and "429" not in last:
                    time.sleep(1)
                    continue
                break
            except httpx.HTTPError:
                last = "Không gọi được model"
                if attempt == 0:
                    time.sleep(1)
                    continue
                break
    raise RuntimeError(last or "Model không trả lời")


def _mock_reply(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user" and (msg.get("content") or "").strip():
            return msg["content"].strip()
    raise ValueError("Thiếu nội dung")


def iter_deltas(
    row: AiProviderModel,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    model: str = "",
    key_index: int | None = None,
) -> Iterator[str]:
    """Sinh từng mảnh chữ. Mock cắt nhỏ câu user. Nhà AI thật dùng stream của API."""
    if row.provider == "mock" or row.kind == "mock":
        text = _mock_reply(messages)
        for start in range(0, len(text), 24):
            yield text[start : start + 24]
        return
    if not (row.base_url or "").strip():
        raise RuntimeError("Nhà AI chưa có base URL")
    keys = _stored_keys(row)
    if row.requires_api_key and not keys:
        raise RuntimeError("Nhà AI chưa có API key")
    if key_index is not None:
        if not keys and key_index == 0:
            keys = [""]
        elif 0 <= key_index < len(keys):
            keys = [keys[key_index]]
        else:
            raise ValueError("key_index không tồn tại")
    if not keys:
        keys = [""]
    last = ""
    for key in keys:
        produced = False
        try:
            for delta in _stream_once(row, key, messages, temperature, model):
                produced = True
                yield delta
            return
        except _NextKey as exc:
            if produced:
                raise RuntimeError(exc.detail) from exc
            last = exc.detail
        except httpx.HTTPError:
            if produced:
                raise RuntimeError("Không gọi được model")
            last = "Không gọi được model"
    raise RuntimeError(last or "Model không trả lời")


def _stream_once(row, key: str, messages, temperature: float, model: str):
    url = f"{(row.base_url or '').rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    used_model = model or row.model or "deepseek-chat"
    payload = {"model": used_model, "messages": messages, "temperature": temperature, "stream": True}
    produced = False
    with httpx.Client(timeout=180) as client:
        with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code == 429 or resp.status_code >= 500:
                raise _NextKey(f"Model từ chối ({resp.status_code})")
            if resp.status_code >= 400:
                raise RuntimeError(f"Model từ chối ({resp.status_code})")
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = str((choices[0].get("delta") or {}).get("content") or "")
                if delta:
                    produced = True
                    yield delta
    if not produced:
        raise _NextKey("model trả về content rỗng")
