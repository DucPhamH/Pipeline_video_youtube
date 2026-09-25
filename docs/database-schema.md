# Database — schema thật đang chạy

> DB mặc định: SQLite tại `crawl-service/data/db.sqlite3` (tự tạo lúc khởi động).
> Đổi sang Postgres: sửa `DATABASE_URL` trong `.env`, không đổi code — xem
> `docs/platform-and-licensing.md` mục 3.

## 1. Bảng `genres` (`GenreModel`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `source_key` | VARCHAR(50) | khớp key trong `registry.py` (`SOURCES`) |
| `genre_key` | VARCHAR(50) | |
| `label` | VARCHAR(100) | tên hiển thị |
| `list_url` | VARCHAR(500) | URL trang danh sách/xếp hạng/search (xem `crawl-service.md`) |
| `enabled` | BOOLEAN, default `True` | job hàng ngày/scheduler chỉ quét dòng `True` |
| `last_run_status` | VARCHAR(20), default `"idle"` | `idle`/`running`/`done`/`error`/`cancelled` (`GenreRunStatus`) — trạng thái lần "Quét ngay"/job lịch gần nhất |
| `last_run_started_at` | DATETIME, nullable | |
| `last_run_finished_at` | DATETIME, nullable | |
| `last_run_discovered` | INTEGER, nullable | số truyện mới thoả tiêu chí, đã crawl xong trong lượt gần nhất |
| `last_run_rejected` | INTEGER, nullable | số truyện mới thấy nhưng không thoả tiêu chí |
| `last_run_errors` | INTEGER, nullable | số lỗi hạ tầng (không tính truyện `rejected`) |
| `last_run_messages` | TEXT, nullable | chi tiết lỗi/gợi ý, nối bằng `\n` |

**Unique**: `(source_key, genre_key)`.

Các cột `last_run_*` LƯU LẠI (không chỉ tồn tại lúc request `/run-now`
đang chạy) — để FE biết đang chạy hay đã xong dù tải lại trang, hoặc quét
thật chạy rất lâu (nhiều phút). Seed từ `GENRE_SEEDS` trong `registry.py`
lúc khởi động app (không tạo trùng — chỉ thêm dòng chưa có).

## 2. Bảng `novels` (`NovelModel`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `title` | VARCHAR(255) | |
| `source_key` | VARCHAR(50) | |
| `source_url` | VARCHAR(500) | URL trang mục lục chương của truyện |
| `genre_id` | INTEGER, FK -> `genres.id`, nullable | null nếu thêm tay bằng URL riêng |
| `is_manual` | BOOLEAN, default `False` | `True` = thêm tay bằng URL, `False` = tự phát hiện qua quét thể loại |
| `last_chapter_index` | INTEGER, default 0 | dùng để resume khi crawl lỗi giữa chừng / sync incremental |
| `is_complete` | BOOLEAN, default `False` | |
| `total_chapters` | INTEGER, nullable | ⚠️ có thể bị giới hạn bởi site nguồn (vd trang chỉ liệt kê tối đa N chương/trang) |
| `lifecycle_status` | VARCHAR(20), default `"discovered"` | 1 trong: `discovered, crawling, fully_crawled, translating, ready_for_video, produced, rejected, error` (`NovelLifecycle`) |
| `error_message` | TEXT, nullable | lý do reject/error gần nhất |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME, auto (`onupdate`) | |

**Unique**: `(source_key, source_url)` — chống thêm trùng 1 truyện.
**Index**: `lifecycle_status` (`ix_novel_lifecycle_status`), `genre_id`
(`ix_novel_genre_id`) — dùng cho job hàng ngày lọc
`discovered`/`crawling`, và lọc theo thể loại.

**Quan hệ**: `chapters` — 1-nhiều tới `ChapterModel`, `cascade="all,
delete-orphan"` (xoá novel thì xoá luôn mọi chapter con), sắp theo
`chapter_index`.

## 3. Bảng `chapters` (`ChapterModel`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `novel_id` | INTEGER, FK -> `novels.id` | |
| `chapter_index` | INTEGER | thứ tự chương (1, 2, 3...) |
| `title` | VARCHAR(255) | |
| `source_url` | VARCHAR(500) | |
| `raw_path` | VARCHAR(500), nullable | đường dẫn file `.txt` trong `data/raw/<novel_id>/<chapter_index>.txt` |
| `status` | VARCHAR(20), default `"pending"` | 1 trong: `pending, crawled, translating, translated, failed, unsupported` (`ChapterStatus`) |
| `error_message` | TEXT, nullable | |
| `queued_for_translate` | BOOLEAN, default `False` | đánh dấu đã sẵn sàng cho Translate service (chưa dùng tới vì Translate service chưa code) |
| `reviewed` | BOOLEAN, default `False` | đã xem/sửa nội dung qua `PUT /chapters/{id}/content` chưa |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME, auto (`onupdate`) | |

**Unique**: `(novel_id, chapter_index)` — chống crawl trùng 1 chương.
**Index**: `novel_id` (`ix_chapter_novel_id`), `status`
(`ix_chapter_status`).

Bản nội dung **đã làm mượt** (`smooth`) KHÔNG có cột riêng trong bảng này
— lưu song song trên filesystem tại
`data/cleaned/<novel_id>/<chapter_index>.txt` (đối chiếu qua `raw_path`,
không đè file raw gốc). API tự kiểm tra file này có tồn tại hay không để
trả `has_cleaned`/`content_source` (xem `api-reference.md`), không lưu cờ
"đã làm mượt" trong DB.

## 4. Bảng `settings` (`SettingsModel`) — key-value

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `key` | VARCHAR(100) PK | vd `crawl.scan_window.bqgxs_com` |
| `value` | JSON | có thể là số, chuỗi, object... |
| `updated_at` | DATETIME, auto (`onupdate`) | |

Không dùng bảng cột cứng (quy ước `platform-and-licensing.md` mục 3) — thêm
setting mới = thêm 1 key trong `SEED_DEFAULTS`/`PER_SITE_CRAWL_DEFAULTS`
(`platform_/settings_store.py`), không migrate schema.

**Key TOÀN CỤC (không thuộc site nào)** — `SEED_DEFAULTS`:

| Key | Giá trị mặc định | Dùng bởi |
|---|---|---|
| `crawl.max_chapters_translate_per_day` | 20 | Translate service (chưa code) |

**Key RIÊNG TỪNG SITE** — `PER_SITE_CRAWL_DEFAULTS`, lưu dạng
`crawl.<tên>.<source_key>` qua `per_site_key(key, source_key)`, vd
`crawl.scan_window.bqgxs_com`; seed 1 dòng/site cho mọi `source_key`
trong `registry.SOURCES` (kể cả `demo_local`) lúc khởi động app:

| Tên (chưa gắn hậu tố site) | Giá trị mặc định | Dùng bởi |
|---|---|---|
| `scan_window` | 5 | `CrawlGenreUseCase` — số truyện MỚI muốn chấp nhận mỗi lượt quét |
| `max_chapters_per_story` | 50 | `CrawlGenreUseCase`, `AddManualNovelUseCase` |
| `max_pages_per_scan` | 3 | `CrawlGenreUseCase` — chặn dò vô tận khi tỉ lệ loại quá cao |
| `max_consecutive_errors` | 5 | `CrawlGenreUseCase` — dừng sớm khi site lỗi liên tiếp |
| `narration_filter` | `"first_person"` | `CrawlGenreUseCase`, `AddManualNovelUseCase` — 1 trong `"any"`/`"first_person"`/`"third_person"` |
| `completion_filter` | `"completed_only"` | `CrawlGenreUseCase`, `AddManualNovelUseCase` — 1 trong `"completed_only"`/`"ongoing_only"`/`"any"` |

Ngoài 2 nhóm trên còn key `crawl.session_cookie.<source_key>` (giá trị
chuỗi cookie header, quản lý qua `platform_/session_cookies.py` và
`PUT /sites/{source_key}/session`) — không nằm trong `SEED_DEFAULTS`
(không seed sẵn, chỉ tồn tại sau khi người dùng lưu cookie lần đầu).

## 5. Quan hệ

```
genres (1) ──< (N) novels ──< (N) chapters

settings: đứng độc lập, không FK tới bảng nào
```

Xoá 1 `novel` xoá cascade toàn bộ `chapter` con (`cascade="all,
delete-orphan"` khai ở `NovelModel.chapters`). Xoá 1 `genre` **không**
cascade tới `novel` (`genre_id` chỉ nullable FK, không set
`ondelete`/cascade) — theo domain, 1 genre chỉ bị tắt (`enabled=False`),
không có endpoint xoá genre.

## 6. Chưa có (việc cần làm sau)

- Bảng `StoryPackage` (dự kiến trong `crawl-service.md`) — **chưa tạo**
  vì thuộc phạm vi Video service, làm khi tới lượt service đó.
- Chưa có bảng lưu lịch sử từng lượt chạy job riêng — `last_run_*` trên
  `genres` chỉ giữ **lượt gần nhất** (bị ghi đè mỗi lần chạy mới), không
  phải bảng log nhiều dòng.
- Chưa có Alembic — schema tạo trực tiếp từ model lúc khởi động, đổi
  cột = sửa model + xoá DB dev (xem `project-structure.md`).
