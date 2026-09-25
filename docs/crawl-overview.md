# Crawl Service — thiết kế chức năng (đọc nhanh)

> **Dành cho AI / người mới vào repo:** đọc file này **trước**.  
> Spec sâu / lịch sử quyết định dài: [crawl-service.md](./crawl-service.md).  
> Bản đồ thư mục code: [project-structure.md](./project-structure.md).  
> Schema DB: [database-schema.md](./database-schema.md).  
> API: [api-reference.md](./api-reference.md).  
> Service kế tiếp (dịch): [translate-service.md](./translate-service.md).
>
> **Phạm vi:** CHỈ `crawl-service` + FE crawl. Không implement dịch/TTS/video ở đây.

**Trạng thái:** đã ship (code trong `crawl-service/` + `frontend/`). Cập nhật: 2026-09-18.

---

## 0. Một câu định vị

**Crawl = ingest + làm sạch nguyên liệu truyện ngắn đã hoàn** cho pipeline
video/TTS. Không phải “lncrawl tải mọi site cho fan đọc”.

Mỗi truyện: **phát hiện 1 lần → crawl hết chương → (làm mượt + review) →
xuất / bàn giao translate**. Không theo dõi truyện dài theo ngày.

```
Sites → Site (Quét | URL | Thư viện) → Novel (pipeline CTA)
         ↓
   raw + cleaned files + SQLite
         ↓
   Export ZIP/TXT/EPUB/XLSX  ·  (sau) handoff → translate-service
```

---

## 1. Vấn đề đang giải

| Muốn | Không muốn |
|---|---|
| Tìm truyện **ngắn + đã kết** trên nhiều site Trung (và region khác) | Theo dõi serial dài hàng tháng |
| Crawl ổn định, resume, retry chương lỗi | Crack paywall / bypass thanh toán |
| Làm sạch rule-based + review trước khi đốt tiền dịch | Gọi LLM dịch bên trong crawl |
| User tự dán URL hoặc quét thể loại | Bắt buộc cloud SaaS / multi-tenant |
| Bán/src self-host: Docker + FE đủ dùng hàng ngày | Clone 400 crawler lncrawl |

**Chi phí:** crawl ≈ rẻ (băng thông). **Dịch mới đắt** → crawl phải lọc chặt +
smooth/review trước khi handoff (cap dịch thuộc translate-service, không
nhét LLM vào đây).

---

## 2. Quyết định đã chốt (đừng hỏi lại)

1. **Library mode:** job quét chỉ nhận truyện **mới**; đã `fully_crawled` thì
   bỏ qua khi phát hiện lại — trừ **Đồng bộ / Retry** có chủ đích.
2. **Thêm URL tay:** crawl **toàn bộ**, **không** áp filter ngắn/hoàn/ngôi
   (filter chỉ cho job quét).
3. **Genre UI:** 1 select **phẳng** / site (không tách “thể loại / ranking”).
4. **DB riêng** service; translate **không** đọc SQLite crawl — chỉ API/handoff.
5. **Raw vs cleaned:** 2 file song song; smooth không đè raw.
6. **Lifecycle translate/video** trên Novel là **gợi ý pipeline** (enum có sẵn);
   bước dịch thật nằm ở `translate-service` (chưa/đang thiết kế riêng).
7. **FE** gọi REST crawl trực tiếp; i18n vi/en/zh.

---

## 3. Domain model (tối thiểu)

| Entity | Vai trò |
|---|---|
| **Site** (registry) | Adapter nguồn: key, region, access_kind (free / session) |
| **Genre** | 1 URL list/ranking trên 1 site; **1 active** / site khi quét |
| **Novel** | 1 truyện + `lifecycle_status` + tiến độ chương |
| **Chapter** | 1 chương + status + `reviewed` + có cleaned? |

### Novel lifecycle (crawl sở hữu đến `fully_crawled`)

```
discovered → crawling → fully_crawled
                ↘ error (resume/retry được)
rejected (không khớp filter quét)
```

Enum còn: `translating` | `ready_for_video` | `produced` — **dành pipeline sau**;
FE đã ẩn filter các trạng thái chưa ship.

### Chapter status

`pending` | `crawled` | `failed` | `unsupported`  
(+ dấu vết translating/translated trong enum — translate-service sẽ là owner
thật của bản dịch, không lưu bản dịch trong crawl).

---

## 4. Tính năng đã ship (checklist)

### Ingest

| # | Chức năng |
|---|---|
| 1 | Registry nhiều site + filter region/access trên Sites |
| 2 | Quét thể loại (“Quét ngay”) + huỷ giữa chừng + progress live |
| 3 | Lịch daily (APScheduler) per-site + webhook Discord/Telegram |
| 4 | Thêm truyện bằng URL (TOC hoặc 1 chương nếu `derive_novel_url`) |
| 5 | Validate nội dung chống silent success (bot/ads page) |
| 6 | Resume / retry novel / retry 1 chương / retry tất cả lỗi |
| 7 | Session cookie per-site + probe + guide FE |
| 8 | Dry-run (DEV) test parser không ghi DB |

### Làm sạch & xuất

| # | Chức năng |
|---|---|
| 9 | Smooth rule-based (+ OpenCC tùy site) |
| 10 | Review raw↔cleaned; lưu & chương sau; review all |
| 11 | Export Excel / TXT / EPUB / ZIP bundle; batch ZIP |
| 12 | Fingerprint / author trên novel (metadata) |

### UX vận hành (2026-09)

| # | Chức năng |
|---|---|
| 13 | Sites: khối **Hôm nay** (đang crawl / sẵn xử lý / lỗi) — không full history |
| 14 | Site: tab **Quét \| URL \| Thư viện**; preset quét (Video ngắn CN…) |
| 15 | Novel: pipeline CTA (mượt → review → ZIP); menu Chuẩn bị / Xuất |
| 16 | Preset filter chương: Chưa mượt / Chưa review / Lỗi |

### Không thuộc crawl (để service khác)

Dịch LLM · đổi ngôi / rút audio / clone style · TTS · ghép video · auth user.

---

## 5. Luồng chính

### 5a. Quét hàng ngày / Quét ngay

```
Genre active + settings (scan_window, max_chapters, narration, completion…)
  → list novels trên site
  → evaluate: mới? ngắn? hoàn? ngôi?
  → accept → crawl all chapters (delay + validate)
  → fully_crawled | error
```

### 5b. Pipeline trên 1 Novel (sau crawl)

```
fully_crawled
  → Smooth (cleaned/)
  → Review (reviewed=true)
  → Export  và/hoặc  (sau) POST handoff → translate-service
```

### 5c. Import tay

```
URL → AddManualNovel (bỏ filter quét) → crawl all → cùng pipeline 5b
```

---

## 6. Kiến trúc code (siêu gọn)

```
crawl-service/src/
  platform_/     # config, db, settings KV, scheduler, locks, cookies
  crawl/
    domain/      # entities, ports, validate
    application/ # use cases: scan genre, crawl novel, smooth, export…
    infrastructure/
      sources/   # BaseHtmlSource + per-site adapters + registry
      persistence/
    api/         # FastAPI routers
frontend/src/features/crawl/   # Sites, SiteDetail, NovelDetail, Settings
```

**Fetch:** httpx (+ optional TLS/challenge / Playwright theo site) — không bật
browser cho mọi request. Chi tiết tầng: `crawl-service.md` §4c/8.

**Locks:** in-process theo key (1 worker). Multi-worker = hạn chế đã biết.

---

## 7. Settings quan trọng (per-site)

Lưu KV (`platform_.settings_store`), key có `source_key`:

- `scan_window`, `max_chapters_per_story`, `max_pages_per_scan`
- `max_consecutive_errors`
- `narration_filter`, `completion_filter`
- `opencc_mode`
- `daily_enabled` / hour / minute / `daily_genre_key`

Preset UI: Video ngắn CN · Ngắn mọi ngôi · Rộng hơn (chỉ ghi draft filter;
user phải Lưu).

Global: webhook daily summary.

---

## 8. Biên giới với Translate

| Crawl giao | Translate nhận |
|---|---|
| Chapters cleaned (+ ideally reviewed) | `POST /works/from-crawl` (xem translate-service.md) |
| `external_id = crawl:novel:{id}` | Work riêng, DB riêng |
| Callback URL (opt) | Cập nhật gợi ý lifecycle trên FE crawl |

**Chưa bắt buộc đã code handoff** — khi làm translate P2 mới nối. Export file
hiện là cầu tạm cho user mang sang tool dịch ngoài.

---

## 9. FE — bản đồ màn hình

| Route | Việc |
|---|---|
| `/sites` | Danh sách site + **Hôm nay** |
| `/sites/:key` | Quét / URL / Thư viện + session + settings |
| `/novels/:id` | Pipeline CTA, smooth, review, export, bảng chương |
| `/settings` | Webhook global (filter quét = per-site) |
| DevTools | Dry-run (DEV only) |

---

## 10. Non-goals / nợ kỹ thuật đã biết

- Không Celery/Kafka ở quy mô hiện tại (scheduler in-process đủ).  
- Không multi-tenant.  
- Site VIP phụ thuộc cookie user; không giải mã trái phép.  
- Một số site registry chết / cần session — xem `SUPPORT_SITES.md`.  
- SQLite: commit theo chương + WAL; tránh nhiều writer.  
- Enum translating/video trên Novel = chỗ neo pipeline, chưa phải product dịch.

---

## 11. Khi AI được hỏi “sửa / thêm gì”

| Câu hỏi | Đọc thêm |
|---|---|
| Thêm site mới | `docs/ADD_SITE.md` + `infrastructure/sources/` |
| Đổi filter quét / lịch | settings_store + SiteSettingsDialog |
| Lỗi nội dung rác / 502 | `domain/services.py` validate + source adapter |
| UX pipeline / Hôm nay | `frontend/src/features/crawl/` |
| Bàn giao dịch | `docs/translate-service.md` — **không** nhét LLM vào crawl |
| Schema bảng | `docs/database-schema.md` |

---

## 12. Chạy nhanh (dev)

```bash
# API (trong crawl-service)
PYTHONPATH=src .venv/bin/uvicorn main:app --reload --port 8090

# FE
cd frontend && npm run dev   # thường :5173
```

Docker: `docker compose up` ở root (API + FE nginx) — xem README.

---

*File này là lối vào chức năng. Chi tiết lịch sử / VIP / UI dài → `crawl-service.md`.*
