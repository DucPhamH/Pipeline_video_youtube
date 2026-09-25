# Kiến trúc Microservices — cách các service sau này ghép với nhau

> Trả lời câu hỏi: "làm sao để thành microservices". Tài liệu này áp dụng
> cho toàn bộ hệ thống (Crawl/Translate/TTS/Video), không riêng 1 service.

## 1. Nguyên tắc cốt lõi

Mỗi service = **1 thư mục ở gốc repo, tự build/deploy/chạy độc lập**,
KHÔNG nằm chung trong 1 app Python (khác bản nháp kiến trúc cũ trong
`crawl-service.md` từng vẽ `backend/src/{crawl,translate,tts,video}` — đã
lỗi thời, sửa lại theo tài liệu này).

```
Crawl/                          (repo gốc, monorepo chứa nhiều service)
├── docker-compose.yml           chạy TẤT CẢ service cùng lúc (dev local)
├── docs/
├── crawl-service/                ĐÃ CODE — **đọc nhanh:** [crawl-overview.md](./crawl-overview.md)
│   ├── Dockerfile                  chi tiết: crawl-service.md · project-structure.md
│   ├── requirements.txt
│   ├── .env
│   └── src/{platform_, crawl}/...
├── translate-service/            (chưa code) — **thiết kế chức năng:**
│   └── …                         [docs/translate-service.md](./translate-service.md)
├── tts-service/                  (chưa code)
├── video-service/                (chưa code)
└── frontend/                     (chưa code) React, gọi API các service trên
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

Muốn biết truyện nào đã crawl xong, Translate service gọi **API thật** của
Crawl service:

```
GET http://crawl-service:8000/api/crawl/novels?status=fully_crawled
```

(`crawl-service` ở đây là tên service trong `docker-compose.yml`, Docker tự
phân giải thành IP nội bộ — không phải `localhost`.)

Translate service lưu kết quả dịch vào **DB CỦA RIÊNG NÓ** (bảng
`translated_chapters` chẳng hạn), chỉ giữ lại `chapter_id` (giá trị số, lấy
từ response API của Crawl) để tham chiếu — KHÔNG tạo foreign key thật giữa
2 DB khác nhau (không thể, và cũng không nên, vì đó là khác database).

## 3. Cách các service gọi nhau — polling qua HTTP, không cần message queue

Vì quy mô hiện tại (self-host, 1 người dùng), **không cần** Kafka/RabbitMQ —
thêm vào chỉ tốn hạ tầng, đi ngược tinh thần "càng free càng tốt". Thay vào
đó, mỗi service tự có `scheduler.py` riêng (đã có ở Crawl, dùng
APScheduler), lịch trình định kỳ **tự đi hỏi** service phía trước:

```
Crawl service:      tự crawl web (đã code) — không phụ thuộc service nào khác
Translate service:  APScheduler mỗi X phút -> gọi API Crawl (mục 2) lấy
                     danh sách chương "fully_crawled" chưa dịch -> dịch ->
                     lưu vào DB riêng -> (tương lai) gọi ngược 1 API của
                     Crawl để đánh dấu đã dịch xong, hoặc tự theo dõi bằng
                     bảng riêng của mình.
TTS service:         tương tự, hỏi Translate service.
Video service:       tương tự, hỏi TTS service.
```

Đây chính là mô hình **pipeline kéo (pull-based)** — mỗi service tự chủ
động lấy việc, không ai đẩy việc cho ai. Đơn giản, không cần hạ tầng thêm,
dễ debug (gọi thử bằng `curl`/Swagger UI là thấy ngay dữ liệu thật).

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

Xem file `docker-compose.yml` ở gốc repo — mỗi service 1 block, ví dụ thêm
Translate service (khi code xong) chỉ cần:

```yaml
translate-service:
  build: ./translate-service
  ports: ["8001:8000"]
  env_file: ["./translate-service/.env"]
  environment:
    CRAWL_SERVICE_URL: http://crawl-service:8000
  depends_on: [crawl-service]
```

Không đụng vào block `crawl-service` đã có.

## 6. Việc CHƯA làm (thành thật, tránh ảo tưởng đã xong)

- Chưa có `tts-service`/`video-service`.
- `translate-service/` **đã code Phase 0–2** (import TXT, mock/OpenAI, glossary/review/budget, from-crawl, callback lifecycle, FE `/translate`).
- Crawl đã có `GET .../translate-handoff`, `POST .../send-to-translate`, `POST .../translate-lifecycle`.
- Translate callback lifecycle `translating` / `ready_for_video` / `failed` khi job chạy xong.
