import { useEffect, useState } from "react"

/** Debounce giá trị (vd ô tìm kiếm) — tránh refetch storm mỗi phím. */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
