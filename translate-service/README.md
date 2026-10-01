# Translate Service

Dịch và biến thể nội dung. DB riêng, không mở SQLite của crawl. Nhận chương
đã làm sạch qua `POST /api/translate/works/from-crawl`, hoặc import TXT.
Mặc định `lang_tgt=vi`.

Provider là OpenAI-compatible (OpenAI, Claude, Gemini, DeepSeek, Groq,
Ollama/LM Studio, …) hoặc mock. User lưu nhiều kết nối trong registry
`/api/translate/ai-providers`, kể cả nhiều API key trên một AI. Model chọn
lúc tạo job, không ghi đè model mặc định trong Settings.

Mode trên một Work: `full`, `pov`, `audio_cut`, `style_clone`. Ba mode sau
dịch từ bản `full` đã xong, không dịch lại từ nguồn. `audio_cut` chạy hai
lượt (giữ beat, rồi rút).

Import EPUB, xuất EPUB bản dịch, và EPUB song ngữ (nguồn cạnh bản dịch). Lượt sửa câu (`polish`) tắt mặc định. Đọc audio nằm ở `tts-service`. Chưa ghép video.

## Chạy local

```bash
cd translate-service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=src .venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8010
```

Từ gốc repo: `make translate-dev` (cần `.venv` đã tạo như trên).

API prefix: `/api/translate` — docs: http://localhost:8010/docs

Docker Compose ở gốc repo map cổng host `8010`. UI production đi qua nginx
`/api/translate/`, không gọi thẳng cổng này.

**Chỉ chạy 1 worker/process** (uvicorn mặc định, không `--workers N`, không
gunicorn nhiều worker). Thread dịch, "generation" chống 2 run cùng 1 job sau
Cancel→Resume, và giãn cách gọi AI đều nằm trong bộ nhớ process — nhiều worker
sẽ chạy trùng job và vượt rate-limit.

## Bảo mật

- `FOLIO_API_TOKEN` (tùy chọn): khi đặt, mọi route trừ `/api/health` và
  `/api/translate/health` cần header `X-Folio-Token: <token>` hoặc
  `Authorization: Bearer <token>`; GET (vd tải export) nhận thêm `?token=`.
  Sai/thiếu → 401. Callback sang crawl-service gửi kèm `X-Folio-Token`. Để trống
  → không kiểm tra, log cảnh báo lúc khởi động (chỉ dùng trong mạng tin cậy).
- `TRANSLATE_MAX_UPLOAD_MB` (mặc định 50): giới hạn file EPUB / văn bản TXT
  import (413 nếu vượt). `TRANSLATE_MAX_EPUB_UNCOMPRESSED_MB` (mặc định 500):
  chặn EPUB giải nén quá lớn (zip bomb).
- Đổi `base_url` của AI đã lưu sang host khác phải gửi kèm `api_key`/`api_keys`
  mới trong cùng request (422 nếu không) — tránh gửi key cũ tới server lạ.
- `segment.error` lưu dạng `[code] thông điệp` đã che key, bỏ query string, cắt
  ngắn. `code`: `rate_limited`, `auth`, `too_large`, `truncated`, `network`,
  `refusal`, `worker_crashed`, `provider_error`.

## QA output

Sau mỗi segment chạy kiểm tra luật rẻ, lưu ở `qa_flags` (segment) và
`flagged_segments` (job): `untranslated` (còn nhiều chữ CJK), `length_ratio`,
`repetition`, `polish_failed` — segment vẫn DONE. `refusal` (model từ chối) →
segment FAILED, không cache. `POST /api/translate/jobs/{id}/retranslate-flagged?flag=X`
đưa segment có cờ X (bỏ trống = mọi cờ) về pending và chạy tiếp.

## Test

```bash
cd translate-service
PYTHONPATH=src .venv/bin/pytest -q --tb=short
```

## Luồng

**Từ crawl.** Trên novel, **Gửi sang dịch** gọi handoff với `start_job: false`.
UI mở Work và modal chọn AI + mode. Job xong thì callback
`translating` / `ready_for_video` / `failed` về crawl.

**Import TXT.**

1. `POST /api/translate/works/import-txt` — `{title, lang_src, text}`
2. Tạo job trên variant `full` (UI, hoặc `POST /api/translate/variants/{id}/jobs`)
3. Poll `GET /api/translate/jobs/{id}` tới `completed`
4. `GET /api/translate/variants/{id}/export.txt` hoặc `export.json`

Spec chức năng: [`docs/translate-service.md`](../docs/translate-service.md).
