# Cấu trúc dự án — hiện trạng code thật

> Tài liệu này mô tả **code đã viết**, khác với `crawl-service.md` (thiết kế
> nghiệp vụ) — đây là bản đồ thư mục để biết sửa gì ở đâu.

## 1. Cây thư mục

```
Crawl/
├── docs/                          Tài liệu thiết kế + tài liệu này
│   ├── crawl-overview.md           **Đọc nhanh cho AI** — vấn đề + đã ship
│   ├── crawl-service.md            Nghiệp vụ + kiến trúc Crawl (chi tiết)
│   ├── translate-service.md        Thiết kế chức năng Translate (chưa code)
│   ├── platform-and-licensing.md   Quy ước chung (DB, bán tool, chi phí)
│   ├── project-structure.md        (file này)
│   ├── database-schema.md
│   ├── api-reference.md
│   ├── microservices-architecture.md
│   ├── ADD_SITE.md
│   └── SUPPORT_SITES.md
│
├── frontend/                      React 19 + TS + Vite + Tailwind v4 +
│   │                               shadcn/ui (@base-ui/react) + TanStack
│   │                               Query — SPA gọi thẳng REST API crawl-service.
│   │                               KHÔNG có tài liệu thiết kế riêng — code tự
│   │                               giải thích qua comment; xem `src/features/
│   │                               crawl/` cho toàn bộ UI của service này.
│   └── src/
│       ├── api/                    client.ts (fetch wrapper), types.ts (khớp
│       │                           tay theo schemas.py — KHÔNG có codegen,
│       │                           đổi schema BE phải tự sửa file này theo)
│       ├── features/crawl/         pages/ (SitesPage, SiteDetailPage,
│       │                           NovelDetailPage, SettingsPage,
│       │                           DevToolsPage — chỉ route ở bản DEV),
│       │                           components/, api.ts, sessionGuides.ts
│       ├── components/ui/          shadcn/ui primitives (Select, Dialog...)
│       ├── layout/, lib/, hooks/
│       └── App.tsx, main.tsx
│
└── crawl-service/
    ├── .venv/                      Virtualenv (KHÔNG commit — chạy
    │                               `python3 -m venv .venv` để tạo lại)
    ├── requirements.txt
    ├── .env.example                Copy sang .env, điền giá trị thật
    ├── tools/qidian_decrypt/       Node script giải mã payload Qidian VIP
    │                               (cần Node 18+, chỉ dùng khi có cookie VIP)
    ├── data/                       Dữ liệu runtime (KHÔNG commit)
    │   ├── db.sqlite3               DB chính (tự tạo lúc khởi động)
    │   ├── raw/<novel_id>/*.txt     Text gốc từng chương đã crawl
    │   ├── cleaned/<novel_id>/*.txt Bản đã "làm mượt" (mục 9.6b), song song
    │   │                            raw/, không đè — database-schema.md §3
    │   └── fixtures/demo_novel/     2 chương mẫu cho nguồn demo_local (test)
    │
    └── src/                        Toàn bộ source code Python
        ├── main.py                  Entry point — chạy:
        │                            `PYTHONPATH=. uvicorn main:app --reload`
        │                            (chạy từ trong thư mục `crawl-service/src`)
        │
        ├── platform_/               Shared kernel CỦA RIÊNG SERVICE NÀY
        │   │                        (mỗi service tự có 1 bản, không dùng
        │   │                        chung với service khác — xem
        │   │                        microservices-architecture.md mục 1)
        │   ├── config.py             AppConfig (env-based): DB url, license
        │   │                         key, CORS origins, đường dẫn data/...
        │   ├── db.py                 SQLAlchemy engine/session, init_db()
        │   ├── settings_store.py     Bảng Settings key-value (SEED_DEFAULTS,
        │   │                         PER_SITE_CRAWL_DEFAULTS, get/set/get_all)
        │   ├── scheduler.py          APScheduler — job crawl hàng ngày, dùng
        │   │                         CHUNG `CrawlGenreUseCase` với "Quét ngay"
        │   ├── locks.py              Khoá theo key trong process (genre-run:*,
        │   │                         crawl-novel:*, add-novel:*) — mục 8
        │   │                         `platform-and-licensing.md`
        │   ├── run_cancel.py         Cờ huỷ quét giữa chừng theo genre_id
        │   ├── run_progress.py       Snapshot tiến độ live in-memory (khác
        │   │                         `last_run_*` đã lưu DB)
        │   ├── session_cookies.py    Đọc/ghi cookie phiên đăng nhập/site
        │   │                         (lưu qua chính Settings key-value)
        │   └── terminal_ui.py        Hiện tiến độ crawl ngay trên terminal
        │                             lúc chạy `uvicorn` (dev tiện theo dõi)
        │
        └── crawl/                   Bounded context "Crawl" (DDD)
            ├── domain/               Thuần Python, KHÔNG import FastAPI/
            │   │                     SQLAlchemy/httpx
            │   ├── entities.py        Novel, Chapter, Genre + enum trạng thái
            │   ├── value_objects.py   ChapterRef, NovelRef (dataclass bất biến)
            │   ├── ports.py           Protocol: SourcePort, *Repository
            │   ├── services.py        validate_chapter_content(),
            │   │                      evaluate_candidate() — logic thuần
            │   └── rule_smooth.py     Pipeline "làm mượt" rule-based (regex
            │                          thuần, không AI) — mục 9.6b
            │
            ├── application/          Orchestrate domain qua port, KHÔNG biết
            │   │                     hạ tầng cụ thể nào đang chạy
            │   ├── dto.py              Kết quả trả về (dataclass thuần)
            │   ├── progress.py         CrawlProgress + ProgressCallback (bắn
            │   │                       tiến độ live, không phải kết quả cuối)
            │   ├── chapter_resolve.py  try_list_chapters() — tự suy mục lục
            │   │                       khi người dùng dán nhầm URL 1 chương
            │   └── use_cases.py        CrawlGenreUseCase, CrawlNovelUseCase,
            │                           DryRunUseCase, AddManualNovelUseCase,
            │                           ForceAcceptNovelUseCase,
            │                           SmoothNovelUseCase, SetActiveGenreUseCase
            │
            ├── infrastructure/       Implement các port bằng công nghệ cụ thể
            │   ├── sources/
            │   │   ├── registry.py          ⭐ FILE WIRING DUY NHẤT — import
            │   │   │                        adapter + khai GENRE_SEEDS + quy
            │   │   │                        ước đặt tên genre_key (mục 7)
            │   │   ├── base_html_source.py     Tầng 1 (httpx) — retry/backoff,
            │   │   │                           phân trang, dùng chung mọi site
            │   │   │                           clone cùng 1 họ CMS
            │   │   ├── base_browser_source.py  Tầng 2/3 escalation (TLS →
            │   │   │                           Playwright) — kế thừa parse
            │   │   │                           HTML chung với base_html_source
            │   │   ├── tls_fetch.py            Tầng 1b — curl_cffi (TLS
            │   │   │                           impersonate Chrome)
            │   │   ├── challenge_fetch.py      Solver challenge cookie dùng
            │   │   │                           chung (vd 17k acw_sc__v2)
            │   │   ├── browser_fetch.py        Playwright Chromium + inject
            │   │   │                           cookie user (mục 4c)
            │   │   ├── content_pipeline.py     Phát hiện khoá VIP + OCR ảnh +
            │   │   │                           hook decrypt Qidian sau fetch
            │   │   ├── site_access.py          access_kind (free/session_
            │   │   │                           optional/session_required)
            │   │   ├── site_regions.py         Gắn vùng (china/japan/korea/
            │   │   │                           vietnam/taiwan) cho filter FE
            │   │   ├── qidian_decrypt_assets.py, ciweimao_crypto.py
            │   │   │                           Hỗ trợ giải mã riêng 2 site VIP
            │   │   │                           nặng nhất (gọi Node/thuật toán
            │   │   │                           riêng — mục 4c/8)
            │   │   ├── <site>_source.py        ⭐ 1 FILE / SITE — ~29 file hiện
            │   │   │                           có (bqgxs_com, wenku8_net,
            │   │   │                           qidian_com, ciweimao_com,
            │   │   │                           truyenfull_vn, syosetu_com...
            │   │   │                           — danh sách CHÍNH XÁC luôn nằm
            │   │   │                           ở chính thư mục này + registry.py
            │   │   │                           SOURCES, không liệt kê hết ở
            │   │   │                           tài liệu vì đổi liên tục)
            │   │   └── demo_local_source.py    SourcePort đọc file cục bộ
            │   │                               (is_test=True, chỉ dùng test)
            │   └── persistence/
            │       ├── models.py            SQLAlchemy ORM (GenreModel,
            │       │                        NovelModel, ChapterModel) — cột
            │       │                        đầy đủ xem database-schema.md
            │       └── repositories.py       Implement *Repository, map
            │                                 ORM <-> domain entity
            │
            └── api/                  Tầng trình diễn — FastAPI
                ├── schemas.py          Pydantic request/response
                └── routers.py          Endpoint, gọi use case (xem
                                        api-reference.md)
```

## 2. Quy ước đặt tên cần nhớ

- **`platform_`** (có gạch dưới) chứ không phải `platform` — tránh đè lên
  module chuẩn `platform` của Python. Nếu thêm file mới trong này, giữ
  nguyên tên `platform_`.
- **Không có `__init__.py`** trong các thư mục package — dùng implicit
  namespace package của Python 3 (không cần thêm, hoạt động bình thường
  với cấu trúc hiện tại).
- **Mỗi site 1 file `<site>_source.py` riêng** (`infrastructure/sources/`,
  sửa 17/9/2026 — trước đó dựng nhiều instance cùng 1 class generic) — thêm
  site mới cùng họ CMS: tạo file mới kế thừa `BaseHtmlSource`, khai
  `SourceConfig`, không cần code logic mới; site khác họ hẳn: override
  method cần thiết, vẫn implement đúng `SourcePort` (Protocol, không bắt
  buộc kế thừa `BaseHtmlSource`). Xem `crawl-service.md` mục 4b.
- Mỗi service mới (`translate-service`, `tts-service`, `video-service` —
  làm sau) là **1 thư mục riêng ở gốc repo** (ngang hàng `crawl-service/`,
  `frontend/`), KHÔNG phải thư mục con bên trong `crawl-service/` — mỗi
  service tự deploy độc lập (microservice thật). Bên trong mỗi service vẫn
  tổ chức cùng 4 tầng `domain/application/infrastructure/api` như `crawl/`.
  Xem [docs/microservices-architecture.md](./microservices-architecture.md).

## 3. Cách chạy local

**Backend — venv (dev, sửa code live-reload):**
```bash
cd crawl-service
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/playwright install chromium
# VIP Qidian (tuỳ chọn): cài Node.js 18+ — xem tools/qidian_decrypt/README.md

cd src
PYTHONPATH=. ../.venv/bin/uvicorn main:app --reload --port 8000
# Mở http://localhost:8000/docs (Swagger UI — gọi thử API trực tiếp)
```

**Frontend — dev server:**
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, gọi thẳng backend ở trên
npm run build         # tsc -b && vite build — production bundle
npm run lint          # oxlint
```

**Docker (giống môi trường sẽ chạy thật khi bán/self-host):**
```bash
docker compose up --build
# Mở http://localhost:8090/docs  (cổng 8090, đổi bằng biến CRAWL_SERVICE_PORT
# nếu 8090 đã bị chiếm — xem docker-compose.yml ở gốc repo)
```
Dữ liệu (`data/db.sqlite3`, `data/raw/`, `data/cleaned/`) lưu trong Docker
volume `crawl_data`, giữ nguyên qua các lần `docker compose down/up`.

Lúc khởi động, `main.py` tự động:
1. `init_db()` — tạo bảng nếu chưa có (KHÔNG có migration tool — xem mục 6).
2. Seed `Settings` (giá trị mặc định nếu key chưa tồn tại — cả global lẫn
   1 dòng/site cho các key riêng từng site).
3. Seed `Genre` từ `GENRE_SEEDS` trong `registry.py` (không tạo trùng nếu
   đã có — dùng `get_or_create`), đồng bộ hoá lại `enabled`/`label` nếu
   seed đổi, và tắt các option đã bị bỏ khỏi catalog.
4. Tự phục hồi mọi Genre kẹt `last_run_status="running"` do server bị tắt
   giữa lúc đang quét (lock/thread cũ đã mất theo tiến trình cũ) —
   `crawl-service.md` mục 9.2.
5. Tự phục hồi mọi Novel kẹt `lifecycle_status="crawling"` cùng lý do
   (thêm 17/9/2026, bug thật tương tự mục 4 nhưng ở cấp truyện — nặng hơn
   vì "Thử lại" chỉ nhận truyện `error`/`fully_crawled`, "crawling" không
   tự bấm lại được qua UI) — reset về `error`, `last_chapter_index`/
   Chapter đã lưu KHÔNG mất, "Thử lại" vẫn resume đúng chỗ dở.

## 4. Test

```bash
cd crawl-service
./.venv/bin/pytest -v
./.venv/bin/ruff check src/
```

~28 file test (`tests/`), chạy dưới vài giây (không cần mạng — dùng nguồn
`demo_local` đọc file cục bộ + fake source trong từng test + DB SQLite
riêng cho test, tách khỏi `data/db.sqlite3` thật đang dev, xem
`tests/conftest.py`). Không liệt kê hết từng file ở đây (số lượng đổi liên
tục) — nhóm chính:

- `test_domain_*.py` — logic thuần domain (validate, evaluate_candidate,
  invariant Novel/Genre), không DB/HTTP.
- `test_api_crawl_pipeline.py`, `test_*_pagination.py` — chạy thật qua
  FastAPI TestClient + use case + repository + SQLite.
- `test_crawl_novel_resume.py`, `test_scan_existing_sync.py` — resume sau
  lỗi, "Đồng bộ chương mới" (mục 9.2b `crawl-service.md`).
- `test_genre_cancel.py`, `test_genre_progress_api.py`,
  `test_genre_run_status.py` — huỷ quét, tiến độ live, tự phục hồi sau crash.
- `test_genre_naming_consistency.py` — enforce quy ước `genre_key` dùng
  chung nhãn giữa các site (mục 7 `crawl-service.md`).
- `test_site_session.py`, `test_fetch_tiers.py`, `test_wenku8_images.py` —
  cookie phiên, 3 tầng fetch, OCR ảnh VIP.
- `test_rule_smooth.py`, `test_smooth_api.py`, `test_chapter_review.py` —
  pipeline "làm mượt" + xem/sửa nội dung chương.
- `test_locks.py`, `test_race_conditions.py` — khoá theo key, tranh chấp
  request đồng thời.

⚠️ **Đã biết có vài test order-dependent/flaky** (`test_fetch_tiers.py::
test_browser_fetch_keeps_playwright_per_thread`, `test_retry_errors.py::
test_retry_errors_queues_error_novels` — pass khi chạy riêng file, thỉnh
thoảng fail khi chạy CẢ bộ test cùng lúc) — nghi do state/thread rò rỉ giữa
test, CHƯA root-cause xong; chạy lại riêng file đó nếu gặp fail lẻ tẻ
trước khi kết luận có bug thật.

## 5. Docker

`Dockerfile` + `.dockerignore` trong `crawl-service/`, orchestrate bằng
`docker-compose.yml` ở gốc repo — xem mục 3 cách chạy. Thiết kế sẵn để
thêm service mới (Translate/TTS/Video) là thêm 1 block trong compose, xem
[docs/microservices-architecture.md](./microservices-architecture.md).

## 6. Ghi chú quan trọng — CHƯA có (việc cần làm sau)

- **Chưa có Alembic/migration tool** — `init_db()` chỉ chạy
  `Base.metadata.create_all()`, tạo bảng còn thiếu nhưng KHÔNG tự sửa bảng
  đã tồn tại khi đổi schema. Đổi cột/bảng hiện tại phải tự xoá
  `data/db.sqlite3` (mất dữ liệu) hoặc tự viết script ALTER — cần bổ sung
  Alembic trước khi có dữ liệu thật đáng giữ.
- **Chưa có CI** (GitHub Actions chạy test tự động mỗi lần đổi code) — hợp
  lý để thêm khi có git repo thật (hiện repo chưa init git).
