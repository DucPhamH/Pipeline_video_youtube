"""Nhà AI nằm ở ai-service khi AI_API_BASE_URL được đặt. Không thì dùng bảng local (test)."""
from __future__ import annotations

import re

import httpx
from sqlalchemy.orm import Session

from platform_.auth import outgoing_headers
from platform_.config import config
from platform_.db import SessionLocal
from translate.domain.entities import AiProvider
from translate.infrastructure.persistence.repositories import AiProviderRepository


def _base() -> str:
    return (config.ai_api_base_url or "").rstrip("/")


def load_ai_provider(db: Session, provider_id: int | None) -> AiProvider | None:
    if provider_id is None:
        return None
    base = _base()
    if not base:
        return AiProviderRepository(db).get(provider_id)
    try:
        resp = httpx.get(
            f"{base}/api/ai/providers/{provider_id}",
            headers=outgoing_headers(),
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise ValueError("Không kết nối được dịch vụ AI") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise ValueError("Dịch vụ AI từ chối")
    row = resp.json()
    slots = [key_slot(i) for i in range(max(1, int(row.get("key_count") or 1)))]
    return AiProvider(
        id=row["id"],
        label=row.get("label") or "",
        kind=row.get("kind") or "custom",
        provider=row.get("provider") or "openai",
        base_url=row.get("base_url") or "",
        model=row.get("model") or "",
        api_key=slots[0],
        requires_api_key=bool(row.get("requires_api_key", True)),
        api_keys=slots,
    )


KEY_SLOT_PREFIX = "@key:"


def key_slot(index: int) -> str:
    """Thay key thật bằng số thứ tự — job vẫn xoay/chạy song song từng key như cũ."""
    return f"{KEY_SLOT_PREFIX}{index}"


def key_slot_index(api_key: str) -> int | None:
    if not (api_key or "").startswith(KEY_SLOT_PREFIX):
        return None
    try:
        return int(api_key[len(KEY_SLOT_PREFIX):])
    except ValueError:
        return None


def gateway_chat(
    provider_id: int, *, system: str, user: str, model: str = "", api_key: str = ""
) -> str:
    """Một lượt model. Key ở lại ai-service."""
    base = _base()
    if not base:
        raise RuntimeError("Chưa cấu hình dịch vụ AI")
    try:
        resp = httpx.post(
            f"{base}/api/ai/chat",
            headers=outgoing_headers(),
            timeout=180,
            json={
                "provider_id": provider_id,
                "temperature": 0.3,
                "model": model,
                "key_index": key_slot_index(api_key),
                "caller": "translate",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    except httpx.HTTPError as exc:
        raise httpx.ConnectError("Không kết nối được dịch vụ AI") from exc
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = str(resp.json().get("detail") or "")
        except Exception:  # noqa: BLE001
            detail = (resp.text or "")[:300]
        upstream = re.search(r"\((5\d\d)\)", detail)
        if upstream:
            # Lỗi 5xx của model: giữ dạng HTTPStatusError để job thử key khác như cũ.
            raise httpx.HTTPStatusError(
                detail, request=resp.request, response=httpx.Response(int(upstream.group(1)))
            )
        raise RuntimeError(detail or f"Model từ chối ({resp.status_code})")
    content = str((resp.json() or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("model trả về content rỗng")
    return content


def export_local_providers() -> None:
    """Đẩy nhà AI đang nằm trong DB dịch sang ai-service, giữ id. Đã có thì bỏ qua."""
    base = _base()
    if not base:
        return
    db = SessionLocal()
    try:
        rows = AiProviderRepository(db).list_all()
    finally:
        db.close()
    for row in rows:
        if row.id is None:
            continue
        httpx.post(
            f"{base}/api/ai/providers/import",
            headers=outgoing_headers(),
            timeout=15,
            json={
                "id": row.id,
                "label": row.label,
                "kind": row.kind,
                "provider": row.provider,
                "base_url": row.base_url,
                "model": row.model,
                "api_key": row.api_key,
                "api_keys": row.api_keys,
                "requires_api_key": row.requires_api_key,
            },
        )
