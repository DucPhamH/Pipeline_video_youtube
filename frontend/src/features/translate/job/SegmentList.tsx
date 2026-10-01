import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { Flag, Search } from "lucide-react"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { friendlyError, qaFlagLabel } from "../errorText"
import { useStatusLabels } from "../hooks/useStatusLabels"
import type { Segment } from "../types"
import { SEG_FILTERS, type SegFilter } from "./segmentFilter"

/** Chiều cao cố định mỗi hàng (px, gồm khoảng cách) — để cửa sổ hoá danh sách dài. */
const ROW_H = 72
const ROW_GAP = 6
const OVERSCAN = 6

export function SegmentList({
  segments,
  totalCount,
  activeId,
  onOpen,
  titleFor,
  search,
  onSearch,
  filter,
  onFilter,
  counts,
  qaFlags,
  qaFlag,
  onQaFlag,
}: {
  /** Đã lọc. */
  segments: Segment[]
  totalCount: number
  activeId: number | null
  onOpen: (id: number) => void
  titleFor: (chapterIndex: number) => string
  search: string
  onSearch: (q: string) => void
  filter: SegFilter
  onFilter: (f: SegFilter) => void
  counts: Record<SegFilter, number>
  qaFlags: string[]
  qaFlag: string
  onQaFlag: (f: string) => void
}) {
  const t = useT()
  const { segmentStatusLabel } = useStatusLabels()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewH, setViewH] = useState(600)

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    setViewH(el.clientHeight || 600)
    const ro = new ResizeObserver(() => setViewH(el.clientHeight || 600))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Đổi bộ lọc/tìm kiếm → về đầu danh sách.
  useEffect(() => {
    const el = scrollRef.current
    // onScroll sẽ cập nhật scrollTop.
    if (el) el.scrollTop = 0
  }, [filter, search, qaFlag])

  // Giữ hàng đang mở trong tầm nhìn (điều hướng bằng phím).
  const activeIdx = activeId == null ? -1 : segments.findIndex((s) => s.id === activeId)
  useEffect(() => {
    const el = scrollRef.current
    if (!el || activeIdx < 0) return
    const top = activeIdx * ROW_H
    if (top < el.scrollTop) el.scrollTop = top
    else if (top + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = top + ROW_H - el.clientHeight
  }, [activeIdx])

  const flagAvailable = counts.flagged > 0 || qaFlags.length > 0
  const filters = SEG_FILTERS.filter((f) => f !== "flagged" || flagAvailable)
  const filterLabel: Record<SegFilter, string> = {
    all: t("translate.filterAll"),
    pending: t("translate.filterPending"),
    done: t("translate.filterDone"),
    failed: t("translate.filterFailed"),
    reviewed: t("translate.filterReviewed"),
    flagged: t("translate.filterFlagged"),
  }

  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN)
  const end = Math.min(segments.length, Math.ceil((scrollTop + viewH) / ROW_H) + OVERSCAN)
  const visible = segments.slice(start, end)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="space-y-2.5 border-b border-border p-4">
        <label className="flex h-[38px] items-center gap-2 rounded-[10px] border border-input bg-card px-3 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/40">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={t("translate.job.searchPlaceholder")}
            aria-label={t("translate.job.searchPlaceholder")}
            className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </label>
        <div role="radiogroup" aria-label={t("translate.job.filters")} className="flex flex-wrap gap-1.5">
          {filters.map((f) => {
            const on = filter === f
            return (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => onFilter(f)}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                  on
                    ? "bg-foreground text-background"
                    : "border border-input bg-card text-muted-foreground hover:text-foreground",
                )}
              >
                {filterLabel[f]}
                <span className={cn("font-mono tabular-nums", on ? "opacity-80" : "opacity-70")}>{counts[f]}</span>
              </button>
            )
          })}
        </div>
        {filter === "flagged" && qaFlags.length > 1 ? (
          <select
            aria-label={t("translate.qaFlagFilter")}
            className="h-8 w-full rounded-lg border border-input bg-card px-2 text-xs"
            value={qaFlag}
            onChange={(e) => onQaFlag(e.target.value)}
          >
            <option value="">{t("translate.qaFlagAll")}</option>
            {qaFlags.map((f) => (
              <option key={f} value={f}>
                {qaFlagLabel(f, t)}
              </option>
            ))}
          </select>
        ) : null}
        <p className="font-mono text-[11px] text-muted-foreground tabular-nums">
          {t("translate.job.segmentsCount", { shown: segments.length, total: totalCount })}
        </p>
      </div>

      <div
        ref={scrollRef}
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        className="scrollbar-thin relative min-h-0 flex-1 overflow-y-auto px-3 py-3"
      >
        {totalCount === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-muted-foreground">{t("translate.segmentsEmpty")}</p>
        ) : segments.length === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-muted-foreground">{t("translate.segmentsFilterEmpty")}</p>
        ) : (
          <ul className="relative" style={{ height: segments.length * ROW_H - ROW_GAP }} aria-label={t("translate.segments")}>
            {visible.map((s, i) => {
              const idx = start + i
              const on = s.id === activeId
              const flags = s.qa_flags ?? []
              const doneLike = s.status === "done" || s.status === "skipped_cache"
              return (
                <li
                  key={s.id}
                  className="absolute inset-x-0"
                  style={{ top: idx * ROW_H, height: ROW_H - ROW_GAP }}
                >
                  <button
                    type="button"
                    onClick={() => onOpen(s.id)}
                    aria-current={on ? "true" : undefined}
                    className={cn(
                      "flex h-full w-full flex-col justify-center gap-1 rounded-[10px] border px-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      on
                        ? "border-primary/40 bg-accent"
                        : "border-border bg-card hover:border-input hover:bg-muted/50",
                    )}
                  >
                    <span className="flex w-full min-w-0 items-center gap-2">
                      <span className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                        #{s.chapter_index}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">
                        {titleFor(s.chapter_index)}
                      </span>
                      <StatusPill
                        status={s.status}
                        label={segmentStatusLabel(s.status)}
                        tone={doneLike ? "success" : undefined}
                        className="shrink-0"
                      />
                    </span>
                    {flags.length > 0 ? (
                      <span className="flex min-w-0 items-center gap-1 text-[11px] font-semibold text-danger">
                        <Flag className="size-3 shrink-0" aria-hidden />
                        <span className="truncate">{flags.map((f) => qaFlagLabel(f, t)).join(" · ")}</span>
                      </span>
                    ) : s.status === "failed" && s.error ? (
                      <span className="truncate text-[11px] text-danger">{friendlyError(s.error, t)}</span>
                    ) : s.reviewed ? (
                      <span className="truncate text-[11px] font-medium text-accent-foreground">
                        ✓ {t("translate.reviewed")}
                      </span>
                    ) : s.output_preview ? (
                      <span className="truncate text-[11px] text-muted-foreground">{s.output_preview}</span>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
