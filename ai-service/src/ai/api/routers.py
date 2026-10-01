"""Nhà AI và một lượt chat. Service khác gọi vào đây, không giữ key."""
from __future__ import annotations

import datetime as dt
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ai.api.schemas import (
    AiProviderAddKeyIn,
    AiProviderImportIn,
    AiProviderIn,
    AiProviderOut,
    AiProviderPatchIn,
    ChatIn,
    ChatOut,
    UsageOut,
    UsageRow,
)
from ai.infrastructure.chat import complete, iter_deltas
from ai.infrastructure.persistence.models import AiProviderModel, AiUsageModel
from platform_.db import get_db

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _hint(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 4:
        return "****"
    return f"…{k[-4:]}"


def _keys(row: AiProviderModel) -> list[str]:
    try:
        items = json.loads(row.api_keys_json or "[]")
    except (ValueError, TypeError):
        items = []
    out = [str(x).strip() for x in items if str(x).strip()] if isinstance(items, list) else []
    if not out and (row.api_key or "").strip():
        out = [row.api_key.strip()]
    return out


def _clean(keys: list[str] | None, fallback: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in keys or []:
        item = str(key).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    if not out and fallback.strip():
        out = [fallback.strip()]
    return out


def _engine(kind: str) -> str:
    return "mock" if kind == "mock" else "openai"


def _host(url: str) -> str:
    raw = (url or "").strip()
    if raw and "://" not in raw:
        raw = f"http://{raw}"
    try:
        parts = urlsplit(raw)
        return f"{(parts.hostname or '').lower()}:{parts.port or ''}"
    except ValueError:
        return raw.lower()


def _out(row: AiProviderModel) -> AiProviderOut:
    keys = _keys(row)
    return AiProviderOut(
        id=row.id,
        label=row.label,
        kind=row.kind,
        provider=row.provider,
        base_url=row.base_url or "",
        model=row.model or "",
        requires_api_key=bool(row.requires_api_key),
        has_api_key=bool((row.api_key or "").strip()),
        api_key_hint=_hint(row.api_key),
        api_key_hints=[_hint(k) for k in keys],
        key_count=len(keys) or 1,
        sort_order=row.sort_order,
    )


def _get(db: Session, provider_id: int) -> AiProviderModel:
    row = db.get(AiProviderModel, provider_id)
    if row is None:
        raise HTTPException(404, "AI provider not found")
    return row


@router.get("/providers", response_model=list[AiProviderOut])
def list_providers(db: Session = Depends(get_db)):
    rows = db.query(AiProviderModel).order_by(AiProviderModel.sort_order, AiProviderModel.id).all()
    return [_out(row) for row in rows]


@router.post("/providers", response_model=AiProviderOut, status_code=201)
def add_provider(body: AiProviderIn, db: Session = Depends(get_db)):
    keys = _clean(body.api_keys, body.api_key)
    count = db.query(AiProviderModel).count()
    row = AiProviderModel(
        label=body.label.strip() or body.kind,
        kind=body.kind,
        provider=_engine(body.kind),
        base_url=body.base_url.strip(),
        model=body.model.strip(),
        api_key=keys[0] if keys else "",
        api_keys_json=json.dumps(keys, ensure_ascii=False),
        requires_api_key=1 if body.requires_api_key else 0,
        sort_order=count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/providers/import", response_model=AiProviderOut)
def import_provider(body: AiProviderImportIn, db: Session = Depends(get_db)):
    """Giữ id. Đã có thì không ghi đè — sửa sau đó nằm ở service này."""
    row = db.get(AiProviderModel, body.id)
    if row is not None:
        return _out(row)
    if body.kind == "mock":
        mock = db.query(AiProviderModel).filter(AiProviderModel.kind == "mock").first()
        if mock is not None:
            return _out(mock)
    keys = _clean(body.api_keys, body.api_key)
    row = AiProviderModel(
        id=body.id,
        label=body.label.strip() or body.kind,
        kind=body.kind,
        provider=body.provider or _engine(body.kind),
        base_url=body.base_url.strip(),
        model=body.model.strip(),
        api_key=keys[0] if keys else "",
        api_keys_json=json.dumps(keys, ensure_ascii=False),
        requires_api_key=1 if body.requires_api_key else 0,
        sort_order=body.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/providers/{provider_id}", response_model=AiProviderOut)
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    return _out(_get(db, provider_id))


@router.put("/providers/{provider_id}", response_model=AiProviderOut)
def update_provider(provider_id: int, body: AiProviderPatchIn, db: Session = Depends(get_db)):
    row = _get(db, provider_id)
    if body.base_url is not None and _host(row.base_url) != _host(body.base_url):
        supplied = _clean(body.api_keys, body.api_key or "")
        if (row.api_key or _keys(row)) and not supplied:
            raise HTTPException(422, "Đổi base_url sang host khác cần nhập lại api_key trong cùng request")
        row.api_keys_json = json.dumps(supplied, ensure_ascii=False)
        row.api_key = supplied[0] if supplied else ""
        body = body.model_copy(update={"api_keys": None, "api_key": None})
    if body.label is not None:
        row.label = body.label.strip() or row.label
    if body.kind is not None:
        row.kind = body.kind
        row.provider = _engine(body.kind)
    if body.base_url is not None:
        row.base_url = body.base_url.strip()
    if body.model is not None:
        row.model = body.model.strip()
    if body.api_keys is not None:
        keys = _clean(body.api_keys, body.api_key if body.api_key is not None else row.api_key)
        row.api_keys_json = json.dumps(keys, ensure_ascii=False)
        if keys:
            row.api_key = keys[0]
    elif body.api_key is not None:
        row.api_key = body.api_key
        keys = _keys(row)
        if row.api_key and row.api_key not in keys:
            keys = [row.api_key, *[k for k in keys if k != row.api_key]]
        row.api_keys_json = json.dumps(keys, ensure_ascii=False)
    if body.requires_api_key is not None:
        row.requires_api_key = 1 if body.requires_api_key else 0
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    row = _get(db, provider_id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post("/providers/{provider_id}/keys", response_model=AiProviderOut, status_code=201)
def add_key(provider_id: int, body: AiProviderAddKeyIn, db: Session = Depends(get_db)):
    row = _get(db, provider_id)
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "api_key rỗng")
    keys = _keys(row)
    if key not in keys:
        keys.append(key)
    row.api_keys_json = json.dumps(keys, ensure_ascii=False)
    if not row.api_key:
        row.api_key = key
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/providers/{provider_id}/keys/{index}", response_model=AiProviderOut)
def delete_key(provider_id: int, index: int, db: Session = Depends(get_db)):
    row = _get(db, provider_id)
    keys = _keys(row)
    if index < 0 or index >= len(keys):
        raise HTTPException(404, "Key index không tồn tại")
    keys.pop(index)
    row.api_keys_json = json.dumps(keys, ensure_ascii=False)
    row.api_key = keys[0] if keys else ""
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, db: Session = Depends(get_db)):
    _check_chat(body)
    row = _get(db, body.provider_id)
    try:
        content = complete(
            row,
            [{"role": m.role, "content": m.content} for m in body.messages],
            temperature=body.temperature,
            model=body.model.strip(),
            key_index=body.key_index,
            on_usage=lambda model, prompt, completion: _record_usage(
                db, row.id, model, body.caller, prompt, completion
            ),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)[:500]) from exc
    return ChatOut(content=content)


def _check_chat(body: ChatIn) -> None:
    if not body.messages or len(body.messages) > 8:
        raise HTTPException(400, "messages phải từ 1 đến 8")
    for msg in body.messages:
        if msg.role not in ("system", "user", "assistant"):
            raise HTTPException(400, "role phải là system, user hoặc assistant")
        if len(msg.content) > 200_000:
            raise HTTPException(400, "message quá dài")
    if not 0 <= body.temperature <= 2:
        raise HTTPException(400, "temperature ngoài khoảng")


@router.post("/chat/stream")
def chat_stream(body: ChatIn, db: Session = Depends(get_db)):
    _check_chat(body)
    row = _get(db, body.provider_id)
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    def events():
        parts: list[str] = []
        try:
            for delta in iter_deltas(
                row,
                messages,
                temperature=body.temperature,
                model=body.model.strip(),
                key_index=body.key_index,
            ):
                parts.append(delta)
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            return
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)[:500]}, ensure_ascii=False)}\n\n"
            return
        if row.provider != "mock" and row.kind != "mock":
            _record_usage(db, row.id, body.model.strip() or row.model, body.caller, 0, 0)
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


def _record_usage(db: Session, provider_id: int, model: str, caller: str, prompt: int, completion: int) -> None:
    db.add(
        AiUsageModel(
            provider_id=provider_id,
            model=model[:100],
            caller=caller.strip()[:30],
            prompt_tokens=max(0, prompt),
            completion_tokens=max(0, completion),
        )
    )
    db.commit()


@router.get("/usage", response_model=UsageOut)
def usage(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    sums = (
        func.count(AiUsageModel.id),
        func.coalesce(func.sum(AiUsageModel.prompt_tokens), 0),
        func.coalesce(func.sum(AiUsageModel.completion_tokens), 0),
    )

    def rows(group) -> list[tuple]:
        return (
            db.query(group, *sums)
            .filter(AiUsageModel.created_at >= since)
            .group_by(group)
            .order_by(group)
            .all()
        )

    def as_row(key, calls, prompt, completion, label: str = "") -> UsageRow:
        return UsageRow(
            key=str(key or ""), label=label, calls=calls, prompt_tokens=prompt, completion_tokens=completion
        )

    labels = {p.id: p.label for p in db.query(AiProviderModel).all()}
    calls, prompt, completion = db.query(*sums).filter(AiUsageModel.created_at >= since).one()
    return UsageOut(
        days=days,
        total=as_row("total", calls, prompt, completion),
        by_day=[as_row(*r) for r in rows(func.date(AiUsageModel.created_at))],
        by_provider=[
            as_row(pid, c, p, k, labels.get(pid, f"#{pid}")) for pid, c, p, k in rows(AiUsageModel.provider_id)
        ],
        by_caller=[as_row(*r) for r in rows(AiUsageModel.caller)],
    )
