# Folio — Frontend

React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui. Data fetching dùng
TanStack Query. Một SPA gọi ba API: `crawl-service`, `translate-service`, và `tts-service`.

## Màn hình

| Route | Việc |
|---|---|
| `/sites` | Danh sách nguồn + hàng đợi hôm nay |
| `/sites/:sourceKey` | Quét / dán URL / thư viện + cookie phiên |
| `/novels/:id` | Làm mượt, review, xuất file, **Gửi sang dịch** |
| `/settings` | Webhook crawl + proxy |
| `/translate` | Thư viện Work (từ crawl hoặc import TXT) |
| `/translate/:workId` | Variant, glossary, bắt đầu job |
| `/translate/:workId/jobs/:jobId` | Tiến độ, review từng chương, xuất TXT/JSON |
| `/translate/settings` | Registry AI (chung dữ liệu với `/settings`) |
| `/tts` | Thư viện đọc (từ bản dịch hoặc import TXT/EPUB) |
| `/tts/:workId` | Giọng, nghe thử, xuất audio |
| `/dev-tools` | Dry-run parser — chỉ bản `npm run dev` |

i18n: VI / EN / ZH.

## Cấu trúc

```
src/
  api/                 client.ts + types.ts (crawl)
  features/crawl/      UI crawl
  features/translate/  UI dịch (api.ts, types.ts, pages, modal bắt đầu dịch)
  features/tts/        UI đọc
  layout/              nav: Site, Dịch, Đọc, Cài đặt
  i18n/
  App.tsx
```

## Chạy

Cần crawl-service ở `:8090`, translate-service ở `:8010`, và tts-service ở `:8011`.

```bash
cp .env.example .env
npm install
npm run dev             # http://localhost:5173
```

`.env.example` đặt `VITE_API_BASE_URL`, `VITE_TRANSLATE_API_BASE_URL`, và `VITE_TTS_API_BASE_URL`.
Build Docker để trống các biến đó: nginx trong image proxy cùng origin
(`/api/` → crawl, `/api/translate/` → translate, `/api/tts/` → tts).

`npm run build` ra `dist/`. `npm run lint` chạy oxlint.
