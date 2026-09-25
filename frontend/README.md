# Crawl Service — Frontend

React + TypeScript + Vite + Tailwind. Gọi thẳng REST API của
`crawl-service` (xem `docs/api-reference.md` ở gốc repo) — chưa có
state-management/data-fetching library nào (react-query...), giữ nhẹ vì
quy mô app còn nhỏ.

## Cấu trúc

```
src/
  api/            client.ts (fetch wrapper) + types.ts (khớp Pydantic schemas)
  features/crawl/ toàn bộ UI cho Crawl service — api.ts, components/, pages/
  layout/         AppLayout (nav)
  App.tsx         route
```

Service mới (Translate/TTS/Video) sau này thêm `features/translate/`,
`features/tts/`... tương tự, không đụng `features/crawl/`.

## Chạy

```bash
cp .env.example .env   # sửa VITE_API_BASE_URL nếu backend chạy port khác
npm install
npm run dev             # http://localhost:5173, cần crawl-service chạy sẵn ở :8090
```

`npm run build` để build production (`dist/`).
