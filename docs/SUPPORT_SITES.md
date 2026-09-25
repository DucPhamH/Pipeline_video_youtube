# Site support tiers (for commercial source packages)

Buyers: number of adapters in `registry.py` ≠ support SLA.
Write the tier into the invoice.

## Tier A — primary (recommend for demos / early support)

Keep this list short and honest; update when a site breaks often.

| Key | Notes |
|---|---|
| `bqgxs_com` | HTML, free, used in internal QA |
| `bgq99_cc` | Classic biquge-style |
| `demo_local` | Offline fixtures — always works for smoke test |

## Tier B — included, best-effort

Other registered CN / JP / KR / VN / TW sources. May need cookies
(Playwright / session). Fix on request only if support contract says so.

VN hosts often geo-block non-VN IPs. Prefer UI:
Settings → **Proxy Việt Nam**, or site → **Cài đặt quét** → Proxy URL
(Clash `http://127.0.0.1:7890`). Env `CRAWL_PROXY_VN` is fallback only.
Applies to `truyenfull_today`, `dtruyen_com`, `sstruyen_net`, `docln_net`
(`truyenfull_vn` / `.live` often works without a VN exit).

## Zhihu 盐选 (`zhihu_com`) — Tier C / experimental

- **Primary flow:** Sites → 知乎盐选 → paste cookie (`z_c0` + `d_c0`) →
  **Thêm truyện bằng URL**
  `https://www.zhihu.com/market/paid_column/<id>`
- Requires a Zhihu account that **already can read** the column (membership / purchase).
- Signing: `x-zse-96` (see `zhihu_sign.py`, MediaCrawler-derived).
- Not in support SLA by default — anti-bot / paywall change often.

## Tier C — experimental mirrors

New biquge mirrors with JS-gated chapter shells are not registered until
chapter HTML/API is verified. Unregistered Python files under `sources/`
(if any) are not advertised.

## Buyer checklist before go-live

1. `docker compose up --build` → open UI  
2. Scan `demo_local` or one Tier A site  
3. Smooth → export ZIP once  
4. Optionally set daily schedule + webhook  
