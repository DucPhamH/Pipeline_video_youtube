# API Reference — endpoint thật đang chạy

> Nguồn chân lý luôn là Swagger UI tự sinh tại `/docs` khi server đang chạy
> (`http://localhost:8000/docs`) — file này là bản tóm tắt để đọc nhanh,
> không cần bật server. Field trong các ví dụ JSON dưới đây lấy đúng theo
> `crawl/api/schemas.py`, không suy đoán.

Base URL: `http://localhost:<port>` — prefix `/api/crawl` cho mọi endpoint
context Crawl (context Translate/TTS/Video sau này sẽ có prefix riêng
`/api/translate`, `/api/tts`, `/api/video`).

## Health

```
GET /api/health
→ {"status": "ok"}
```

## Sites — danh sách site + phiên đăng nhập (`/api/crawl/sites`)

Registry hiện có **~31 site** trong `SOURCES` (`infrastructure/sources/registry.py`,
kể cả `demo_local` dùng để test nội bộ). `GET /sites` **bỏ** mọi site có
`SourcePort.is_test=True` (hiện chỉ `demo_local`) — chỉ trả site thật.

### `GET /sites?search&access_kind&region&limit&offset`

Mọi query param optional. `search`: substring khớp `key` hoặc `name`
(không phân biệt hoa/thường). `access_kind`: `free` | `session_optional` |
`session_required` (site cần cookie đăng nhập ở mức nào — xem
`site_access.py`), hoặc giá trị đặc biệt `needs_session` = mọi site khác
`free` (gộp `session_optional` + `session_required`). `region`: `china` |
`japan` | `korea` | `vietnam` | `taiwan` (`site_regions.py`). `limit` mặc
định 20, tối đa 100; `offset` phân trang.

```json
// GET /sites?region=vietnam
{
  "items": [
    {
      "key": "truyenfull_vn",
      "name": "TruyenFull",
      "access_kind": "free",
      "region": "vietnam"
    }
  ],
  "total": 1
}
```

### `GET /sites/{source_key}/session` — trạng thái cookie phiên

404 nếu `source_key` không có trong `SOURCES`.

```json
{
  "source_key": "qidian_com",
  "configured": true,
  "cookie_names": ["ck", "e1", "e2"],
  "cookie_header": "ck=...; e1=...; e2=..."
}
```

### `PUT /sites/{source_key}/session` — lưu cookie phiên

Dùng cho site `session_optional`/`session_required` (vd `qidian_com`,
`wenku8_net`, `ciweimao_com`) — người dùng đăng nhập tay trên trình duyệt,
copy chuỗi cookie (dạng `name=value; name2=value2`, kiểu Cookie-Editor/
DevTools) rồi dán vào đây. Lưu trong bảng `settings`
(`crawl.session_cookie.<source_key>`), **không** tự đăng nhập hộ, không
giải CAPTCHA.

```json
// body
{"cookie_header": "ck=abc123; e1=%5B...%5D; e2=..."}
```
Response giống `GET /sites/{source_key}/session` (trạng thái sau khi lưu).

### `POST /sites/{source_key}/session/probe` — thử tải trang chủ

Thử `GET` trang chủ site bằng cookie đã lưu, kiểm tra còn bị chặn/verify
(Cloudflare, captcha, "访问频繁"...) hay không — dò theo vài từ khoá chặn
phổ biến trong tiêu đề/nội dung trang trả về. Trả `ok:false,
message:"Site này không dùng HTTP HTML..."` nếu site không có `base_url`
HTTP thật (vd `demo_local`). Không raise lỗi khi request thất bại — trả
`ok:false` kèm `message` mô tả exception.

```json
{
  "ok": true,
  "final_url": "https://www.qidian.com",
  "http_status": 200,
  "page_title": "起点中文网",
  "looks_blocked": false,
  "cookie_configured": true,
  "message": "Trang chủ tải được với phiên hiện tại."
}
```

## Genres — thể loại đang theo dõi (`/api/crawl/genres`)

Mỗi `Genre` là **1 option THẬT** trên menu/nav của 1 site (mirror đúng 1
URL liệt kê/xếp hạng/search có thật) — không có field nhóm cặp
"kind"/"family_key" gì cả, tất cả nằm chung 1 danh sách phẳng.

### `GET /genres?source_key&search&enabled&last_run_status&limit&offset`

Mọi query param optional. `source_key`: lọc đúng 1 site. `search`:
substring khớp `label`/`genre_key` (tuỳ implementation repo). `enabled`:
lọc theo cờ bật/tắt. `last_run_status`: lọc theo trạng thái lần quét gần
nhất (`idle`/`running`/`done`/`error`/`cancelled`). Kết quả **chỉ** gồm
genre nằm trong `GENRE_SEEDS` hiện tại (`catalog_genre_keys()`) — genre cũ
trong DB nhưng đã bị bỏ khỏi catalog (vd site đã gỡ đăng ký) không hiện ra
dù vẫn còn bản ghi trong bảng `genres`.

```json
{
  "items": [
    {
      "id": 5,
      "source_key": "bqgxs_com",
      "genre_key": "fantasy",
      "label": "Huyền huyễn (玄幻)",
      "list_url": "https://www.bqgxs.com/list1/",
      "enabled": true,
      "last_run_status": "done",
      "last_run_started_at": "2026-09-17T07:31:57",
      "last_run_finished_at": "2026-09-17T07:33:12",
      "last_run_discovered": 3,
      "last_run_rejected": 11,
      "last_run_errors": 0,
      "last_run_messages": null
    }
  ],
  "total": 1
}
```

### `PATCH /genres/{genre_id}` — chọn làm active / tắt

Body `{"enabled": true}` → chọn genre này làm "active" cho **site của nó**,
tự tắt mọi genre khác cùng site (`SetActiveGenreUseCase` — khớp UI select
mỗi site 1 lựa chọn). Body `{"enabled": false}` → chỉ tắt riêng genre này,
không đụng genre khác (dùng khi muốn 1 site tạm không quét gì). 404 nếu
không tìm thấy `genre_id`.

### `POST /genres/{genre_id}/run-now` — quét thủ công ngay

Chạy **nền** (thread riêng phía BE, session DB riêng) — trả về **ngay**
`202 Accepted` với `GenreOut` ở `last_run_status="running"`, không chờ
crawl xong (crawl thật có thể mất nhiều phút — nhiều truyện x nhiều
chương, retry khi site chậm). FE poll `GET /genres` để thấy chuyển
`done`/`error`/`cancelled` + kết quả.

Khoá theo `genre-run:{genre_id}` (`platform_/locks.py`) — **dùng chung
key** với job lịch trong scheduler, nên chặn cả bấm "Quét ngay" 2 lần liên
tiếp lẫn bấm đúng lúc job lịch cùng thể loại đang chạy. 404 nếu không tìm
thấy `genre_id`; **409** nếu khoá đang bị giữ. Khoá chỉ nhả khi thread nền
xong (kể cả lỗi bất ngờ — try/finally), không nhả ngay khi request trả về.

Ý nghĩa các field kết quả (đọc lại qua `GET /genres`, không có trong
response của chính `/run-now`):
- `last_run_discovered`: số truyện mới thoả tiêu chí (ngắn/hoàn thành/ngôi
  kể tuỳ settings riêng site), đã crawl xong.
- `last_run_rejected`: số truyện mới thấy nhưng không thoả tiêu chí.
- `last_run_errors`: số lỗi hạ tầng (site chặn, sập...), không tính truyện
  `rejected`.
- `last_run_messages`: chi tiết lỗi/gợi ý, nối bằng `\n`.

### `GET /genres/{genre_id}/progress` — tiến độ live

Snapshot **in-memory** (không lưu DB) của lượt quét đang chạy — dùng để FE
hiện thanh tiến độ trong lúc `last_run_status="running"`. `progress: null`
nếu chưa có snapshot (chưa chạy lần nào từ lúc server khởi động, hoặc đã
chạy xong và bị dọn). 404 nếu không tìm thấy `genre_id`.

```json
{
  "progress": {
    "task_id": "genre:5",
    "kind": "genre",
    "label": "Huyền huyễn (玄幻)",
    "phase": "scanning_candidates",
    "page": 2,
    "max_pages": 3,
    "discovered": 2,
    "rejected": 7,
    "errors": 0,
    "synced": 0,
    "scan_window": 5,
    "novel_title": "",
    "chapter_index": 0,
    "chapter_total": 0,
    "message": ""
  }
}
```

### `POST /genres/{genre_id}/cancel` — dừng lượt quét đang chạy

Đặt cờ yêu cầu dừng (`run_cancel.request_cancel`) — scan loop chỉ check cờ
giữa các ứng viên/chương, nên có thể mất vài giây tới khi HTTP request
đang chờ site trả lời xong mới thực sự dừng. 404 nếu không tìm thấy
`genre_id`; **409** nếu `last_run_status != running` (không có gì để
dừng).

## Novels — truyện (`/api/crawl/novels`)

### `GET /novels?status&source_key&search&is_manual&genre_id&limit&offset`

Mọi query param optional. `status`: 1 trong `discovered, crawling,
fully_crawled, translating, ready_for_video, produced, rejected, error`.
`source_key`: lọc đúng 1 site. `search`: substring khớp `title` (lọc phía
server). `is_manual`: `true` = chỉ truyện thêm tay bằng URL riêng, `false`
= chỉ truyện do quét thể loại tự phát hiện. `genre_id`: lọc đúng truyện
được phát hiện từ 1 genre cụ thể (null với truyện thêm tay). `limit` mặc
định 20, tối đa 100; `offset` phân trang.

```json
{
  "items": [
    {
      "id": 12,
      "title": "Đấu Phá Thương Khung",
      "source_key": "bqgxs_com",
      "source_url": "https://www.bqgxs.com/xxx/",
      "genre_id": 5,
      "is_manual": false,
      "total_chapters": 120,
      "last_chapter_index": 120,
      "lifecycle_status": "fully_crawled",
      "error_message": null
    }
  ],
  "total": 1
}
```

### `GET /novels/{novel_id}` — chi tiết 1 truyện

Trả `NovelOut` (không kèm sẵn danh sách chương — dùng
`/novels/{id}/chapters` riêng để phân trang được). 404 nếu không tìm thấy.

### `GET /novels/{novel_id}/chapters?status&search&reviewed&limit&offset`

404 nếu `novel_id` không tồn tại. `status`: 1 trong `pending, crawled,
translating, translated, failed, unsupported`. `search`: substring khớp
`title` chương. `reviewed`: lọc theo đã/chưa review nội dung. `limit`/
`offset` như trên.

```json
{
  "items": [
    {
      "id": 101,
      "chapter_index": 1,
      "title": "Chương 1: ...",
      "status": "crawled",
      "error_message": null,
      "reviewed": false,
      "has_cleaned": true
    }
  ],
  "total": 120
}
```
`has_cleaned`: đã có bản làm mượt (`data/cleaned/<novel_id>/<n>.txt`) hay
chưa — tính lại mỗi request (không lưu cột riêng trong DB).

### `POST /novels` — thêm truyện bằng URL riêng

Body (`AddNovelIn`):
```json
{"source_key": "bqgxs_com", "url": "https://www.bqgxs.com/xxx/", "force": true}
```
`force`: field giữ lại để FE cũ không lỗi khi gửi — **bị bỏ qua hoàn
toàn**, thêm tay luôn crawl toàn bộ, không áp filter ngắn/hoàn thành/ngôi
kể (những filter đó chỉ áp dụng khi "Quét ngay" theo thể loại).

Tạo `Novel` **đồng bộ** trong request này (nhanh — chỉ gọi
`list_chapters()` lấy metadata), nhưng crawl nội dung chương chạy **nền**:
- Nếu tạo Novel thất bại (vd site không parse được URL, hoặc trùng URL đã
  có): trả **200** với `success:false`.
- Nếu tạo Novel thành công: trả **202 Accepted**, `success:true`,
  `chapters_crawled:0` (crawl chưa chạy xong lúc trả response) — poll
  `GET /novels/{id}` để thấy `lifecycle_status` chuyển
  `fully_crawled`/`error`.

Khoá theo `add-novel:{source_key}:{url}` lúc tạo Novel (chống bấm thêm 2
lần cùng URL), sau đó chuyển sang khoá `crawl-novel:{novel_id}` cho phần
crawl nền. **409** nếu 1 trong 2 khoá đang bị giữ.

```json
// response (202) khi thành công
{"novel_id": 34, "chapters_crawled": 0, "success": true, "error": null}
```
```json
// response (200) khi thất bại — vd trùng URL
{"novel_id": 12, "chapters_crawled": 0, "success": false, "error": "Truyện này đã có trong hệ thống"}
```

### `POST /novels/{novel_id}/retry` — crawl lại (resume / sync chương mới)

Chỉ dùng được cho truyện đang `error` (resume từ `last_chapter_index`,
không tải lại từ đầu) hoặc `fully_crawled` (sync chương mới ra thêm —
incremental). 404 nếu không tìm thấy `novel_id`; **400** nếu
`lifecycle_status` không phải 1 trong 2 trạng thái trên. Luôn chạy
**incremental** dù resume lỗi hay sync truyện đã xong. Khoá theo
`crawl-novel:{novel_id}` — **409** nếu đang bị giữ (vd đang crawl dở, hoặc
đang nằm trong 1 batch `retry-errors`). Chạy nền, trả **202** ngay với
`chapters_crawled:0` (kết quả thật xem qua `GET /novels/{id}` sau).

### `POST /novels/retry-errors` — retry hàng loạt theo site

Dùng sau khi cập nhật cookie phiên (site chặn vì hết hạn login) — xếp
hàng retry **mọi** novel đang `error` của 1 `source_key`, chạy **tuần tự**
trong 1 thread nền (tránh đập site dồn dập nhiều request cùng lúc).

Body (`RetryErrorsIn`):
```json
{"source_key": "qidian_com", "genre_id": null, "is_manual": null, "limit": 100}
```
`genre_id`/`is_manual`: filter thêm (optional) — vd chỉ retry truyện thêm
tay. `limit`: tối đa 200, mặc định 100.

404 nếu `source_key` không có trong `SOURCES`. Trả **202** ngay
(`RetryErrorsOut`):
```json
{"queued": 8, "skipped": 2, "novel_ids": [12, 15, 19, 22, 30, 31, 40, 41]}
```
`skipped`: số novel bỏ qua vì không lấy được khoá `crawl-novel:{id}` (đang
crawl bởi request khác) hoặc không chuyển được sang trạng thái crawling.

### `POST /novels/{novel_id}/force-accept` — ép nhận truyện bị reject

Chỉ áp dụng cho truyện đang `rejected` (không thoả tiêu chí ngắn/hoàn
thành/ngôi kể lúc quét) — chuyển về `discovered` rồi crawl. Cùng pattern
2 pha với `POST /novels`: tạo/chuyển trạng thái đồng bộ trước (200 nếu
`success:false`, vd novel không ở trạng thái `rejected`), rồi crawl nền
(202 nếu thành công). Khoá theo `crawl-novel:{novel_id}` — 409 nếu đang bị
giữ.

### `POST /novels/{novel_id}/smooth` — làm mượt nội dung (rule-based)

Body (`SmoothNovelIn`, optional — không gửi body hoặc `chapter_ids: null`
đều được xem là "tất cả"):
```json
{"chapter_ids": [101, 102]}
```
`chapter_ids` rỗng/null = làm mượt **mọi** chương đã crawl của truyện; có
list = chỉ những chương đó. Kỹ thuật rule-based lấy từ dự án
`novel-processor` (MIT license) — dọn khoảng trắng thừa, dòng rác quảng
cáo lặp lại... Ghi ra `data/cleaned/<novel_id>/<n>.txt`, **không đè**
file raw gốc (`data/raw/`). Chỉ áp dụng cho truyện đã crawl ít nhất 1
phần (`fully_crawled`, `error`, `translating`, `ready_for_video`) — 400
nếu `lifecycle_status` không thuộc nhóm này, hoặc `chapter_ids` gửi lên
không khớp chương nào của truyện.

```json
{
  "novel_id": 12,
  "success": true,
  "chapters_smoothed": 118,
  "chapters_skipped": 2,
  "removed_lines": 340,
  "chapter_ids": [101, 102, "..."],
  "error": null
}
```
Chạy **đồng bộ** (không phải background job) — request chờ tới khi làm
mượt xong toàn bộ chương được chọn.

## Chapters — nội dung + review (`/api/crawl/chapters`)

Crawl về mà không xem/sửa được thì vô dụng — nhóm endpoint này cho đọc
raw text 1 chương, lưu bản đã sửa (fix encoding/rác quảng cáo sót/lỗi
chính tả...), và đánh dấu đã review.

### `GET /chapters/{chapter_id}/content` — đọc nội dung

Ưu tiên trả **bản cleaned** (nếu `smooth` đã chạy cho chương này), không
thì trả raw. 404 nếu không tìm thấy chương, hoặc chương chưa crawl xong
(`raw_path` rỗng), hoặc lỗi đọc file.

```json
{
  "chapter_id": 101,
  "success": true,
  "content": "Nội dung đang hiển thị (cleaned nếu có, không thì raw)...",
  "reviewed": false,
  "error": null,
  "has_cleaned": true,
  "content_source": "cleaned",
  "raw_content": "Nội dung raw gốc...",
  "cleaned_content": "Nội dung đã làm mượt..."
}
```
`content_source`: `"raw"` hoặc `"cleaned"` — cho biết field `content` lấy
từ đâu, để FE hiện đúng badge.

### `PUT /chapters/{chapter_id}/content` — lưu nội dung đã sửa

Body: `{"content": "..."}`. Ghi đè **bản đang được ưu tiên hiển thị**
(cleaned nếu đã có, raw nếu chưa) — không tạo thêm bản cleaned mới nếu
chương chưa từng làm mượt. Tự đánh dấu `reviewed=true`. 400 nếu không tìm
thấy chương, chương chưa có nội dung, `content` rỗng (chỉ khoảng trắng),
hoặc lỗi ghi file.

### `DELETE /chapters/{chapter_id}/cleaned` — bỏ bản cleaned

Xoá file cleaned của chương này (nếu có) — trở về hiển thị raw như trước
khi làm mượt. **Không** đụng tới cờ `reviewed`. 404 nếu không tìm thấy
chương, chương chưa có nội dung, hoặc lỗi khi đọc lại raw sau khi xoá.

## Settings — cấu hình chỉnh qua UI (`/api/crawl/settings`)

### `GET /settings`

Trả **toàn bộ** key hiện có trong bảng `settings` (đã merge với giá trị
seed mặc định cho key chưa từng ghi) — gồm cả key toàn cục lẫn key
**riêng từng site** (dạng `crawl.<tên>.<source_key>`). FE tự lọc đúng key
của site đang xem theo hậu tố `source_key`.

```json
{
  "values": {
    "crawl.max_chapters_translate_per_day": 20,
    "crawl.scan_window.bqgxs_com": 5,
    "crawl.max_chapters_per_story.bqgxs_com": 50,
    "crawl.max_pages_per_scan.bqgxs_com": 3,
    "crawl.max_consecutive_errors.bqgxs_com": 5,
    "crawl.narration_filter.bqgxs_com": "first_person",
    "crawl.completion_filter.bqgxs_com": "completed_only",
    "crawl.scan_window.qidian_com": 5
  }
}
```

### `PATCH /settings` — cập nhật 1 hoặc nhiều key cùng lúc

Body: `{"values": {"crawl.max_chapters_per_story.bqgxs_com": 60}}` → trả
lại toàn bộ settings hiện tại (giống response `GET`). Không cần gửi hết
mọi key, chỉ gửi key muốn đổi — key không tồn tại sẽ được tạo mới (không
migrate schema, xem `database-schema.md`).

## Dry-run — test 1 URL, không lưu DB (`/api/crawl/dry-run`)

### `POST /dry-run`

Body: `{"source_key": "...", "url": "...", "mode": "genre" | "chapters" | "content"}`

| mode | Gọi hàm nào | Dùng khi |
|---|---|---|
| `genre` | `source.list_genre_novels()` | test URL/search thể loại mới trước khi thêm vào `GENRE_SEEDS` |
| `chapters` | `source.list_chapters()` | test 1 truyện có ra đúng danh sách chương không |
| `content` | `source.fetch_chapter_content()` + `validate_chapter_content()` | test 1 chương có tải + validate được nội dung không |

Không tạo bản ghi Genre/Novel/Chapter nào trong DB — chỉ gọi thẳng
source, dùng lúc thêm site mới hoặc debug 1 URL đang lỗi.

Response tuỳ mode (`DryRunOut`, `crawl/api/schemas.py`):
- `ok`: luôn có — `false` nếu source ném lỗi.
- `preview`: mode `genre`/`chapters` — list dict thô trả về từ source.
- `content_preview` + `content_length` + `validation_passed`: mode
  `content`.
- `error`: có giá trị khi `ok:false`, mô tả lỗi.

## Chưa có

- `POST /chapters/{id}/retry` — crawl lại 1 chương lẻ bị `failed`/
  `unsupported`. Hiện chỉ retry được **cả truyện** qua
  `/novels/{id}/retry` hoặc hàng loạt qua `/novels/retry-errors`.
