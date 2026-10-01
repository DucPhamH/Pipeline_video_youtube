"""Gọi ai-service. TTS không giữ key."""
from __future__ import annotations

import httpx

from platform_.auth import outgoing_headers
from platform_.config import config


def complete(provider_id: int, messages: list[dict[str, str]]) -> str:
    url = f"{config.ai_api_base_url}/api/ai/chat"
    try:
        resp = httpx.post(
            url,
            json={"provider_id": provider_id, "messages": messages, "temperature": 0.2, "caller": "tts"},
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
