# Novel Crawl Studio — commercial source package

**Self-host tool** to discover short completed novels, crawl chapters, clean
text, review, and export (Excel / TXT / EPUB) — ready for a downstream
TTS / video pipeline you own.

This package sells **source code for internal use** (see [`LICENSE`](LICENSE)).
It is not a multi-tenant SaaS.

## What you get

| Layer | Path | Notes |
|---|---|---|
| API | [`crawl-service/`](crawl-service/) | FastAPI + SQLite + adapters per site |
| UI | [`frontend/`](frontend/) | React — Sites → Scan → Novel → Smooth/Review/Export |
| Docs | [`docs/`](docs/) | Architecture, API, schema, how to add a site |
| License | [`LICENSE`](LICENSE) | Commercial — no redistribution of source |

**Shipped:** crawl, filters, schedule, webhook, session cookies, smooth,
OpenCC, review, exports, i18n (VI/EN/ZH).

**Not shipped (designed only):** translate / TTS / video microservices.

## Quick start (Docker — recommended)

```bash
cp crawl-service/.env.example crawl-service/.env
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:5173 | UI |
| http://localhost:8090/docs | API OpenAPI |

Data persists in Docker volume `crawl_data`.

## Dev (hot reload)

```bash
make bootstrap          # venv + npm + .env
make api-dev            # :8090
make fe-dev             # :5173 — needs frontend/.env → VITE_API_BASE_URL
```

## Typical workflow

1. Open **Sites** → pick a source  
2. **Scan settings**: short novels + completed + narration (optional)  
3. **Scan now** or paste novel URL  
4. Open novel → **Smooth** → **Review** → **Export**  

Daily schedule + Discord/Telegram webhook: Site settings + global Settings.

## Extend: add a site

See [`docs/ADD_SITE.md`](docs/ADD_SITE.md). Support tiers:
[`docs/SUPPORT_SITES.md`](docs/SUPPORT_SITES.md).

## Version

See [`CHANGELOG.md`](CHANGELOG.md). Current: **1.0.0**.

## Legal

You are responsible for how you use crawled content (copyright, site ToS,
publishing platforms). This tool does not grant rights to third-party texts.

License: [`LICENSE`](LICENSE) — internal use; no resale of source.
