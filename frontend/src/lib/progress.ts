/** Nhớ chỗ đang đọc / đang nghe trên máy này (localStorage). */

export type ReadRecord = {
  kind: "translate" | "write"
  id: number
  /** Đường dẫn trình đọc, không kèm ?ch. */
  path: string
  title: string
  chapter: number
  chapterTitle: string
  at: number
}

export type ListenRecord = {
  workId: number
  title: string
  segmentId: number
  chapterTitle: string
  time: number
  at: number
}

const READ_KEY = "folio.reading"
const LISTEN_KEY = "folio.listening"
const LIMIT = 8

function load<T>(key: string): T[] {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? "[]")
    return Array.isArray(raw) ? (raw as T[]) : []
  } catch {
    return []
  }
}

function save<T>(key: string, items: T[]) {
  try {
    localStorage.setItem(key, JSON.stringify(items.slice(0, LIMIT)))
  } catch {
    /* hết chỗ hoặc chế độ riêng tư — bỏ qua */
  }
}

export function recentReads(): ReadRecord[] {
  return load<ReadRecord>(READ_KEY).sort((a, b) => b.at - a.at)
}

export function readPosition(kind: ReadRecord["kind"], id: number): ReadRecord | undefined {
  return load<ReadRecord>(READ_KEY).find((r) => r.kind === kind && r.id === id)
}

export function rememberRead(record: Omit<ReadRecord, "at">) {
  const rest = load<ReadRecord>(READ_KEY).filter((r) => !(r.kind === record.kind && r.id === record.id))
  save(READ_KEY, [{ ...record, at: Date.now() }, ...rest])
}

export function recentListens(): ListenRecord[] {
  return load<ListenRecord>(LISTEN_KEY).sort((a, b) => b.at - a.at)
}

export function listenPosition(workId: number): ListenRecord | undefined {
  return load<ListenRecord>(LISTEN_KEY).find((r) => r.workId === workId)
}

export function rememberListen(record: Omit<ListenRecord, "at">) {
  const rest = load<ListenRecord>(LISTEN_KEY).filter((r) => r.workId !== record.workId)
  save(LISTEN_KEY, [{ ...record, at: Date.now() }, ...rest])
}
