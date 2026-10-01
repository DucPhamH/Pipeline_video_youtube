/** 75 → "1:15", 3725 → "1:02:05". */
export function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00"
  const s = Math.floor(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = String(s % 60).padStart(2, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`
}
