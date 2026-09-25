# Platform & khả năng bán tool — quy ước chung (áp dụng mọi service)

> Đây là tài liệu tầng "platform" (shared kernel) — Crawl/Translate/TTS/Video
> đều phải theo quy ước ở đây. Không lặp lại nội dung nghiệp vụ từng service.

## 1. Mô hình bán đã chốt: self-host, mỗi khách 1 bản deploy riêng

- **Không multi-tenant trong DB** — mỗi khách chạy 1 instance độc lập
  (Docker, trên VPS/máy của chính họ). Giữ nguyên được thiết kế đơn giản
  hiện tại (SQLite, không auth phức tạp).
- **Khách dùng API key riêng của họ** (Anthropic để dịch) — người bán không
  gánh chi phí vận hành của khách, chỉ bán 1 lần (hoặc theo version/support).
- **License**: file license ký số, kiểm tra **offline lúc khởi động app**
  (không cần server riêng để xác thực — giữ đúng tinh thần "free", người bán
  không tốn chi phí vận hành hạ tầng license). License hết hạn/không hợp lệ
  → app chỉ cảnh báo + khoá tính năng mới (vd không cho thêm truyện mới),
  **không tự ý xoá dữ liệu khách đã có** (tránh rủi ro pháp lý + trải nghiệm tệ).
- **Cấu hình nguồn (site/thể loại)** nằm trong **1 file config duy nhất**
  (`sources.config.py` hoặc tương đương), viết rõ ràng dễ đọc — để khách kỹ
  thuật (hoặc gói mở rộng có hỗ trợ) có thể tự thêm site khác mà không phải
  đọc cả codebase.

## 2. ⚠️ Rủi ro pháp lý cần biết trước khi bán — nói thẳng

Core nghiệp vụ của tool là: crawl truyện có bản quyền → dịch → phát hành lại
qua kênh YouTube. Vài điểm cần cân nhắc:

- Dùng **cá nhân, tự làm kênh của mình** là 1 việc; **bán 1 tool để người
  khác làm việc này ở quy mô lớn hơn** làm tăng rủi ro (bản quyền nội dung
  gốc, ToS của site nguồn, thậm chí chính sách bản quyền của YouTube nếu
  bị chủ sở hữu gốc khiếu nại — DMCA/Content ID).
- Nhiều repo crawl truyện tương tự trên GitHub tự ghi rõ giới hạn trách
  nhiệm, ví dụ repo `jjwxcNovelCrawler` đã tìm lúc nghiên cứu ghi thẳng:
  *"chỉ dùng học tập, nghiêm cấm mục đích thương mại, xoá trong 24h"* — đây
  là thông lệ chung của giới làm tool loại này, không phải hù doạ.
- Đề xuất cụ thể (không chặn việc bán, chỉ để làm đúng cách):
  1. Ghi rõ trong tài liệu bán / điều khoản sử dụng: **người mua tự chịu
     trách nhiệm pháp lý** khi dùng tool để crawl/phát hành nội dung.
  2. Không quảng cáo tool bằng tên site nguồn cụ thể (biquge.pro...) một
     cách công khai thương mại — để trong tài liệu kỹ thuật nội bộ là đủ.
  3. Nếu định bán nghiêm túc, lâu dài, số lượng lớn → nên hỏi qua 1 luật sư
     SHTT ở Việt Nam về giới hạn được phép, đặc biệt phần "phát hành lại
     nội dung dịch" trên nền tảng công khai (YouTube).

## 3. Quy ước DB chung (áp dụng mọi bounded context)

- **Settings dùng key-value table**, KHÔNG dùng bảng cột cứng:
  ```
  Settings: key (TEXT, PK), value (JSON), updated_at
  ```
  Lý do: thêm cấu hình mới (context nào cũng có thể cần) không phải
  migrate schema mỗi lần — chỉ cần `INSERT`/`UPDATE` 1 dòng key mới. Áp
  dụng thay cho bảng `Settings` cột cứng đã viết tạm trong `crawl-service.md`
  (đã cập nhật lại — xem mục 4 dưới).
- Mọi bảng nghiệp vụ có cả `created_at` **và** `updated_at` (không chỉ
  `created_at` như bản nháp đầu).
- Index bắt buộc trên cột dùng để filter/join thường xuyên — ví dụ bên
  Crawl: `Novel.lifecycle_status`, `Novel.genre_id`, `Chapter.novel_id`,
  `Chapter.status`. Mỗi service tự liệt kê index của mình trong doc riêng.
- **DB mặc định: SQLite** (free, zero-setup, đủ cho self-host 1 khách, 1
  người dùng). Vì dùng SQLAlchemy nên đổi sang Postgres chỉ cần đổi
  connection string — không đổi code — dành cho khách cần mạnh hơn
  (backup dễ, nhiều tiến trình ghi cùng lúc). Đây cũng là 1 điểm bán thêm
  ("hỗ trợ nâng cấp DB khi cần").
- ID dùng **int autoincrement** — đơn giản, đủ dùng vì mỗi bản deploy độc
  lập, không cần UUID (không có nhu cầu đồng bộ giữa các instance của các
  khách khác nhau).

## 4. Chi phí — ưu tiên free, áp dụng toàn bộ pipeline

| Thành phần | Lựa chọn | Chi phí |
|---|---|---|
| DB | SQLite | Free |
| TTS | Edge-TTS | Free |
| Ghép video | ffmpeg | Free |
| Hosting | Self-host (khách tự trả VPS) | Free với người bán |
| License check | File ký số offline | Free (không cần server) |
| Dịch | Claude API (khách tự trả bằng key riêng) | **Duy nhất khoản bắt buộc trả phí**, nhưng người mua trả, không phải người bán |

Translate đã code và cắm nhiều provider OpenAI-compatible (kể cả model
local), khách tự trả key. Xem `translate-service.md`.

## 5. Đóng gói để bán

- `docker-compose.yml` chạy 1 lệnh (`docker compose up`), kèm `.env.example`
  đầy đủ biến cần điền (API key, license key...).
- README hướng dẫn: cần key gì, VPS tối thiểu cấu hình gì, cách thêm 1 site
  nguồn mới (trỏ đúng vào file config mục 1).
- Có thể bán theo 2 gói: **Gói cơ bản** (đúng site/thể loại đã build sẵn,
  không hỗ trợ thêm site mới) và **Gói mở rộng** (kèm hỗ trợ thêm
  site/thể loại theo yêu cầu khách) — không ảnh hưởng kiến trúc, chỉ là
  chính sách bán.

## 6. Việc cần chỉnh lại ở các doc đã viết

- `crawl-service.md` mục "Settings" → đổi từ bảng cột cứng sang key-value
  theo mục 3 ở đây (đã chỉnh, xem doc đó).
- `crawl-service.md` mục "Cấu hình nguồn/thể loại" → nói rõ đây là ví dụ
  cụ thể cho **gói cơ bản**; khi bán, đây là phần đổi theo từng khách/thị
  trường (mục 1 ở đây).
