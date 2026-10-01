# DESIGN.md — Folio (Lantern Library)

Direction: **a lit reading desk, not a grey console.** Dark ink sidebar, bright paper workspace, one jade action colour, and one colour per pipeline stage. Every running job is visible, and every page puts its single primary action in the same place.

Tokens live in `src/index.css` (shadcn variable names, exposed as Tailwind colours in `@theme inline`).

## Palette

| Role | Token | Light | Dark |
|---|---|---|---|
| Page ground | `background` | `#F3F5F4` | `#0B110F` |
| Surface | `card` / `popover` | `#FFFFFF` | `#131B18` |
| Text | `foreground` | `#101614` | `#E8EEEB` |
| Muted fill | `muted` / `secondary` | `#EEF2F0` | `#1A2420` |
| Muted text | `muted-foreground` | `#5B6763` | `#93A39D` |
| Border | `border` | `#E3E8E6` | `#24332F` |
| Action (jade) | `primary` (`primary-hover`) | `#0B8F6B` (`#08785A`) | `#2BD4A0` on `#06261C` |
| Soft action | `accent` / `accent-foreground` | `#E3F5EE` / `#076A50` | jade 15% / `#7FF0C9` |
| Danger | `destructive` | `#D92D3F` | `#FF6B7D` |
| Live (saffron) | `live` | `#F5A524` | `#F5A524` |
| Glow (mint) | `glow` | `#2BD4A0` | `#2BD4A0` |
| Sidebar ink | `sidebar` / `sidebar-foreground` | `#0E1513` / `#B7C4BF` | `#080D0B` / `#B7C4BF` |

Primary on white is about 4.1:1, which is fine for buttons (14px semibold) and icons. For small link text, use `text-accent-foreground` (`#076A50`).

### Pipeline stages

| Stage | Route | Token (`bg-stage-*`, `text-stage-*`) | Light / soft | Dark |
|---|---|---|---|---|
| Collect | `/sites`, `/novels` | `stage-collect` | `#3563E9` / `#E8EEFD` | `#7FA2FF` |
| Translate | `/translate` | `stage-translate` | `#0B8F6B` / `#E3F5EE` | `#2BD4A0` |
| Listen | `/tts` | `stage-listen` | `#D9820A` / `#FDF1DE` | `#F5A524` |
| Write | `/write` | `stage-write` | `#D63F5C` / `#FCE8EC` | `#FF7A93` |

In dark mode, the soft variants are a 15% alpha mix of the stage colour.

### Status

`success` / `warning` / `danger` / `info` each have a foreground and a `-soft` fill (for example `bg-warning-soft text-warning`). Status is **always** shown with `<StatusPill status=… />`: it never uses raw colour classes and never uses free-form text badges.

## Type

- **Display / headings:** Fraunces Variable (`font-display`, `font-heading`). Page titles are 30–36px, and section titles on the shelf are 22px.
- **UI / body:** Geist Variable. The base size is **15px** with line-height 1.55. Section titles are Geist 17–20px semibold.
- **Numbers:** Geist Mono (`font-mono`) for progress, counts, IDs and durations.
- **Reader body:** Source Serif 4 (`font-reading`), used only in the reader.

## Motion (CSS only, all disabled under `prefers-reduced-motion`)

- Page enter: fade plus an 8px rise, 220ms, `cubic-bezier(.2,.8,.2,1)`. Applied automatically per route.
- Lists: `.stagger` adds a 30ms step for each of the first 10 children.
- Live progress: `.progress-live` shimmer sweep, plus a pulsing `.dot-live`.
- Covers and cards: `.lift` lifts 4px on hover and deepens the shadow.
- Dialogs: scale .96→1 with a 4px backdrop blur. Toasts match the cards (12px radius, soft status fills).
- Skeletons: `.skeleton-shimmer`.

## Layout rules

1. **Shell:** a 252px dark ink sidebar with brand, Search (Ctrl/⌘ K command palette), Bookshelf, a PIPELINE group (each stage has a colour dot and a running count), a "Running now" widget, then Settings, Advanced, and theme plus language controls. There is no global top header.
2. **Mobile (<1024px):** an ink top bar (logo, search, menu) and a bottom tab bar (Shelf · Collect · Translate · Listen · More). More opens the drawer.
3. **Page header:** every page renders `<PageHeader>`, laid out as breadcrumb, then eyebrow, then a Fraunces title, then meta/description. Put **one primary action at the top right** with secondary actions to its left. Page-level tabs go in the header's `tabs` slot, using `SegmentedTabs variant="underline"`.
4. **Destructive actions** go in an overflow `ActionMenu`, never next to the primary action.
5. **Cards** have a 16px radius, a 1px border and 20px padding. Empty lists use `<EmptyState>` (a tinted icon circle, title, hint, and a CTA).
6. **Progress** always uses `<Progress>`, with its tone taken from the stage and `live` set while running.
7. Book covers come from `<BookCover>`: a curated palette chosen by title hash (jade, cobalt, wine, amber-brown, teal, plum), a spine strip, an orb, and the title in Fraunces.

## Forbidden

- Low-contrast grey-sage on grey, and body text below 13px
- More than one filled primary button per header
- Status shown with ad-hoc colours instead of StatusPill
- Purple gradients, glassmorphism, comic/manga styling
