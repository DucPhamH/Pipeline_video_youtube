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

Chưa có: import EPUB, TTS, ghép video.

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
