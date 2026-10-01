export { cn } from "cn"

/** Tính % (0–100, làm tròn) từ done/total; null khi chưa biết tổng. */
export function percent(done: number | null | undefined, total: number | null | undefined): number | null {
  if (!total || total <= 0 || done == null) return null
  return Math.round((done / total) * 100)
}
