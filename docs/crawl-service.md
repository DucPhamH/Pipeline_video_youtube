# Crawl Service — tài liệu thiết kế

> **AI / agent mới vào:** đọc **[crawl-overview.md](./crawl-overview.md) trước**
> (1 trang nắm vấn đề + quyết định + đã ship). File này là bản **chi tiết /
> lịch sử thiết kế** — đọc khi cần đào sâu.
>
> Phạm vi: CHỈ module crawl (lấy + làm sạch nguyên liệu truyện ngắn).
> Dịch/TTS/video → [translate-service.md](./translate-service.md) và service tương ứng.

## 1. Mục tiêu

**Chỉ nhắm vào truyện NGẮN, ĐÃ HOÀN THÀNH** — đủ ngắn để gói gọn trong
**1-5 video**, không nhắm vào truyện dài đang ra tiếp (không có khái niệm
"theo dõi 1 truyện nhiều ngày liên tục" nữa). Mỗi ngày, job quét thể loại
**Kinh dị** (vd search trên `bqgxs.com`), tìm **truyện MỚI xuất hiện** (chưa từng thấy)
khớp tiêu chí ngắn+hoàn thành → crawl **toàn bộ truyện đó 1 lần** (vì đã
hoàn thành, không cần chờ chương mới) → đẩy vào hàng đợi dịch, cap **không
quá 20 chương dịch/ngày** để kiểm soát chi phí (một truyện dài hơn cap có
thể tràn sang ngày hôm sau). Truyện đã crawl nếu site đẩy lên đầu list với
chương mới thì job quét / nút Đồng bộ sẽ sync phần thiếu.

> `biquge.pro` đã **gỡ khỏi registry** (HTTP 520 dai dẳng trên `/novel/*`).

**Vì sao đổi từ "theo dõi liên tục" sang "quét 1 lần khi phát hiện":**
truyện đã hoàn thành thì không còn chương mới để chờ — crawl xong 1 lần là
xong nhiệm vụ của truyện đó, tài nguyên hàng ngày dồn hết vào việc *tìm
truyện ngắn mới* thay vì *hỏi lại truyện cũ có gì mới không* (vốn không có
gì mới vì nó đã hoàn thành).

**Vấn đề chi phí — hiểu đúng để cắt đúng chỗ:** crawl (tải trang, đọc text)
gần như miễn phí, chỉ tốn băng thông/thời gian. **Dịch (gọi Claude) mới là
chỗ tốn tiền**, tính theo token. ⇒ Cắt chi phí ở đầu vào bước dịch (cap
20 chương/ngày), không phải giới hạn crawl.

## 2. Tham khảo từ các dự án crawl truyện lớn — áp dụng gì, vì sao

Đã đọc kỹ 2 repo lớn, nhiều người dùng thật, nhiều bài học thực chiến:

- **[lncrawl/lightnovel-crawler](https://github.com/lncrawl/lightnovel-crawler)** — 361 nguồn, 446 crawler, có CLI/REST API/web UI/Docker server.
- **[404-novel-project/novel-downloader](https://github.com/404-novel-project/novel-downloader)** — chuyên site Trung Quốc (Qidian, Jinjiang...), nhiều kinh nghiệm đối phó chống-crawl kiểu Trung Quốc.

| Bài học từ 2 repo trên | Áp dụng vào thiết kế của mình |
|---|---|
| **"Silent success" là lỗi phổ biến nhất**: trang chặn bot vẫn trả HTTP 200 kèm trang quảng cáo/challenge, tưởng crawl thành công nhưng nội dung là rác. | Sau khi lấy nội dung, **validate** trước khi lưu: tối thiểu N ký tự, tỉ lệ ký tự Hán đủ cao, không chứa vài cụm đặc trưng của trang chặn (vd "请稍后", "验证"...). Nếu không đạt → coi là lỗi rõ ràng, không lưu rác. |
| **Escalation theo tầng khi bị chặn**, không retry-cứng: request thường trước → đổi cách tiếp cận nếu do IP → chỉ bật browser thật khi *thực sự* cần (site có JS-challenge thật). | **3 tầng fetch** (mục 4c): (1) httpx `BaseHtmlSource` → (1b) challenge cookie / `curl_cffi` TLS impersonate → (2) Playwright Chromium. Adapter chọn tầng; **không** bật browser cho mọi site. |
| **Tái dùng session/cookie đã "qua cửa"** thay vì mở phiên mới mỗi request. | `httpx.Client` / Playwright context tái dùng; cookie user (`session_cookies`) gắn mọi tầng. |
| **Pacing lịch sự — rotate/retry dồn dập khi bị rate-limit sẽ tệ hơn.** | Giữ `request_delay_sec` giữa các request cùng site (đã có), khi gặp lỗi thì **backoff tăng dần**, không retry liên tục ngay lập tức. |
| **Trạng thái chi tiết theo từng chương** (pending/downloading/failed/done) thay vì chỉ "ok/lỗi" chung cho cả truyện — dễ biết chính xác chương nào cần làm lại. | `Chapter.status` tách rõ, xem mục 5. |
| **Resume theo từng chương đã tải**, không tải lại từ đầu. | Đã có sẵn qua `last_chapter_index` — làm rõ thêm: cập nhật ngay sau MỖI chương thành công, không đợi xong cả batch. |
| **Chế độ test 1 site/1 URL riêng lẻ** (source editor có "test run" trong lncrawl) — vì "site đổi cấu trúc HTML" là lý do site gãy phổ biến nhất, cần sửa selector nhanh mà không chạy lại cả pipeline. | Thêm 1 lệnh/endpoint `crawl_dry_run(source_key, url)` — chạy thử 1 URL, in ra kết quả parse được (không lưu DB), dùng để chỉnh selector khi thêm site mới hoặc khi site đổi cấu trúc. |
| **VIP / chống-bot nặng** (login, ảnh chương, giải mã Qidian): novel-downloader dùng cookie user + OCR + Node decrypt — **không crack thanh toán**. | **Trong phạm vi**: cookie session user; OCR ảnh VIP (`rapidocr`); Node decrypt VIP Qidian. Thiếu cookie/quyền → `ScrapeError` rõ, không lưu rác. Xem mục 4c. |
| **"Library" mode (lncrawl)**: server giữ trạng thái cả thư viện đã tải/dịch, lần sau chỉ động vào phần *chưa xong* — không hỏi lại phần đã xong. | Novel có **vòng đời trạng thái** rõ ràng (`discovered → crawling → fully_crawled → translating → ready_for_video → produced`) — job hàng ngày chỉ quan tâm truyện `discovered` mới, bỏ qua mọi truyện đã `produced`/`fully_crawled`. Khớp thẳng với việc "mỗi truyện chỉ xử lý 1 lần" ở mục 1. |
| **Export nhiều định dạng qua bước "đóng gói" riêng (lncrawl xuất EPUB/PDF/TXT...)** — tách khâu đóng gói ra khỏi khâu tải. | Sau khi 1 truyện `fully_crawled`+dịch xong, có bước **đóng gói thành 1-5 phần** (`StoryPackage`, chia đều theo độ dài) — biên giới giữa Crawl/Translate và Video service, xem mục 7. |

## 3. Tính năng chính

| # | Tính năng |
|---|---|
| 1 | Chọn thể loại theo dõi/site (select box PHẲNG, hardcode danh sách option — mục 7/9.2) — ~31 site đã đăng ký (17/9/2026). |
| 2 | Job hàng ngày: quét N truyện đầu danh sách thể loại → lọc ra truyện **MỚI** (chưa từng thấy) khớp tiêu chí **ngắn + đã hoàn thành** (mục 7) → crawl **toàn bộ** truyện đó (không phải chỉ chương mới, vì là lần đầu thấy). |
| 3 | Truyện đã `fully_crawled`/`produced` rồi thì job các ngày sau **bỏ qua hẳn** khi PHÁT HIỆN LẦN ĐẦU (mục 2 — "Library mode") — trừ 1 ngoại lệ có kiểm soát: "Đồng bộ chương mới" (mục 9.2b) cho `fully_crawled`/`error`. |
| 4 | Cho phép thêm 1 truyện cụ thể bằng URL riêng, ngoài danh sách thể loại (dùng cho truyện ngắn bạn tự chọn tay). |
| 5 | Validate nội dung trước khi lưu — chống "silent success" (mục 2). |
| 6 | Escalation theo tầng khi 1 site bị chặn (httpx → TLS/challenge → Playwright) + pipeline VIP (cookie / OCR / Node) — mục 4c/8. |
| 7 | Resume trong lúc crawl 1 truyện: lỗi giữa chừng thì lần sau chỉ crawl tiếp phần còn thiếu, không tải lại từ đầu. |
| 8 | Chạy tay ("Quét ngay"/"Crawl lại") cho 1 truyện/1 thể loại — **huỷ được giữa chừng**, xem tiến độ live, và chế độ test 1 URL không lưu DB (`dry-run`) — mục 9.2, 9.2b, 9.4. |
| 9 | Lỗi 1 truyện/1 site không làm crash job — các truyện khác vẫn chạy tiếp. |
| 10 | Chống trùng lặp: unique `(novel_id, chapter_index)`, và không thêm lại truyện đã `discovered` trước đó. |
| 11 | Cookie phiên đăng nhập cho site cần login/VIP (mục 9.1b) — không crack thanh toán, chỉ đọc bằng chính account người dùng. |
| 12 | "Làm mượt" nội dung rule-based (không tốn tiền AI) + xem/sửa/review từng chương trước khi đưa qua Translate (mục 9.6b). |

*Không thuộc phạm vi crawl service (để service khác lo): dịch, TTS, ghép
video, quản lý người dùng/đăng nhập.*

## 4. Kiến trúc (DDD nội bộ + microservice độc lập)

> Cập nhật: mỗi service (Crawl, Translate, TTS, Video) giờ là **1 thư mục
> ở gốc repo, tự deploy riêng** (microservice thật), KHÔNG nằm chung 1 app
> như bản nháp cũ. Xem toàn cảnh + cách các service gọi nhau ở
> [docs/microservices-architecture.md](./microservices-architecture.md).
> Mục này chỉ mô tả cấu trúc BÊN TRONG service Crawl (`crawl-service/`).

Bên trong `crawl-service/`, code vẫn tổ chức theo DDD —
`domain / application / infrastructure / api`. Domain layer thuần Python,
không biết gì về FastAPI/SQLAlchemy/httpx — dễ test, dễ đổi hạ tầng mà
không đụng logic nghiệp vụ. Tầng `api/` chính là hợp đồng HTTP mà service
khác (Translate...) sẽ gọi vào sau này.

```
crawl-service/src/crawl/           # package nghiệp vụ của service này
  domain/
    entities.py       Novel, Chapter, Genre — thuần Python (không phụ thuộc
                       SQLAlchemy), mang state + invariant (vd Chapter không
                       thể translated trước khi crawled).
    value_objects.py  ChapterRef, NovelRef (dataclass bất biến)
    ports.py           interface trừu tượng (Protocol), KHÔNG implement:
                          - SourcePort: list_genre_novels/list_chapters/
                            fetch_chapter_content/derive_novel_url (mục 9.3b)
                          - NovelRepository, ChapterRepository
    services.py         domain logic thuần: validate(text) chống "silent
                       success", is_new_chapter(), lọc "ngắn" theo entities —
                       không đụng DB/HTTP, test được không cần mock nặng.

  application/
    use_cases.py       CrawlGenreUseCase, CrawlNovelUseCase, DryRunUseCase —
                       orchestrate domain services + ports (SourcePort,
                       Repository) qua interface, không biết SourcePort nào
                       đang chạy thật (httpx hay browser).
    dto.py              input/output cho use case (dataclass thuần, KHÔNG
                       phải Pydantic — Pydantic chỉ ở tầng api/).

  infrastructure/       # implement các port ở trên bằng công nghệ cụ thể
    sources/
      base_html_source.py      tầng 1 httpx — retry/backoff, CSS selector
      base_browser_source.py   tầng 2 Playwright — kế thừa parse HTML chung
      tls_fetch.py             tầng 1b curl_cffi (TLS impersonate Chrome)
      challenge_fetch.py       challenge cookie dùng chung (vd 17k acw_sc)
      browser_fetch.py         Playwright Chromium + inject cookie user
      content_pipeline.py      VIP/OCR/Node decrypt sau khi có HTML/bytes
      *_source.py              1 adapter / site (biquge, wenku8, qidian...)
      demo_local_source.py     nguồn test cục bộ, is_test=True
      registry.py              WIRING + GENRE_SEEDS
    persistence/
      models.py                 SQLAlchemy ORM (khác entities ở domain/)
      repositories.py            implement NovelRepository/ChapterRepository

  api/                  # tầng trình diễn — FastAPI router cho context này
    routers.py           nhận HTTP request → map sang DTO → gọi use case →
                       trả response
    schemas.py            Pydantic request/response (khác domain entities)

crawl-service/src/platform_/  # shared kernel CỦA RIÊNG SERVICE NÀY (mỗi
                       service tự có 1 bản riêng, không dùng chung code với
                       Translate/TTS/Video — xem microservices-architecture.md
                       mục 1): config, DB engine/session factory, scheduler
                       (APScheduler job hàng ngày gọi CrawlGenreUseCase),
                       Settings key-value (mục 5).
```

**Vì sao tách vậy:** `infrastructure/sources` đổi (thêm site, đổi selector,
nâng cấp lên browser thật) không đụng `use_cases.py`; đổi ORM/DB không đụng
`domain/`; test `services.py` (validate, lọc "ngắn"...) không cần chạy
DB/HTTP thật. Service khác (Translate/TTS/Video) sẽ giao tiếp với service
này qua gọi HTTP vào tầng `api/`, KHÔNG gọi thẳng `use_cases.py` (khác
codebase, khác tiến trình) — chi tiết ở `microservices-architecture.md` mục 3.

### 4b. Mỗi site 1 adapter riêng (sửa 17/9/2026)

Trước đó `registry.py` dựng thẳng NHIỀU *instance* của cùng 1 class
`GenericHtmlSource` (khác nhau ở tham số `SourceConfig` truyền vào) — dùng
được vì 2 site hiện có cùng "họ" CMS (biquge-clone), nhưng khiến mọi
selector/quy luật phân trang của MỌI site đều dồn hết vào 1 file
`registry.py`, khó tìm/khó review khi thêm nhiều site khác họ (đúng phản
hồi thật: "kiến trúc các repo nổi trên mạng nó đề chia các site ra adapter
riêng"). Đổi sang kế thừa (`class BiqugeProSource(BaseHtmlSource)`, `class
BqgxsComSource(BaseHtmlSource)`, mỗi class 1 file riêng):

- `BaseHtmlSource` (`base_html_source.py`) chỉ còn giữ phần THẬT SỰ dùng
  chung giữa mọi site cùng họ CMS: retry/backoff (`_get_soup`), phân trang
  danh sách (`list_genre_novels_page`), parse HTML theo `SourceConfig`
  (selector CSS) — tránh chép lại ~150 dòng xử lý HTTP/lỗi cho mỗi site.
- Mỗi site tự khai `SourceConfig` của mình trong `__init__`, VÀ có thể tự
  định nghĩa method riêng (vd `BqgxsComSource._paginate_list_url` xử lý 3
  kiểu URL khác nhau của riêng site này, `BiqugeProSource._paginate_list_url`
  chỉ có 1 kiểu `?page=N`) — site sau này khác họ CMS hẳn (cần logic hoàn
  toàn khác, không chỉ đổi selector) chỉ cần **override thẳng method** ở
  đúng adapter đó (`list_chapters`, `fetch_chapter_content`...), không đụng
  `BaseHtmlSource` dùng chung hay adapter của site khác.
- `registry.py` giờ CHỈ còn wiring (import + khởi tạo adapter + khai
  `GENRE_SEEDS`) — không còn 1 dòng selector/logic riêng site nào.
- Thêm site MỚI hoàn toàn cùng họ CMS: tạo 1 file `<site>_source.py`, class
  kế thừa `BaseHtmlSource`, khai `SourceConfig` (không cần code logic mới).
  Site khác họ hẳn: tạo adapter riêng override method cần thiết, vẫn implement
  đúng `SourcePort` (Protocol, không bắt buộc kế thừa `BaseHtmlSource`).

### 4c. Ba tầng fetch + pipeline VIP (sửa 16/9/2026)

**Chính sách:** không crack / bypass thanh toán. VIP chỉ đọc khi user dán
cookie session (account đã mua/được đọc trên site) — giống novel-downloader.

| Tầng | Module | Khi dùng |
|---|---|---|
| 1 | `base_html_source.py` (httpx) | HTML mở, site clone biquge… |
| 1b | `tls_fetch.py` (`curl_cffi`) + `challenge_fetch.py` | Soft CF / TLS fingerprint / challenge cookie (vd 17k `acw_sc__v2`) |
| 2 | `browser_fetch.py` + `base_browser_source.py` (Playwright) | CF “Just a moment”, trang render JS nặng |

**Proxy (học lncrawl):** cấu hình trên **UI** trước — Cài đặt → Proxy theo vùng,
hoặc trang site → Cài đặt quét → Proxy URL. `proxy_pool.py` ưu tiên UI, rồi
fallback env `CRAWL_HTTP_PROXY` / `CRAWL_PROXY_VN`… / file. Site VN thường
**cần exit IP Việt**; không set proxy → đi thẳng (nhiều host
reset TCP từ IP nước ngoài). Chi tiết: `crawl-service/.env.example`.

Sau khi có HTML/bytes → `content_pipeline.py`:

- Phát hiện trang khoá VIP / login → `ScrapeError` (cần cookie hoặc hết quyền).
- Chương ảnh (vd ciweimao VIP) → OCR (`rapidocr-onnxruntime`).
- Payload Qidian mã hoá → gọi Node script `tools/qidian_decrypt/` (cần Node 18+).

Cookie user (`platform_/session_cookies.py`) gắn mọi tầng. Use case vẫn chỉ
biết `SourcePort` — không biết đang httpx hay browser.

Phụ thuộc vận hành: `playwright install chromium`; Node cho VIP Qidian;
OCR cài qua `requirements.txt`.

⚠️ **Sửa 17/9/2026 — rò rỉ tiến trình Chromium (xác nhận thật, không phải
nghi ngờ suông)**: mỗi job nền (routers.py) chạy trên 1 `threading.Thread`
MỚI dùng đúng 1 lần rồi thread đó chết hẳn — cache Playwright theo-thread ở
`browser_fetch.py` vì vậy KHÔNG giúp tái dùng được gì giữa 2 lần "Quét
ngay" khác nhau, mà trước đây cũng chưa hề đóng `browser`/`playwright` ở
nhánh THÀNH CÔNG — mỗi lần 1 site cần tầng 2 (hiện chỉ `qidian_com`) được
quét là thêm 1 tiến trình Chromium con mồ côi. Đã thêm
`browser_fetch.close_browser()`, gọi ở cuối MỖI hàm target chạy nền
(`routers.py`) và cuối mỗi lượt job lịch (`scheduler.py`, thread pool
riêng của APScheduler) — try/finally, chạy dù job lỗi.

## 5. Data model

Danh sách cột ĐẦY ĐỦ, luôn đúng theo code thật: xem
[database-schema.md](./database-schema.md) — mục này chỉ tóm tắt các field
mang Ý NGHĨA NGHIỆP VỤ cần biết, không liệt kê lại từng cột.

**Genre**: `source_key, genre_key, label, list_url, enabled` + cụm
`last_run_*` (status/started_at/finished_at/discovered/rejected/errors/
messages) LƯU LẠI kết quả lần "Quét ngay"/job lịch gần nhất ngay trên chính
Genre (mục 9.2) — `last_run_status` gồm `idle/running/done/error/cancelled`
(`cancelled` = người dùng chủ động bấm Huỷ giữa chừng, mục 9.2b — TÁCH RIÊNG
khỏi `error` để không hiểu nhầm "site lỗi" khi thực ra là tự dừng).

**Novel**: `title, source_key, source_url, genre_id (nullable), is_manual:
bool, last_chapter_index, is_complete: bool, total_chapters: int|None,
lifecycle_status, error_message, created_at, updated_at`

`lifecycle_status` ("Library mode", mục 2): `discovered → crawling →
fully_crawled → translating → ready_for_video → produced`, hoặc `rejected`
(không khớp tiêu chí ngắn+hoàn thành, không xử lý tiếp), hoặc `error`. Job
hàng ngày **chỉ động vào novel ở trạng thái `discovered` hoặc `crawling`**
khi PHÁT HIỆN LẦN ĐẦU — nhưng có 1 NGOẠI LỆ đã thêm sau bản thiết kế gốc
này: **"Đồng bộ chương mới"** (mục 9.2b) cho phép quét lại ĐÚNG các novel
đang `fully_crawled`/`error` của genre đó (capped
`MAX_EXISTING_SYNCS_PER_SCAN`/lượt quét, `domain/services.py`) để bắt
chương MỚI khi site đẩy truyện cũ lên đầu danh sách hoặc để retry phần còn
thiếu sau lỗi VIP/cookie hết hạn — KHÔNG phải "quét lại từ đầu", chỉ chương
có index lớn hơn những gì đã lưu.

**Chapter**: `novel_id, chapter_index, title, source_url, raw_path, status,
error_message, queued_for_translate: bool, reviewed: bool, created_at,
updated_at`. `raw_path` trỏ file gốc trong `data/raw/<novel_id>/`; bản đã
"làm mượt" (mục 9.6b) lưu file riêng cùng tên trong `data/cleaned/<novel_id>/`
(KHÔNG có cột DB riêng — tồn tại file `cleaned` hay không tự suy ra qua
`RawTextStorage.has_cleaned()`, `application/use_cases.py`).
`reviewed` đánh dấu người dùng đã xem/duyệt nội dung (mục 9.6).

`Chapter.status` (chi tiết theo từng chương, bài học ở mục 2):
`pending → crawled → (queued_for_translate) → translating → translated`,
hoặc `failed` (lỗi khi crawl chương này cụ thể — không ảnh hưởng chương khác),
hoặc `unsupported` (site dùng cơ chế ngoài phạm vi hỗ trợ, xem mục 2).

**Index bắt buộc** (quy ước chung, xem
[platform-and-licensing.md](./platform-and-licensing.md) mục 3):
`Novel.lifecycle_status`, `Novel.genre_id`, `Chapter.novel_id`, `Chapter.status`
— đều là cột filter/join chính trong luồng mục 6 và query danh sách ở mục 9.5.

**StoryPackage** (mới — biên giới sang Video service, chỉ khai báo ở đây,
chi tiết làm ở doc Video): `id, novel_id, part_index, chapter_range,
target_video_index`. Sinh ra khi `Novel.lifecycle_status = ready_for_video`
— chia toàn bộ chương đã dịch thành 1-5 phần đều nhau.

**Settings**: dùng bảng key-value chung của `platform/` (quy ước ở
[docs/platform-and-licensing.md](./platform-and-licensing.md) mục 3) —
`key TEXT PK, value JSON, updated_at`, KHÔNG phải bảng cột cứng riêng cho
Crawl. **CHỈ 1 key thật sự toàn cục**: `crawl.max_chapters_translate_per_day`
(dùng chung với Translate). Các key CÒN LẠI (`scan_window`,
`max_chapters_per_story`, `max_pages_per_scan`, `max_consecutive_errors`,
`narration_filter`, `completion_filter`) là setting RIÊNG TỪNG SITE, lưu
dạng `crawl.<tên>.<source_key>` (mục 9.0/9.1) — sửa 16-17/9/2026 theo yêu
cầu "setting riêng cho từng site". Đã bỏ hẳn `video.target_videos_per_story_min/max`
(17/9/2026 — placeholder cho Video service chưa code, gây rối không cần
thiết). Giá trị ở mục 7/9.1 chỉ là **default khởi tạo lần đầu** (seed) —
người dùng chỉnh trực tiếp trên UI, job hàng ngày luôn đọc Settings hiện
tại từ DB tại thời điểm chạy, không đọc hằng số trong code.

## 6. Luồng job hàng ngày (quét thể loại → phát hiện truyện mới → crawl toàn bộ)

```
1. adapter = SOURCES[genre.source_key]
2. page = 1; while discovered < scan_window và page <= max_pages_per_scan:
     candidates = adapter.list_genre_novels_page(genre.list_url, page)
     # scan_window: số truyện MỚI muốn CHẤP NHẬN mỗi lần quét (mục 7) — KHÔNG
     # phải "số truyện đầu danh sách xét rồi dừng bất kể kết quả" (bug đã
     # gặp thật: top đầu danh sách bị loại gần hết thì quét gần như vô ích).
     # candidates rỗng ở page=1 → lỗi thật (site đổi cấu trúc/chặn).
     # candidates rỗng ở page>1 → hết danh sách thật, dừng, KHÔNG phải lỗi.
     Với mỗi c trong candidates (dừng ngay khi discovered == scan_window):
       a. Nếu đã có Novel(source_url=c.url) trong DB → bỏ qua (đã
          discovered rồi) HOẶC "Đồng bộ chương mới" nếu đủ điều kiện (mục
          9.2b — cap MAX_EXISTING_SYNCS_PER_SCAN/lượt quét).
       b. Nếu chưa có → đây là ứng viên mới, kiểm tra tiêu chí ngắn+hoàn thành (mục 7):
            - Không khớp → tạo Novel(lifecycle_status=rejected), dừng, không crawl.
            - Khớp → tạo Novel(lifecycle_status=discovered), crawl TOÀN BỘ chương
              (không phải chỉ chương mới — vì truyện đã hoàn thành, đây là lần
              đầu và cũng là lần duy nhất crawl truyện này):
                for mỗi chapter (thứ tự tăng dần):
                  - text = adapter.fetch_chapter_content(c.url)
                  - lỗi/không đạt validate(text) → BỎ QUA đúng chương này,
                    crawl TIẾP chương sau (sửa 17/9/2026, theo yêu cầu thật
                    "bỏ qua chương lỗi, crawl tiếp các chap sau") — KHÔNG
                    advance last_chapter_index qua chương bị bỏ qua (để
                    "Crawl lại"/"Thử lại" sau còn tự nhận ra cần bù đúng
                    chương đó, mục 9.6). Lỗi liên tiếp NHIỀU chương mới suy
                    đoán site đang chặn/lỗi thật và dừng hẳn
                    (`max_consecutive_errors`/`MAX_CONSECUTIVE_CHAPTER_
                    FAILURES` — mục 7d).
                  - lưu file + tạo Chapter(status=crawled, queued_for_translate=True)
                  - novel.last_chapter_index = chapter.index  (resume nếu lỗi giữa chừng)
                Xong vòng lặp: ĐỦ mọi chương → fully_crawled. THIẾU vài
                chương lẻ tẻ (không chạm ngưỡng liên tiếp) → VẪN
                fully_crawled + success=True, chỉ ghi chú "Thiếu N chương"
                vào error_message (không im lặng, nhưng cũng không chặn cả
                truyện) — bấm "Crawl lại" từng chương thiếu (mục 9.6) hoặc
                "Thử lại" cả truyện (mục 9.2b) để bù nốt.
     page += 1
3. Hết vòng lặp mà vẫn chưa đủ scan_window (chạm max_pages_per_scan) → ghi
   message gợi ý tăng "Số trang tối đa/lượt quét", KHÔNG coi là lỗi (Genre
   vẫn `last_run_status=done`, chỉ là ít/không có truyện mới lần này).
4. Lỗi thật (site chặn, đổi cấu trúc...) ở bước 2 không dừng các
   candidate/thể loại khác — chỉ dừng đúng thể loại đang quét, log lỗi.
```

## 7. Cấu hình đã chốt

**Nguồn + thể loại — KHÔNG chỉ giới hạn Kinh dị, KHÔNG chỉ 1 site.** Mỗi
SITE (source_key) có sẵn 1 danh sách thể loại/URL liệt kê hardcode để chọn,
nhưng tại 1 thời điểm mỗi site chỉ có ĐÚNG 1 lựa chọn "active" — chọn qua
UI select box PHẲNG, 1 box riêng cho từng site (mục 9.2). Hardcode ở đây
nghĩa là "danh sách option có sẵn để chọn", không phải "chỉ chạy đúng 1 thể
loại cố định toàn hệ thống".

**~31 nguồn đã đăng ký** (17/9/2026 — con số THẬT thay đổi liên tục khi
thêm site mới, xem `registry.py SOURCES`/`GENRE_SEEDS` để có danh sách
CHÍNH XÁC tại thời điểm đọc — tài liệu này không hardcode lại từng site vì
không theo kịp tốc độ thêm site). Mỗi site 1 file adapter riêng (mục 4b),
tự khai `SourceConfig` + số dòng `GENRE_SEEDS` phù hợp với chính site đó.
**Quy ước đặt tên `genre_key` bắt buộc** (soi trực tiếp comment ngay trên
`GENRE_SEEDS` trong `registry.py` — nguồn chân lý, không chép lại ở đây để
tránh lệch): 2 site có CÙNG 1 thể loại thật (cùng khái niệm nội dung) phải
dùng CHUNG `genre_key` + nhãn Việt hoá tương tự nhau (test
`tests/test_genre_naming_consistency.py` enforce điều này tự động mỗi lần
CI chạy); site không có thể loại đó thật thì KHÔNG được seed key đó (không
bịa thêm cho "đều số lượng" giữa các site).

`biquge.pro` (site đầu tiên, nguồn tham chiếu ban đầu khi thiết kế) đã
**gỡ khỏi registry hẳn** — không còn file adapter, không còn seed nào —
sau khi xác nhận trang chi tiết truyện lỗi `HTTP 520` **dai dẳng, 100%**
(9 lần gọi thật khác nhau đều lỗi giống hệt, 15/9/2026), không phải do
mạng/bot. Site kế thừa vai trò "site tham chiếu, đã verify kỹ nhất" trong
tài liệu này từ đó là `bqgxs_com` (mục 7b — vẫn còn nguyên giá trị làm ví
dụ mẫu về QUY TRÌNH verify 1 site mới, dù bản thân danh sách thể loại của
nó không còn là "toàn bộ site đang có" nữa).

**Site cần vượt chống-bot nặng hơn HTML thô** (CF challenge, TLS
fingerprint, VIP/login, ảnh chương, payload mã hoá) dùng 3 tầng fetch +
pipeline VIP riêng — xem mục 4c/8, KHÔNG lặp lại ở đây.

*Đây là cấu hình cho "gói cơ bản" nếu bán tool (xem
[platform-and-licensing.md](./platform-and-licensing.md) mục 5) — đổi
site/thể loại cho khách khác = sửa `registry.py` (thêm/bớt seed) hoặc thêm
1 file adapter mới, không đổi kiến trúc.*

**Cap/ngân sách — là `Settings` chỉnh được qua UI (mục 5), số dưới đây chỉ
là giá trị seed ban đầu:**

| Tham số (Settings) | Giá trị seed | Ý nghĩa |
|---|---|---|
| `scan_window` | **5** | Số truyện MỚI muốn CHẤP NHẬN mỗi lần quét — không phải "cửa sổ quét N truyện đầu rồi dừng" nữa: tự dò sang trang sau nếu top đầu danh sách bị loại hết (mục 7d), tới khi đủ số này. |
| `max_pages_per_scan` | **3** | Chặn dò vô tận khi tỉ lệ loại quá cao (vd chọn option "Hot nhất" của 1 site) — quét hết số trang này mà vẫn chưa đủ `scan_window` thì dừng, ghi rõ lý do vào kết quả (mục 7d, 9.2). |
| `max_chapters_translate_per_day` | **20** | Trần chương dịch/ngày, toàn hệ thống — 1 truyện dài hơn cap sẽ tràn dịch sang hôm sau. |
| `max_chapters_per_story` | **50** | Ngưỡng "ngắn" — ước lượng 1 video ≈ 20-30 phút đọc ≈ vài nghìn từ, 5 video ≈ đủ cho truyện ~50 chương ngắn (~1.000-1.500 ký tự Hán/chương). Chỉnh trực tiếp trên UI khi đo được thời lượng audio thật, không cần sửa code/deploy lại. |

*Vì sao tách thành Settings thay vì hardcode:* đây đều là con số "đoán rồi
tinh chỉnh" (đặc biệt `max_chapters_per_story` — chỉ biết chính xác sau khi
nghe thử audio thật dài bao lâu/chương), nên phải sửa được nhanh mà không
đụng code. UI có 1 trang Settings đơn giản (vài input số + nút lưu), gọi API
`PATCH /settings`.

**Cap/ngân sách — là `Settings` chỉnh được qua UI (mục 5), số dưới đây chỉ
là giá trị seed ban đầu:**

| Tham số (Settings) | Giá trị seed | Ý nghĩa |
|---|---|---|
| `scan_window` | **5** | Số truyện MỚI muốn CHẤP NHẬN mỗi lần quét — không phải "cửa sổ quét N truyện đầu rồi dừng" nữa: tự dò sang trang sau nếu top đầu danh sách bị loại hết (mục 7d), tới khi đủ số này. |
| `max_pages_per_scan` | **3** | Chặn dò vô tận khi tỉ lệ loại quá cao (vd chọn thể loại "Hot nhất", mục 7) — quét hết số trang này mà vẫn chưa đủ `scan_window` thì dừng, ghi rõ lý do vào kết quả (mục 7d, 9.2). |
| `max_chapters_translate_per_day` | **20** | Trần chương dịch/ngày, toàn hệ thống — 1 truyện dài hơn cap sẽ tràn dịch sang hôm sau. |
| `max_chapters_per_story` | **50** | Ngưỡng "ngắn" — ước lượng 1 video ≈ 20-30 phút đọc ≈ vài nghìn từ, 5 video ≈ đủ cho truyện ~50 chương ngắn (~1.000-1.500 ký tự Hán/chương). Chỉnh trực tiếp trên UI khi đo được thời lượng audio thật, không cần sửa code/deploy lại. |

*Vì sao tách thành Settings thay vì hardcode:* đây đều là con số "đoán rồi
tinh chỉnh" (đặc biệt `max_chapters_per_story` — chỉ biết chính xác sau khi
nghe thử audio thật dài bao lâu/chương), nên phải sửa được nhanh mà không
đụng code. UI có 1 trang Settings đơn giản (vài input số + nút lưu), gọi API
`PATCH /settings`.

### 7b. Nguồn thứ 2 — `bqgxs_com` (dùng search từ khoá, không có mục Kinh dị riêng)

Đã soi HTML thật, verify bằng mạng thật (không sandbox), hoạt động đầy đủ:

| Bước | URL/selector thật |
|---|---|
| Phát hiện truyện | `https://www.bqgxs.com/search.php?q=恐怖` — selector `div.box.hot dl` |
| Chi tiết + danh sách chương | selector `div.book_list2 a` — **giới hạn hiển thị tối đa 100 chương gần nhất** (giới hạn thật của site, không phải bug code — không ảnh hưởng vì ngưỡng "ngắn" của mình luôn < 100) |
| Nội dung chương | selector `article` — **chương dài bị chia nhiều trang** (`xxx.html`, `xxx_2.html`...), đã code tự nối lại (`paginated_content=True` trong `SourceConfig`) |

Vì site không có mục "Kinh dị" trong nav (chỉ có 玄幻/武侠/都市/历史/网游/科幻/言情/其他),
dùng search từ khoá "恐怖" thay cho trang thể loại cố định — cùng khuôn dạng
`SourcePort`, không cần kiến trúc riêng. Test thật (15/9/2026, `scan_window=5`):
5/5 kết quả đầu đều là truyện **đang ra tiếp** (chưa hoàn thành) → bị
`rejected` đúng như thiết kế. Nhờ fix `scan_window` = "số muốn nhận" thay vì
"cửa sổ quét cố định" (mục 7d), giờ sẽ tự dò tiếp thay vì dừng ở 5 kết quả
đầu này.

**8 thể loại còn lại có trang riêng** (thêm 16/9/2026, đã soi HTML thật):
site thật ra CÓ mục thể loại — `/list1/` (玄幻) tới `/list8/` (其他) — chỉ
riêng Kinh dị là không có, nên trước đây chỉ thấy đúng 1 lựa chọn. Cùng
selector `div.box.hot dl` với trang search. Phân trang: `/list1/` (trang 1)
→ `/list1/2.html` (trang 2) — khác cả 2 kiểu phân trang khác của site này
(`&p=N` ở search, đổi số cuối `_N.html` ở `/top/`), `BqgxsComSource`
(`bqgxs_com_source.py`) tự nhận diện đúng kiểu qua `_paginate_list_url`.

**Mỗi thể loại trong 8 cái này CÓ bảng xếp hạng riêng** (phát hiện
17/9/2026, theo câu hỏi thật "sao chia 2 block riêng, không filter cùng
lúc được à"): `/top/all_{id}_1.html` với ĐÚNG cùng id 1-8 ở trên (vd
`all_1_1.html` = "最新玄幻小说排行榜" = xếp hạng Huyền huyễn, đã verify HTML
thật cho cả 8 id — VÀ chính trang `/top/` cũng có ĐÚNG 8 tab `<a>` trỏ
thẳng tới 8 URL này, nhãn 玄幻/武侠/都市/历史/网游/科幻/言情/其他, xác nhận đây
là tab CÓ THẬT trên site chứ không phải URL suy đoán) — khác hẳn biquge.pro
(bảng xếp hạng CHUNG toàn site, không lọc được theo thể loại, xem mục 7).
Mỗi thể loại gốc trong 8 cái này seed THÊM 1 dòng `_hot` PHẲNG, độc lập
(genre_key riêng, không gộp cặp với bản mặc định) — Kinh dị (search-based)
và bảng xếp hạng CHUNG toàn site (`/top/all_0_1.html`, đứng 1 mình) thì
KHÔNG có biến thể `_hot` riêng (site không có URL kết hợp tương ứng). Sửa
17/9/2026 lần 2: từng gộp cặp "mặc định + `_hot`" bằng `family_key` để UI
hiện thêm select con "Sắp xếp" đi cùng "Thể loại" — đã BỎ HẲN theo phản hồi
thật "dựa vào menu của site ý... ko tự tạo thêm menu cho select": dù các
URL này có thật, việc UI tự GHÉP CẶP chúng thành 1 khối 2-select vẫn là 1
cấu trúc UI tự bịa ra, không phải mirror thẳng cấu trúc thật của site (mỗi
tab trên site là 1 link độc lập) — nay mỗi dòng `_hot` là 1 option PHẲNG,
ngang hàng, y hệt mọi option khác trong CHÍNH select "Thể loại".

**Sửa 1 lỗi thiết kế phát hiện khi thêm nguồn này**: tiêu chí "đã hoàn thành"
trước đây đọc từ text tóm tắt trên trang danh sách (`NovelRef.latest_chapter_title`)
— nhưng `bqgxs_com` không có field này ở trang search. Đã sửa: luôn xác nhận
qua **chương cuối cùng fetch được thật** (`chapters[-1].title`) thay vì tin
tóm tắt, đúng tinh thần "đừng tin dữ liệu tóm tắt" ở mục 2.

**Định nghĩa "truyện ngắn, đã hoàn thành"** (đã thử tìm nguồn chuyên truyện
kinh dị ngắn khác — Zhihu, Baidu Tieba, nhóm Douban, guishiji.com, qimao.com,
17k.com — tất cả đều chặn bot/không kết nối được/JS-render rỗng, không có
nguồn nào dễ crawl hơn `biquge.pro`) ⇒ xử lý bằng bộ lọc trên chính danh sách
Kinh dị, không cần nguồn riêng — 1 truyện được nhận (`discovered`, không
`rejected`) khi **cả 2 điều kiện** sau đúng:

1. Chương mới nhất chứa từ khoá hoàn thành (`完本`/`大结局`/`尾声`/`完结`) — lấy
   được ngay từ trang danh sách thể loại, không cần mở trang chi tiết.
2. Tổng số chương ≤ `max_chapters_per_story` — cần mở trang chi tiết truyện
   để đếm (lưu ý trang chi tiết `biquge.pro` từng bị lỗi `520` lúc test, xem
   dưới).

Truyện hoàn thành nhưng **dài hơn** ngưỡng → `rejected`, không crawl (đây là
truyện dài, ngoài phạm vi mục tiêu "1-5 video"). Truyện **chưa hoàn thành**
→ luôn `rejected`, không chờ nó ra xong (không còn "theo dõi liên tục" nữa).

### 7c. Lọc theo ngôi kể — option `crawl.narration_filter`

Nhiều kênh audio kể chuyện hợp giọng kể ngôi thứ nhất ("tôi") hơn ngôi thứ
ba thông thường. Thay vì hardcode 1 cờ bật/tắt riêng, làm thành **1 Settings
option chọn được** (giống các option khác ở mục 9.1), áp dụng cho **mọi
thể loại** đang bật, không riêng gì Kinh dị:

| Giá trị | Ý nghĩa |
|---|---|
| `any` | Không lọc (mặc định an toàn nếu tắt tính năng) |
| `first_person` | Chỉ nhận truyện kể theo ngôi thứ nhất ("tôi"/"我") |
| `third_person` | Chỉ nhận truyện kể theo ngôi thứ ba |

**Cách đánh giá**: tải **chương đầu tiên làm mẫu** (chỉ tải khi
`narration_filter != "any"`, tránh tốn request thừa lúc không cần lọc),
đếm tỉ lệ đại từ "我" so với "他"/"她" trong mẫu đó — heuristic tần suất đơn
giản (không phải mô hình NLP), ngưỡng mặc định 60%. Áp dụng SAU khi đã qua
tiêu chí ngắn+hoàn thành (mục 7b) — truyện không hoàn thành bị loại trước,
không tốn thêm 1 request tải mẫu vô ích.

Giá trị seed mặc định: `"first_person"` (theo hướng kinh doanh hiện tại —
đọc truyện dạng audio kể chuyện), chỉnh được về `"any"`/`"third_person"`
qua UI Settings bất kỳ lúc nào, không cần đổi code.

### 7d. `scan_window` = số truyện MUỐN NHẬN, tự dò tiếp nếu bị loại hết

**Bug thật đã gặp** (16/9/2026): `scan_window` (vd 10) trước đây chỉ lấy
ĐÚNG 10 truyện đầu trang danh sách rồi dừng — nếu set
`max_chapters_per_story` nhỏ (lọc chặt) hoặc chọn thể loại có tỉ lệ dài cao
(vd "Hot nhất", mục 7 ở trên), 10 truyện đó có thể bị loại HẾT mà hệ thống
không dò thêm, quét coi như vô ích dù danh sách thể loại còn rất nhiều
truyện chưa xét.

**Sửa đúng**: `CrawlGenreUseCase._scan()` giờ lặp qua nhiều TRANG của cùng
1 danh sách (`SourcePort.list_genre_novels_page(list_url, page)`, verify
bằng HTML thật cho cả 2 site — biquge.pro dùng `?page=N`, bqgxs.com dùng
`&p=N` (trang search) hoặc đổi số cuối `_N.html` (trang `/top/`)) cho tới
khi **đủ `scan_window` truyện được CHẤP NHẬN**, hết danh sách thật (trang
sau trả rỗng), hoặc chạm setting mới **`max_pages_per_scan`** (mặc định 3)
— chặn dò vô tận khi tỉ lệ loại quá cao, tốn quá nhiều request/thời gian.
Site không khai `paginate_list_url` (chưa biết quy luật phân trang) chỉ xét
đúng trang 1, không lỗi, chỉ dừng sớm hơn.

Không đủ truyện sau khi chạm cap → `Genre.last_run_messages` ghi rõ gợi ý
tăng "Số trang tối đa/lượt quét" ở Cài đặt, `last_run_status` vẫn `done`
(không phải lỗi — chỉ là ít/không có truyện mới lần này, xem mục 9.2).

## 8. Site chống-bot nặng (wenku8 / ciweimao / qidian / Zhihu…)

Không còn “phase 2 bỏ qua”. Cùng mô hình mục 4c:

- **wenku8**: tầng 1b (`curl_cffi` + cookie); fallback Playwright nếu CF.
- **ciweimao**: cookie session; text chapter qua API; ảnh VIP → OCR.
- **qidian**: cookie; free HTML; VIP encrypted → Node decrypt; thiếu Node/cookie → lỗi rõ.
- **Zhihu / tương tự**: adapter tầng 2 Playwright + cookie user (cùng hạ tầng).

Rủi ro: cookie hết hạn → user dán lại qua UI session; ToS từng site — chỉ
dùng account của chính user.

## 9. Giao diện & hành vi (UI/UX) — React FE gọi REST API của context này

Nguyên tắc chung: **không có gì "im lặng"** — mọi hành động đều có trạng
thái loading/thành công/lỗi rõ ràng (không dùng `alert()` chặn UI); vì quy
mô 1 người dùng, **không cần websocket** — chỗ nào cần cập nhật realtime
(đang crawl) thì FE tự poll lại API mỗi ~3-5s **chỉ khi có việc đang chạy**,
dừng poll khi xong (tránh poll vô thời hạn tốn tài nguyên).

### 9.0 Trang Danh sách site — điểm vào chính (thay thế 2 tab cũ)

**Sửa 16/9/2026** theo phản hồi thật "UI đang sai — định tích hợp rất
nhiều site, phải có 1 trang list các site, bấm vào từng site mới hiện chi
tiết + action + setting riêng, không để chung sang tab Truyện". Trước đó
2 tab top-level "Thể loại" và "Truyện" đều hiển thị TẤT CẢ site gộp chung,
không mở rộng tốt khi thêm nhiều site khác nhau. Kiến trúc mới:

```
/sites              -> danh sách site (GET /sites, mỗi dòng bấm vào được)
/sites/{source_key} -> trang chi tiết ĐÚNG 1 site (gộp mọi thứ liên quan
                        site đó: chọn thể loại, Quét ngay, thêm truyện bằng
                        URL, danh sách truyện, cài đặt riêng)
```

`GET /sites` chỉ trả site THẬT (`SourcePort.is_test == False`) — nguồn nội
bộ dùng để test (`demo_local`, đọc file cục bộ, không phải site thật) KHÔNG
hiện ở đây (vẫn dùng được ở pytest và trang "Nâng cao"/dry-run, chỉ ẩn khỏi
danh sách cho người dùng thật).

Trang chi tiết site (`/sites/{source_key}`) có 4 phần, xếp dọc:

1. **Chọn thể loại + Quét ngay** ("quét NHIỀU truyện cùng lúc" — mục 9.2).
2. **Thêm truyện bằng URL** ("quét TỪNG truyện/chương MỘT" — mục 9.3).
3. **Cài đặt riêng site này** (mục 9.1 — thu gọn mặc định, đỡ rối mắt).
4. **Danh sách truyện đã crawl từ site này**, tự phân trang (mục 9.5).

### 9.1 Cài đặt riêng từng site (trong trang chi tiết site)

**Sửa 16/9/2026** theo yêu cầu "setting riêng cho từng site" — trước đó
các setting dưới đây dùng CHUNG 1 giá trị cho mọi site, không hợp lý khi
mỗi site có tốc độ/độ dài truyện phổ biến khác nhau. Lưu dưới key
`"crawl.<tên>.<source_key>"` (`platform_/settings_store.py per_site_key()`,
KHÔNG cần bảng riêng — vẫn generic key-value như cũ, chỉ thêm hậu tố):

| Field | Loại | Validate |
|---|---|---|
| Số truyện muốn nhận mỗi lần quét (`scan_window`) | number input | số nguyên ≥ 1 |
| Ngưỡng số chương tối đa/truyện (`max_chapters_per_story`) | number input | số nguyên ≥ 1 |
| Số trang tối đa/lượt quét (`max_pages_per_scan`) | number input | số nguyên ≥ 1 |
| Số lỗi liên tiếp tối đa/lượt quét (`max_consecutive_errors`) | number input | số nguyên ≥ 1 |
| Lọc theo ngôi kể (`narration_filter`) | select: any/first_person/third_person | — |

- Vào trang site → `GET /settings` (trả TOÀN BỘ key, kể cả của site khác —
  FE tự lọc đúng key của site đang xem), panel mặc định THU GỌN, bấm mở
  rộng mới thấy form. Mỗi field có ghi chú nhỏ (lấy từ bảng mục 7).
- Nút **Lưu** → `PATCH /settings` với key đã gắn hậu tố site → toast "Đã
  lưu cài đặt site" — KHÔNG đụng setting của site khác.
- Setting THẬT SỰ toàn cục (không thuộc site nào — trần chương dịch/ngày,
  số video mục tiêu/truyện) vẫn nằm ở trang **Cài đặt** riêng (tab top-level,
  không đổi).

### 9.2 Chọn thể loại + "Quét ngay" (trong trang chi tiết site)

**ĐÚNG 1 card/site, ĐÚNG 1 select "Thể loại" PHẲNG** — mọi option của site
(kể cả bảng xếp hạng chung "Hot nhất" VÀ các bảng xếp hạng riêng theo từng
thể loại, vd 8 dòng `_hot` của bqgxs.com) là 1 DÒNG ngang hàng nhau trong
CHÍNH select này, KHÔNG có select con/khối gộp cặp nào khác. Lịch sử sửa
2 lần (17/9/2026):
1. Đã thử tách "Xếp hạng" thành card riêng — phản hồi thật "sao vẫn chia
   làm 2 block" → gộp lại còn đúng 1 card.
2. Đã thử gộp "Thể loại" + select con "Sắp xếp" theo cặp `family_key` (mỗi
   thể loại gốc + biến thể hot của nó đi cùng nhau) — phản hồi thật "dựa
   vào menu của site ý, mỗi site nó độc lập đó, ko tự tạo thêm menu cho
   select" → bỏ hẳn `family_key`/select con "Sắp xếp": dù các URL riêng lẻ
   là có thật (đã verify HTML, xem mục 7), việc UI tự GHÉP CẶP chúng thành
   1 khối 2-select vẫn là 1 cấu trúc tự bịa, không mirror đúng cấu trúc
   thật của site (site hiện mỗi tab là 1 link phẳng, độc lập) — nay mỗi
   dòng là 1 option phẳng, y hệt cách site tự hiện menu của nó.

**UI vẫn khớp đúng khả năng THẬT của từng site** — không áp 1 khuôn chung:
site nào có bao nhiêu option thật (soi từ chính nav/category/tab của site
đó) thì select có bấy nhiêu dòng, không bịa thêm cho "đều số lượng" giữa
các site (mục 7 — quy ước đặt tên `genre_key`).

**ĐÚNG 1 lựa chọn active/site tại 1 thời điểm** (site chỉ chạy job cho 1
thứ) — không có gì active hiện placeholder "Chưa dùng" (thực tế hiếm gặp,
vì seed mặc định luôn có sẵn 1 dòng active):

| Phần tử | Nội dung |
|---|---|
| Select box "Thể loại" | PHẲNG, gồm MỌI option của site (kể cả "Hot nhất"), không nhóm cặp |
| URL đang chọn | hiển thị dưới card, chỉ để tham khảo |
| Hành động | 1 nút **Quét ngay** — chạy job cho lựa chọn ĐANG active của site |

- Chọn 1 option (ở "Thể loại" hoặc "Sắp xếp") đều gọi `PATCH /genres/{id}`
  với `{"enabled": true}` → BE (`SetActiveGenreUseCase`) tự tắt MỌI lựa
  chọn khác CÙNG site, không đụng site khác → FE nhận lại genre vừa bật,
  cập nhật state cục bộ (đánh dấu mọi sibling cùng site thành tắt) mà
  không cần gọi lại toàn bộ danh sách.
- Muốn 1 site tạm KHÔNG quét gì cả → gọi `PATCH /genres/{id}` với
  `{"enabled": false}` trên chính thể loại đang active (chỉ tắt riêng nó,
  không tự bật thể loại khác) — hiện chưa có nút riêng cho thao tác này
  trên UI, làm sau nếu cần.
- Bấm **Quét ngay** → `POST /genres/{id}/run-now` (id = thể loại đang active
  của site). Quét thật có thể mất NHIỀU PHÚT (nhiều truyện x nhiều chương,
  retry/backoff khi site chậm/chặn) — endpoint này chạy NỀN (1 thread riêng
  phía BE) và trả về **ngay lập tức** (202) Genre ở trạng thái "running",
  KHÔNG giữ request chờ tới khi quét xong như bản đầu (dễ timeout phía
  trình duyệt, và nếu người dùng tải lại trang giữa chừng thì mất hết dấu
  vết là đang có gì chạy — đây là bug thật đã gặp lúc build tính năng).
- **Trạng thái LƯU vào chính Genre** (`last_run_status`:
  `idle`/`running`/`done`/`error`, `last_run_started_at`,
  `last_run_finished_at`, `last_run_discovered/rejected/errors`,
  `last_run_messages`) — không chỉ tồn tại trong state cục bộ của FE. FE
  poll lại `GET /genres` mỗi 3s CHỈ KHI có ít nhất 1 site đang "running"
  (dừng poll khi hết), nên:
  - Nút **Quét ngay** tự đổi "Đang quét…" + disable đúng theo trạng thái
    thật từ BE, không phải chỉ theo lượt bấm gần nhất của riêng tab đó.
  - Tải lại trang / mở tab mới giữa lúc đang quét vẫn thấy đúng "Đang quét
    từ HH:mm:ss…", không tưởng nhầm là không có gì chạy.
  - Quét xong (dù thành công hay lỗi) hiện banner kết quả ngay dưới card đó
    ("3 mới, 2 bị loại, 0 lỗi") — kể cả khi banner đó xuất hiện ở 1 tab
    KHÁC tab đã bấm nút (mọi tab đang mở trang Genres đều thấy cùng 1 sự
    thật từ DB).
  - Khoá `genre-run:{id}` (mục 8) được GIỮ suốt thời gian thread nền chạy,
    không nhả ngay khi request ban đầu trả 202 — bấm "Quét ngay" 2 lần liên
    tiếp hoặc đúng lúc job lịch chạy cùng thể loại vẫn báo 409 như cũ.
  - Job lịch hàng ngày (scheduler.py) dùng CHUNG `CrawlGenreUseCase.execute()`
    nên kết quả chạy tự động cũng hiện lên trang này y hệt, không cần code
    riêng.
- Seed mặc định (`registry.py GENRE_SEEDS`): mỗi site có sẵn ĐÚNG 1 dòng
  `enabled: True` (dòng đầu) — khớp bất biến "1 active/site" ngay từ lần
  chạy đầu tiên, không cần người dùng tự chọn lại.
- **Cập nhật (đã áp dụng, không còn là gap)**: `POST /novels`, `/retry`,
  `/force-accept` (mục 9.3, 9.4) giờ CŨNG chạy NỀN (202 + thread riêng),
  cùng khoá `crawl-novel:{novel_id}` — cùng lý do với "Quét ngay" ở trên
  (truyện dài/site chậm không nên block request).

### 9.1b Cookie phiên đăng nhập cho site cần login/VIP

Site cần cookie session thật (VIP, chống-bot nặng — mục 4c/8) có ô nhập
"Cookie phiên đăng nhập" riêng trong trang chi tiết site (`PUT
/sites/{source_key}/session`, lưu qua `platform_/session_cookies.py` —
CHÍNH LÀ 1 key trong Settings, không bảng riêng) + nút **Kiểm tra** (`POST
/sites/{source_key}/session/probe`, xác nhận cookie còn dùng được thật,
không đợi tới lúc crawl thật mới biết hỏng). FE có sẵn hướng dẫn RIÊNG cho
từng site (đăng nhập ở đâu, cookie tên gì cần copy) — xem
`sessionGuides.ts` phía frontend, tránh người dùng phải tự tìm hiểu. Cookie
lưu dạng text thường (không mã hoá) — chấp nhận được cho self-host 1 người
dùng (xem `platform-and-licensing.md`), KHÔNG phù hợp nếu deploy multi-tenant
thật mà không mã hoá thêm.

### 9.2b Huỷ quét giữa chừng + Đồng bộ chương mới (bổ sung sau bản thiết kế gốc)

**Huỷ quét ("Cancel")**: `POST /genres/{id}/cancel` — đặt 1 cờ dừng
(`platform_/run_cancel.py`, `threading.Event` theo `genre_id`) mà thread
đang quét TỰ KIỂM TRA giữa 2 candidate/2 chương (không kill thread cứng,
tránh dữ liệu dở dang giữa chừng 1 chương). Dừng xong, Genre chuyển
`last_run_status="cancelled"` — TÁCH RIÊNG khỏi `"error"` (mục 5) đúng tinh
thần "không có gì im lặng" (mục 9): người dùng tự bấm Huỷ khác hẳn site bị
lỗi/chặn, không nên hiện cùng 1 màu badge lỗi.

**Tiến độ sống ("live progress")**: trong lúc `last_run_status="running"`,
FE poll thêm `GET /genres/{id}/progress` (khác `GET /genres` ở trên — trả
snapshot chi tiết HƠN: đang ở trang mấy, đang xét truyện nào, đang crawl
chương mấy/tổng bao nhiêu) mỗi ~1s, dừng ngay khi hết "running". Lưu
in-memory (`platform_/run_progress.py`, mất khi restart process — KHÔNG
thay thế `last_run_*` đã lưu DB, chỉ phục vụ hiển thị lúc đang chạy).

**Đồng bộ chương mới ("Đồng bộ"/sync)**: site thường đẩy truyện VỪA có
chương mới lên ĐẦU danh sách thể loại — job/nút "Quét ngay" gặp lại 1
truyện đã biết (`source_url` trùng) sẽ thử refresh mục lục, so với
`last_chapter_index` đã lưu, CHỈ crawl phần CHƯA có (không tải lại từ đầu).
Áp dụng cho novel đang `fully_crawled` (có chương mới thật) hoặc `error`
(retry phần bị lỗi trước đó, vd sau khi cập nhật cookie) — cap
`MAX_EXISTING_SYNCS_PER_SCAN` lượt sync/lần quét (tránh 1 genre có nhiều
truyện cũ làm chậm hẳn việc tìm truyện MỚI, vốn là mục tiêu chính của job).
Nút **Thử lại** ở mục 9.5 gọi cùng cơ chế này cho 1 truyện cụ thể theo yêu
cầu tay (`POST /novels/{id}/retry`), và `POST /novels/retry-errors` xếp
hàng retry HÀNG LOẠT mọi novel `error` của 1 site (chạy tuần tự 1 thread
nền, tránh dội site) — dùng sau khi cập nhật cookie phiên đăng nhập ở trên
làm hỏng hàng loạt truyện VIP cùng lúc.

### 9.3 Thêm truyện bằng URL — "quét từng truyện/chương MỘT" (trong trang chi tiết site)

Khác hẳn "Quét ngay" (mục 9.2 — tự phát hiện NHIỀU truyện cùng lúc theo
thể loại): đây là quét ĐÚNG 1 truyện/chương do người dùng tự dán URL. Luôn
scoped vào site đang xem (không có dropdown chọn nguồn nữa — sửa 16/9/2026,
trước đó form này đứng độc lập, phải tự chọn site mỗi lần):

| Field | Loại | Validate |
|---|---|---|
| URL trang mục lục **hoặc URL 1 chương** (mục 9.3b) | text input (KHÔNG dùng `type="url"` — 1 số nguồn nhận đường dẫn không phải HTTP URL chuẩn, vd nguồn test đọc file cục bộ) | bắt buộc nhập |
| ☐ Vẫn thêm dù không đạt tiêu chí "ngắn" | checkbox, mặc định **tắt** | — |

- Submit → `POST /novels`. BE kiểm tra trùng URL trước:
  - Đã tồn tại → báo "Truyện này đã có trong hệ thống" kèm link tới truyện
    đó, KHÔNG tạo bản ghi mới.
  - Chưa có → chạy thử lấy danh sách chương (như dry-run) để xác nhận URL
    sống được, rồi mới tạo `Novel`. Lỗi (site chặn/sai selector) → hiện lỗi
    ngay trong form, không tạo bản ghi rác trong DB.
- Nếu KHÔNG tick checkbox và truyện không đạt tiêu chí ngắn+hoàn thành →
  BE trả lỗi rõ ràng "Truyện này chưa hoàn thành / dài hơn ngưỡng Y chương"
  thay vì âm thầm tạo `rejected`.
- Thêm thành công → chuyển sang trang chi tiết truyện (9.6), trạng thái
  hiện "Đang crawl…", FE tự poll tới khi `fully_crawled`/`error`.

### 9.3b Crawl từ URL 1 chương chỉ định (không cần đúng trang mục lục)

Người dùng hay copy nhầm (hoặc cố ý chỉ có) link 1 chương thay vì link mục
lục. Xử lý: **cùng 1 field URL ở mục 9.3**, backend tự thử theo thứ tự:

```
1. Thử list_chapters(url) — coi url là trang mục lục (hành vi cũ).
2. Nếu lỗi VÀ source.derive_novel_url(url) trả về URL khác url
   (site này CÓ hỗ trợ suy ra):
     - Suy ra url_mục_lục, kiểm tra trùng theo url_mục_lục (tránh tạo
       trùng nếu truyện đã được thêm qua đường mục lục trước đó).
     - Thử lại list_chapters(url_mục_lục).
3. Nếu source.derive_novel_url(url) trả None (site KHÔNG hỗ trợ) hoặc bước
   2 vẫn lỗi -> trả lỗi gốc, KHÔNG giả vờ thành công.
```

**Chỉ hỗ trợ ở site có quy luật URL đáng tin cậy** — `SourcePort` có thêm
method `derive_novel_url(chapter_url) -> str | None`, implement tuỳ site
(đa số ~29 site hiện tại — 22/29 — CÓ implement, vd `bqgxs_com`: URL chương
`.../131/131542/275597.html` → bỏ segment cuối → `.../131/131542/`, đã
verify bằng HTML thật; `demo_local` implement để test). Site KHÔNG hỗ trợ
(trang mục lục dùng id khác hẳn id trong URL chương, không có quy luật
đáng tin để đoán) thì `derive_novel_url` trả `None` — danh sách site nào
hỗ trợ CHÍNH XÁC tại thời điểm đọc: `grep novel_url_from_chapter
src/crawl/infrastructure/sources/*.py`.

Thêm site mới muốn hỗ trợ tính năng này: set `SourceConfig.novel_url_from_chapter`
(1 hàm biến đổi URL) trong `registry.py` — để trống (mặc định) nghĩa là
site đó không hỗ trợ, không cần code gì thêm.

### 9.4 Công cụ Test/Dry-run (trang "Nâng cao")

Dành cho lúc thêm site mới hoặc site đổi cấu trúc — không đặt ở dashboard
chính, tránh rối cho việc dùng hàng ngày. Sửa 17/9/2026: cả link nav LẪN
route `/dev-tools` chỉ tồn tại ở bản dev (`import.meta.env.DEV`) — trước đó
chỉ ẩn link nav, route vẫn gọi được ở bản production nếu biết/đoán URL
(không phải lỗ hổng nghiêm trọng vì dry-run không đụng DB, nhưng không
khớp ý "tách khỏi dashboard dùng hàng ngày").

| Field | Loại |
|---|---|
| Nguồn | dropdown |
| Loại test | radio: "Danh sách chương" / "Nội dung 1 chương" |
| URL | text input |

- Bấm **Chạy thử** → gọi `POST /dry-run`, kết quả hiện ngay trong panel bên
  dưới, KHÔNG lưu DB:
  - Test danh sách chương → bảng vài dòng đầu (STT, tiêu đề, URL).
  - Test nội dung → đoạn text đầu (vài trăm ký tự) + tổng số ký tự + kết
    quả `validate()` (đạt/không đạt, lý do cụ thể nếu không đạt).
- Selector sai → thông báo cụ thể kiểu: *"Không tìm thấy chương nào với
  selector `#list a` — site có thể đã đổi cấu trúc HTML."* (không phải lỗi
  chung chung "Error").

### 9.5 Danh sách truyện đã crawl (trong trang chi tiết site)

**1 danh sách/SITE, tự phân trang RIÊNG** (sửa 16/9/2026 theo phản hồi thật
"list nào của site nào thì hiển thị site đó" — trước đó là 1 bảng phẳng gộp
MỌI site vào 1 tab "Truyện" chung, không phân trang, càng nhiều truyện càng
khó dùng). Nằm ngay trong trang chi tiết site (mục 9.0) — không phải tab
riêng nữa, luôn chỉ hiện truyện của site đang xem.

- Bảng: Tiêu đề, **Trạng thái** (badge màu theo `lifecycle_status`), Số
  chương (không có cột Nguồn — đã ở đúng trang site rồi, khỏi lặp lại).
- Filter: trạng thái (dropdown, gồm cả `rejected`/`error`), search theo tên
  (lọc phía server qua `?search=`, luôn kèm `?source_key=` của site đang
  xem). Đổi filter → tự quay về trang đầu (tránh kẹt ở 1 trang rỗng).
- Phân trang: 10 truyện/trang, nút **← Trước** / **Sau →**, hiện
  "X-Y / Z truyện". Ẩn nút phân trang nếu site đó ≤ 10 truyện. Chưa có
  truyện nào khớp bộ lọc → gợi ý "Chọn thể loại rồi bấm Quét ngay, hoặc
  thêm truyện bằng URL ở trên".
- Row action theo trạng thái:
  - `error` → nút **Thử lại** (resume crawl từ chương lỗi, không crawl lại từ đầu).
  - `rejected` → nút **Buộc nhận** (bỏ qua kiểm tra ngắn+hoàn thành, chuyển
    sang `discovered` và crawl — tương đương tick checkbox ở mục 9.3 nhưng
    áp dụng cho truyện job tự phát hiện rồi loại).

### 9.6 Chi tiết truyện

- Header: tiêu đề, nguồn, tổng số chương, trạng thái, (nếu `error`) hiện
  rõ `error_message`.
- Bảng chương: STT, tiêu đề, trạng thái (`crawled/failed/translated/...`),
  cờ đã review, nút xem/sửa nội dung (modal/side panel — mục 9.6b), lọc
  theo trạng thái/đã review/search tên chương, phân trang RIÊNG (giống mục
  9.5, không tải hết 1 lần nếu truyện nhiều chương).
- **Nút "Crawl lại"** trên MỖI dòng chương đang `failed`/`unsupported`
  (thêm 17/9/2026, theo đúng yêu cầu thật "bỏ qua chương lỗi, crawl tiếp
  các chap sau, mỗi chap lỗi sẽ có nút crawl lại") — `POST
  /chapters/{id}/retry`: crawl lại ĐÚNG 1 chương đó, KHÔNG đụng chương
  khác, KHÔNG crawl lại cả truyện (khác hẳn "Thử lại" mục 9.2b). Chạy
  ĐỒNG BỘ (1 request mạng, đủ nhanh cho 1 chương). Nếu đây là chương THIẾU
  CUỐI CÙNG của 1 truyện đang kẹt ghi chú "Thiếu N chương" (mục 9.2b) —
  ghi chú đó tự xoá, truyện coi như đủ ngay, không cần bấm "Thử lại" cả
  truyện thêm lần nữa để BE tự nhận ra đã đủ.

### 9.6b Xem/sửa nội dung + "Làm mượt" (rule-based, không tốn tiền AI)

Crawl về mà không đọc/sửa được thì vô dụng (mục 5 — `Chapter.reviewed`).
Mở modal 1 chương → `GET /chapters/{id}/content` hiện nội dung, ưu tiên
**bản đã làm mượt** nếu có (`content_source: "cleaned"`), không thì raw.
Sửa tay → `PUT /chapters/{id}/content` (tự đánh dấu `reviewed=true`); muốn
bỏ bản làm mượt, quay về đúng bản raw gốc → `DELETE /chapters/{id}/cleaned`.

**"Làm mượt"** (`POST /novels/{id}/smooth`, chọn 1/nhiều/tất cả chương) —
dọn RULE-BASED thuần regex (từ dự án `novel-processor`, KHÔNG gọi AI, KHÔNG
tốn chi phí dịch — mục 1): khoảng trắng thừa, dòng quảng cáo/điều hướng
lặp lại, chuẩn hoá ký tự nửa-độ-rộng... Ghi ra file `cleaned/` RIÊNG, không
đè `raw/` gốc — luôn xem/khôi phục lại bản raw thật được (mục 9.6b trên).
Chạy đồng bộ (chờ xong mới trả kết quả), vì đây là xử lý text thuần, không
phải request mạng — không cần chạy nền như crawl.

### 9.7 API endpoints (context `crawl`, tầng `api/`)

**Không liệt kê lại danh sách endpoint ở đây** (từng có 1 bản tóm tắt kiểu
ASCII trong chính mục này — lệch dần với code thật mỗi lần thêm endpoint
mới, đến 17/9/2026 đã thiếu hẳn 1 nửa số endpoint đang chạy thật). Danh
sách ĐẦY ĐỦ + ví dụ request/response thật, LUÔN đúng theo code, chỉ sống ở
1 chỗ duy nhất: [api-reference.md](./api-reference.md) — hoặc Swagger UI
`/docs` khi server đang chạy. 6 nhóm hiện có (17/9/2026): Sites (+ phiên
đăng nhập), Genres (+ tiến độ live + huỷ quét), Novels (+ retry hàng loạt +
làm mượt), Chapters (đọc/sửa/bỏ bản cleaned), Settings, Dry-run.

---
*Service tiếp theo: Translate service (gọi Claude dịch, rút từ hàng đợi theo
cap 20 chương/ngày), rồi TTS service, rồi Merge (ffmpeg) service.*
