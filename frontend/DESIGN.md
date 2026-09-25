# DESIGN.md — Crawl Studio (Reading room)

Dial: ENERGY 1 / RHYTHM 2 / MOTION 1

Filter: anti-slop. Direction: a **library reading room** — novel-adjacent, still a console.

## Identity

Crawl console for novels that feels like a quiet reading desk: soft stone paper, ink text, one **book-green** accent. Not manga, not SaaS-teal flashlight, not cream+terracotta AI editorial.

## Visual language

| Role | Light | Dark |
|---|---|---|
| Page | Stone sage `#ECEEE9` | Ink night `#121510` |
| Surface | `#FAFBF8` | `#1A1E18` |
| Text | Ink `#1C1F1A` | `#E8EBE4` |
| Muted | `#5E6560` | `#9AA398` |
| Accent | Book green `#2C5F4E` | Soft sage `#8FBC9F` |
| Border | `#D5D9D1` | `#2C332B` |

- **Typography:** Geist Variable (UI). **Source Serif 4** only for page titles / brand — never body or buttons.
- **Radius:** 8–10px.
- **Elevation:** 1px border; tiny shadow ok. No glass, purple gradients, comic ink offsets.
- **Color rule:** green = brand/CTA; amber/red/sky only for status.

## Layout

1. Top header: brand (serif) left, theme + language right.
2. Left sidebar: nav links.
3. Main content full remaining width.
4. Section cards with quiet headers.
5. Mobile: hamburger drawer.

## Forbidden

- Cream `#F4F1EA` + terracotta + serif-everywhere (AI editorial cluster)
- Manga / Bangers / screentone / hard comic shadows
- Purple-on-white, glassmorphism, Inter-as-brand
