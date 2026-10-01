/** Poll tự lên lịch cho trang Job: getJob + listSegments khi job đang chạy. */
import { useEffect, useState, type RefObject } from "react"
import { translateApi } from "../api"
import type { Job, Segment } from "../types"

const POLL_MS = 1200
const POLL_HIDDEN_MS = 5000
const POLL_MAX_BACKOFF_MS = 15000

/**
 * Poll tự lên lịch (setTimeout) theo job id + cờ active: không dựng lại interval
 * mỗi tick, không chồng request; chậm lại khi tab ẩn; backoff khi lỗi liên tiếp.
 * `seqRef` tăng mỗi khi job được set từ action — response poll cũ hơn bị bỏ.
 * Trả về số lần lỗi liên tiếp (để hiện banner "mất kết nối").
 */
export function useJobPoll({
  jobId,
  active,
  seqRef,
  onData,
}: {
  jobId: number | undefined
  active: boolean
  seqRef: RefObject<number>
  onData: (job: Job, segments: Segment[]) => void
}): number {
  const [pollFailures, setPollFailures] = useState(0)

  useEffect(() => {
    if (jobId == null || !active) return
    let cancelled = false
    let inFlight = false
    let failures = 0
    let timer: number | undefined

    const schedule = (ms: number) => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => void tick(), ms)
    }
    const nextDelay = () => {
      const base = document.hidden ? POLL_HIDDEN_MS : POLL_MS
      return failures > 0 ? Math.min(base * 2 ** Math.min(failures, 4), POLL_MAX_BACKOFF_MS) : base
    }
    const tick = async () => {
      if (cancelled || inFlight) return
      inFlight = true
      const seq = seqRef.current
      try {
        const [j, segs] = await Promise.all([translateApi.getJob(jobId), translateApi.listSegments(jobId)])
        if (cancelled) return
        failures = 0
        setPollFailures(0)
        // Có action (pause/resume/…) set job trong lúc chờ → response này đã cũ.
        if (seq === seqRef.current) onData(j, segs)
      } catch {
        if (cancelled) return
        failures += 1
        setPollFailures(failures)
      } finally {
        inFlight = false
      }
      if (!cancelled) schedule(nextDelay())
    }
    const onVisible = () => {
      if (!document.hidden && !inFlight) schedule(0)
    }

    schedule(POLL_MS)
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      document.removeEventListener("visibilitychange", onVisible)
      setPollFailures(0)
    }
    // onData phải ổn định (useCallback) — không đưa vào deps để tránh dựng lại poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, active])

  return pollFailures
}
