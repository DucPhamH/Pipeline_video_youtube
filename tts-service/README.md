# TTS service

Đọc sách thành audio. DB riêng, không mở SQLite của crawl hay translate.

- Độc lập: import TXT / EPUB, chọn giọng, nghe thử, đọc theo chương.
- Pipeline: `POST /api/tts/works/from-translate` nhận chương đã dịch. Nút nằm trên job dịch.
- Engine: `edge` (giọng Microsoft, không cần GPU) và `mock` (test).
- Tiếng Việt trên Edge có hai giọng: Hoài My và Nam Minh. Tốc độ, cao độ, và giọng cho câu trong ngoặc kép là cách tách kiểu đọc. Tiếng Trung / Anh có thêm style khi catalog có.
- Xuất zip mp3 từng chương. M4B (mốc chương, bìa EPUB nếu có) cần `ffmpeg` trên máy. Image Docker đã cài ffmpeg.

```bash
make tts-dev   # http://127.0.0.1:8011/docs
```

## Bảo mật & giới hạn

- `FOLIO_API_TOKEN` (tuỳ chọn, dùng chung với các service khác): đặt thì mọi route trừ `/api/health` cần header `X-Folio-Token: <token>` hoặc `Authorization: Bearer <token>`; riêng GET nhận thêm `?token=` để `<audio src>` và link tải file chạy được. Sai/thiếu → 401. Trống → cho qua hết, log cảnh báo lúc khởi động. Gọi translate-service (gắn câu thoại) gửi kèm header này.
- `TTS_MAX_UPLOAD_MB` (mặc định 50): TXT / EPUB lớn hơn → 413.

## Xuất file

- Mỗi lần đọc chỉ xuất một file một lúc; bấm lần hai khi đang xuất → 409.
- M4B: mỗi chương được transcode về AAC mono 24 kHz 64k và cache ở `audio/cache/aac/` theo cache key của chương, xuất lại không transcode lại.
- Mốc chương = cộng dồn độ dài (ffprobe `format=duration`) của chính các part AAC — đúng con số concat demuxer dùng để nối, không phải mp3 gốc (AAC thêm priming/padding). Làm tròn trên tổng cộng dồn nên sách dài không bị trôi mốc.
- Thư mục tạm `audio/exports/` được dọn lúc khởi động.
