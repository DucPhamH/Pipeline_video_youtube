export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral"

const STATUS_TONE: Record<string, StatusTone> = {
  queued: "info",
  pending: "info",
  waiting: "info",
  running: "warning",
  crawling: "warning",
  writing: "warning",
  translating: "warning",
  speaking: "warning",
  smoothing: "warning",
  stopping: "warning",
  paused: "neutral",
  skipped: "neutral",
  cancelled: "neutral",
  canceled: "neutral",
  idle: "neutral",
  completed: "success",
  done: "success",
  crawled: "success",
  ready: "success",
  succeeded: "success",
  failed: "danger",
  error: "danger",
  needs_review: "danger",
}

const LIVE = new Set(["running", "crawling", "writing", "translating", "speaking", "smoothing"])

/** Tone cho một trạng thái job bất kỳ (không phân biệt hoa thường). */
export function statusTone(status: string | null | undefined): StatusTone {
  return STATUS_TONE[(status ?? "").toLowerCase()] ?? "neutral"
}

export function isLiveStatus(status: string | null | undefined): boolean {
  return LIVE.has((status ?? "").toLowerCase())
}
