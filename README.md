# Novel Crawl Studio — commercial source package

**Self-host tool** to discover short completed novels, crawl chapters, clean
text, review, then translate (and adapt) them. Export is Excel / TXT / EPUB
from crawl, and TXT / JSON from translate. TTS and video are not in this
package.

This package sells **source code for internal use** (see [`LICENSE`](LICENSE)).
It is not a multi-tenant SaaS.

## What you get

| Layer | Path | Notes |
|---|---|---|
| Crawl API | [`crawl-service/`](crawl-service/) | FastAPI + SQLite + one adapter per site |
| Translate API | [`translate-service/`](translate-service/) | Separate DB. Import TXT or receive a crawl handoff. OpenAI-compatible providers, including local models |
| UI | [`frontend/`](frontend/) | React — Sites, novel pipeline, and `/translate` |
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

**Not shipped:** TTS, video assembly, EPUB import into translate.

## Quick start (Docker — recommended)

Compose starts crawl, translate, and the UI. Copy both env files first:

```bash
cp crawl-service/.env.example crawl-service/.env
cp translate-service/.env.example translate-service/.env
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:5173 | UI (nginx proxies `/api` to crawl and `/api/translate` to translate) |
| http://localhost:8090/docs | Crawl OpenAPI |
| http://localhost:8010/docs | Translate OpenAPI |

Data persists in Docker volumes `crawl_data` and `translate_data`.

## Dev (hot reload)

```bash
make bootstrap          # crawl venv + frontend npm + .env files
make api-dev            # crawl :8090
make fe-dev             # UI :5173 — frontend/.env sets both API base URLs
```

Translate is a second process. `make bootstrap` does not create its venv:

```bash
cd translate-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp -n .env.example .env
cd ..
make translate-dev      # :8010
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

You can also import a TXT on **Translate** without crawling. Daily schedule
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
