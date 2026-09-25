# Translate Service

Phase-1 MVP: import TXT → Work + Variant(`full`) → Job dịch (OpenAI-compatible hoặc mock) → export TXT.

Mặc định `lang_tgt=vi`. Không share DB với crawl-service — chỉ nhận handoff qua API.

## Chạy local

```bash
cd translate-service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=src .venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8010
```

API prefix: `/api/translate` — docs: http://localhost:8010/docs

## Test

```bash
PYTHONPATH=src .venv/bin/pytest -q --tb=short
```

## Luồng E2E nhanh

1. `POST /api/translate/works/import-txt` — body `{title, lang_src, text}`
2. Lấy `variants[0].id` từ response
3. `POST /api/translate/variants/{id}/jobs` → 202 + `job.id`
4. Poll `GET /api/translate/jobs/{id}` tới `completed`
5. `GET /api/translate/variants/{id}/export.txt`

Settings mặc định: `translate.provider=mock` (prefix `[vi] `). Đổi sang OpenAI-compatible qua `PUT /api/translate/settings`.
