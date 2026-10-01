import type { Segment } from "../types"

export type SegFilter = "all" | "pending" | "done" | "failed" | "reviewed" | "flagged"

export const SEG_FILTERS: SegFilter[] = ["all", "pending", "done", "failed", "reviewed", "flagged"]

export function segmentMatches(s: Segment, filter: SegFilter, qaFlag = ""): boolean {
  switch (filter) {
    case "pending":
      return s.status === "pending" || s.status === "queued"
    case "done":
      return s.status === "done" || s.status === "skipped_cache"
    case "failed":
      return s.status === "failed"
    case "reviewed":
      return s.reviewed
    case "flagged": {
      const flags = s.qa_flags ?? []
      return flags.length > 0 && (!qaFlag || flags.includes(qaFlag))
    }
    default:
      return true
  }
}

/** Đếm số segment cho mỗi bộ lọc trong một lượt duyệt. */
export function countByFilter(segments: Segment[]): Record<SegFilter, number> {
  const out: Record<SegFilter, number> = { all: 0, pending: 0, done: 0, failed: 0, reviewed: 0, flagged: 0 }
  for (const s of segments) {
    for (const f of SEG_FILTERS) if (segmentMatches(s, f)) out[f] += 1
  }
  return out
}
