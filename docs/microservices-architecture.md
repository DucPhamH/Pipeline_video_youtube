# Kiến trúc Microservices — cách các service sau này ghép với nhau

> Sản phẩm tên **Folio**. Repo vẫn nằm trong thư mục `Crawl/`.
> Trả lời câu hỏi: "làm sao để thành microservices". Tài liệu này áp dụng
> cho toàn bộ hệ thống (crawl / translate / TTS / video), không riêng 1 service.

## 1. Nguyên tắc cốt lõi

Mỗi service = **1 thư mục ở gốc repo, tự build/deploy/chạy độc lập**,
KHÔNG nằm chung trong 1 app Python (khác bản nháp kiến trúc cũ trong
`crawl-service.md` từng vẽ `backend/src/{crawl,translate,tts,video}` — đã
lỗi thời, sửa lại theo tài liệu này).

```
Crawl/                          (repo gốc, monorepo chứa nhiều service)
├── docker-compose.yml           crawl + translate + frontend
├── docs/
├── crawl-service/                ĐÃ CODE — [crawl-overview.md](./crawl-overview.md)
├── translate-service/            ĐÃ CODE — [translate-service.md](./translate-service.md)
├── frontend/                     ĐÃ CODE — Sites, novel, /translate
├── tts-service/                  ĐÃ CODE — import TXT/EPUB, giọng Edge, mp3/m4b
├── write-service/                ĐÃ CODE — truyện mới, gọi ai-service
├── ai-service/                   ĐÃ CODE — nhà AI và chat, các service khác gọi vào
└── video-service/                chưa có
```

**Mỗi service tự có 1 bản `platform_/` riêng** (config, db, settings_store,
scheduler) — KHÔNG dùng chung code với service khác. Đây là đánh đổi có chủ
đích của microservices thật: chấp nhận trùng lặp 1 ít boilerplate (vài trăm
dòng code hạ tầng) để đổi lấy việc mỗi service triển khai/nâng cấp/sập độc
lập, không phụ thuộc nhau về mặt code.

## 2. Nguyên tắc "mỗi service sở hữu DB riêng"

**Không service nào được đọc thẳng vào DB của service khác.** Vd
`translate-service` KHÔNG được mở file `crawl-service/data/db.sqlite3` để
đọc — vì vậy sau này đổi schema/đổi DB engine của Crawl sẽ không làm gãy
Translate.

Crawl giao chương bằng HTTP (`POST /works/from-crawl`), không bằng cách
đọc file DB. Trong Compose, hostname là `crawl-service` / `translate-service`
(DNS nội bộ), không phải `localhost`.

Translate lưu Work, Variant, Job, Segment trong DB của nó. Tham chiếu crawl
là `external_id` dạng `crawl:novel:{id}` — không có foreign key xuyên DB.

## 3. Cách các service gọi nhau — HTTP khi user bấm, không message queue

Quy mô self-host, một người dùng: không Kafka/RabbitMQ.

Crawl tự quét web và không phụ thuộc service khác. Lịch daily
(APScheduler) chỉ thuộc crawl.

Translate **không** tự poll danh sách truyện. User bấm **Gửi sang dịch**
trên novel: crawl gọi `POST /api/translate/works/from-crawl` (mặc định
không start job). Translate lưu Work trong DB của nó. Job chạy xong thì
gọi ngược `POST /api/crawl/novels/{id}/translate-lifecycle`
(`translating` / `ready_for_video` / `failed`).

TTS nhận chương đã dịch bằng `POST /api/tts/works/from-translate` (frontend
gọi khi user bấm trên job dịch). TTS không mở DB của translate. Video chưa có.

## 4. Vì sao Crawl service ĐÃ SẴN SÀNG cho microservices mà không cần sửa

Kiến trúc DDD chọn từ đầu (`domain/application/infrastructure/api`) hoá ra
khớp thẳng với ranh giới microservice:

- Tầng `api/` (routers.py + schemas.py) **đã là hợp đồng HTTP** — chính là
  thứ service khác sẽ gọi vào, không cần viết thêm gì.
- Tầng `domain/` + `application/` không hề biết tới FastAPI hay SQLAlchemy
  cụ thể — nên dù chạy độc lập (như hiện tại) hay bị gọi từ xa bởi service
  khác, code nghiệp vụ không đổi.

⇒ Crawl service hiện tại **đã là 1 microservice hoàn chỉnh** (dù đang chạy
1 mình) — không cần "chuyển đổi" gì khi thêm Translate/TTS/Video, chỉ cần
tạo thư mục mới cùng khuôn và để chúng gọi API của nhau.

## 5. `docker-compose.yml` — chạy nhiều service cùng lúc

Compose chạy crawl (`8090`), translate (`8010`), TTS (`8011`), write (`8012`),
ai (`8013`) và frontend (nginx, `5173`). Nhà AI nằm ở `ai-service`. Dịch, viết
và đọc gọi vào đó. Thêm video sau này là thêm một block, không sửa DB của
service đã có.

## 6. Việc chưa làm

- Chưa có `video-service`. TTS đã có service riêng.
- Translate chưa import EPUB (P5 trong spec). Polish/QA opt-in chưa làm.
- Đã có: handoff crawl, callback lifecycle, registry nhiều AI, pool/fallback,
  glossary, review, export TXT/JSON, UI `/translate`.
