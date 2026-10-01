# Folio

![Folio](frontend/public/logo.svg)

**Self-host desk** for a short finished novel: collect chapters, clean and
review them, translate, then optionally read them aloud. The repo folder is
still `Crawl/`. `crawl-service` is only the first of three services. The product name is Folio.

Export is Excel / TXT / EPUB from crawl, TXT / JSON / EPUB from translate,
and MP3 / M4B from TTS. Video assembly is not in this package.

This package sells **source code for internal use** (see [`LICENSE`](LICENSE)).
It is not a multi-tenant SaaS.

## What you get

| Layer | Path | Notes |
|---|---|---|
| Crawl API | [`crawl-service/`](crawl-service/) | FastAPI + SQLite + one adapter per site |
| Translate API | [`translate-service/`](translate-service/) | Separate DB. Import TXT or receive a crawl handoff. OpenAI-compatible providers, including local models |
| TTS API | [`tts-service/`](tts-service/) | Separate DB. Import TXT/EPUB or receive a finished translation. Edge voices, chapter MP3 / M4B |
| AI API | [`ai-service/`](ai-service/) | Saved providers and chat. Translate, write, and TTS call this. Keys stay here |
| Write API | [`write-service/`](write-service/) | Separate DB. Original stories from a premise, outline, and chapter count. Calls ai-service |
| UI | [`frontend/`](frontend/) | React — Sites, novel pipeline, `/translate`, and `/tts` |
| Docs | [`docs/`](docs/) | Architecture, API, schema, how to add a site |
| License | [`LICENSE`](LICENSE) | Commercial — no redistribution of source |

**Shipped — crawl:** genre scan, add-by-URL, filters, daily schedule,
Discord/Telegram webhook, session cookies, rule smooth + OpenCC, chapter
review, export Excel / TXT / EPUB / ZIP, i18n (VI/EN/ZH).

**Shipped — translate:** handoff from a novel (“Gửi sang dịch”, no job until
you pick an AI), TXT import, glossary, estimate, review, resume. Modes:
full translation, POV rewrite, audio cut, style clone. Several saved AIs can
share one job (parallel pool or sequential fallback) or rotate multiple keys
on one model. Export TXT / JSON.

**Shipped — TTS:** TXT/EPUB import, Edge voice catalog (rate, pitch, style), narrator plus quoted dialogue, chapter MP3, zip, and M4B when ffmpeg is installed. A finished translate job can be sent across with “Đọc thành audio”.

**Not shipped:** video assembly. Translate can import and export EPUB. A polish pass exists and is off unless you tick it.

## Quick start (Docker — recommended)

Compose starts crawl, translate, TTS, and the UI. Copy the env files first:

```bash
cp crawl-service/.env.example crawl-service/.env
cp translate-service/.env.example translate-service/.env
cp tts-service/.env.example tts-service/.env
cp write-service/.env.example write-service/.env
cp ai-service/.env.example ai-service/.env
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:5173 | UI (nginx proxies `/api`, `/api/translate`, `/api/tts`) |
| http://localhost:8090/docs | Crawl OpenAPI |
| http://localhost:8010/docs | Translate OpenAPI |
| http://localhost:8011/docs | TTS OpenAPI |
| http://localhost:8012/docs | Write OpenAPI |
| http://localhost:8013/docs | AI OpenAPI |

Data persists in Docker volumes `crawl_data`, `translate_data`, and `tts_data`.

### Crawl service environment

| Variable | Default | What |
|---|---|---|
| `FOLIO_API_TOKEN` | empty | Shared API token. When set, every route except `/api/health` and the docs needs `X-Folio-Token: <token>` or `Authorization: Bearer <token>` (GET downloads also accept `?token=`). Calls to translate-service send it too. Empty = no auth (a warning is logged at startup). |
| `CRAWL_ENABLE_DEMO_SOURCE` | `false` | Registers the `demo_local` test source (reads files under `data/fixtures` only). |
| `CRAWL_ALLOW_PRIVATE_FETCH` | `false` | Allow fetching private/loopback IPs (local test sites). |
| `NOTIFY_ALLOW_PRIVATE_WEBHOOK` | `false` | Allow a webhook URL on a private IP. |
| `SCHEDULER_TZ` | process local time | IANA timezone for daily scans. |
| `TRANSLATE_SERVICE_URL` / `CRAWL_PUBLIC_URL` | `http://localhost:8010` / `http://localhost:8090` | Translate handoff + callback URLs. |

## Dev (hot reload)

```bash
make bootstrap          # venv crawl + translate + tts, npm, .env files
make api-dev            # crawl :8090
make translate-dev      # translate :8010
make tts-dev            # tts :8011
make write-dev          # write :8012
make ai-dev             # ai :8013
make fe-dev             # UI :5173 — frontend/.env sets the API base URLs
```

`frontend/.env.example` points the UI at `http://localhost:8090` and
`http://localhost:8010`.

## Typical workflow

1. Open **Sites** → pick a source.
2. **Scan settings**: short novels + completed + narration (optional).
3. **Scan now** or paste a novel URL.
4. Open the novel → **Smooth** → **Review**.
5. **Gửi sang dịch** hands the cleaned chapters to translate and opens the
   work. The job does not start until you choose an AI and a mode.
6. On **Translate**, review segments and export TXT or JSON.
7. **Đọc thành audio** sends a finished translation to TTS, or import a
   TXT/EPUB on **Đọc** directly.

You can also import a TXT on **Translate** or **Đọc** without crawling. Daily schedule
and the Discord/Telegram webhook live in site settings and global Settings.

## Extend: add a site

See [`docs/ADD_SITE.md`](docs/ADD_SITE.md). Support tiers:
[`docs/SUPPORT_SITES.md`](docs/SUPPORT_SITES.md).

## Version

See [`CHANGELOG.md`](CHANGELOG.md). Packaged release **1.0.0**; translate
work after that is listed under **Unreleased**.

## Legal

You are responsible for how you use crawled content (copyright, site ToS,
publishing platforms). This tool does not grant rights to third-party texts.

License: [`LICENSE`](LICENSE) — internal use; no resale of source.
