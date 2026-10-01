"""Gọi ai-service. Write không giữ key."""
from __future__ import annotations

import json

import httpx

from platform_.auth import outgoing_headers
from platform_.config import config


def complete(provider_id: int, messages: list[dict[str, str]], *, temperature: float = 0.8) -> str:
    url = f"{config.ai_api_base_url}/api/ai/chat"
    try:
        resp = httpx.post(
            url,
            json={"provider_id": provider_id, "messages": messages, "temperature": temperature, "caller": "write"},
            headers=outgoing_headers(),
            timeout=180,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("Không kết nối được dịch vụ AI") from exc
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = str(resp.json().get("detail") or "")
        except Exception:  # noqa: BLE001
            detail = (resp.text or "")[:200]
        raise RuntimeError(detail or "Dịch vụ AI từ chối")
    content = str((resp.json() or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("AI trả về rỗng")
    return content


def iter_content(provider_id: int, messages: list[dict[str, str]], *, temperature: float = 0.8):
    """Sinh từng mảnh chữ từ ai-service. Lỗi nằm trong sự kiện error."""
    url = f"{config.ai_api_base_url}/api/ai/chat/stream"
    try:
        with httpx.Client(timeout=180) as client:
            with client.stream(
                "POST",
                url,
                json={
                    "provider_id": provider_id,
                    "messages": messages,
                    "temperature": temperature,
                    "caller": "write",
                },
                headers=outgoing_headers(),
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise RuntimeError(_detail(resp) or "Dịch vụ AI từ chối")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if payload.get("error"):
                        raise RuntimeError(str(payload["error"]))
                    delta = str(payload.get("delta") or "")
                    if delta:
                        yield delta
    except httpx.HTTPError as exc:
        raise RuntimeError("Không kết nối được dịch vụ AI") from exc


def _detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detail") or "")
    except Exception:  # noqa: BLE001
        return (resp.text or "")[:200]
