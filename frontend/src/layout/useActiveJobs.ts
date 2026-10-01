import { useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { crawlApi } from "@/features/crawl/api"
import { translateApi } from "@/features/translate/api"
import { ApiError } from "@/api/client"
import { ttsApi } from "@/features/tts/api"

export type ActiveJob = {
  key: string
  kind: "translate" | "listen"
  title: string
  status: string
  done: number
  total: number
  to: string
}

export type ActiveJobs = {
  jobs: ActiveJob[]
  translateCount: number
  listenCount: number
}

const ACTIVE = new Set(["queued", "running"])
const POLL_MS = 5000
/** Fallback (tts-service cũ, chưa có /jobs/active): số tác phẩm mới nhất được hỏi chi tiết. */
const TTS_PROBE = 3
/** Đặt false khi tts-service trả 404/405/422 cho /jobs/active → dùng cách suy ra cũ. */
let ttsActiveSupported = true
export const ACTIVE_JOBS_KEY = ["shell", "active-jobs"] as const

/**
 * TTS: GET /api/tts/jobs/active. Trả null nếu service chưa có endpoint
 * (404/405/422 — bản cũ khớp nhầm /jobs/{job_id}) để rơi về cách suy ra cũ.
 */
async function loadListenJobsDirect(): Promise<ActiveJob[] | null> {
  if (!ttsActiveSupported) return null
  try {
    const rows = await ttsApi.activeJobs()
    return rows.map((r) => ({
      key: `tts-${r.job_id}`,
      kind: "listen",
      title: r.work_title,
      status: r.status,
      done: r.done_segments,
      total: r.total_segments,
      to: `/tts/${r.work_id}`,
    }))
  } catch (err) {
    if (err instanceof ApiError && [404, 405, 422].includes(err.status)) {
      ttsActiveSupported = false
      return null
    }
    return []
  }
}

/**
 * Fallback TTS: suy ra từ latest_job của vài tác phẩm mới nhất + tác phẩm mà
 * pipeline crawl đang ở bước "speaking".
 */
async function loadListenJobsDerived(): Promise<ActiveJob[]> {
  const [ttsList, pipelines] = await Promise.allSettled([ttsApi.listWorks(), crawlApi.listPipelines()])
  const probeIds = new Set<number>()
  if (ttsList.status === "fulfilled") {
    for (const w of [...ttsList.value.items].sort((a, b) => b.id - a.id).slice(0, TTS_PROBE)) probeIds.add(w.id)
  }
  if (pipelines.status === "fulfilled") {
    for (const p of pipelines.value.items) {
      if (p.stage === "speaking" && p.tts_work_id) probeIds.add(p.tts_work_id)
    }
  }
  const works = await Promise.allSettled([...probeIds].map((id) => ttsApi.getWork(id)))
  const listenJobs: ActiveJob[] = []
  for (const res of works) {
    if (res.status !== "fulfilled") continue
    const work = res.value
    for (const reading of work.readings) {
      const job = reading.latest_job
      if (!job || !ACTIVE.has(job.status)) continue
      listenJobs.push({
        key: `tts-${job.id}`,
        kind: "listen",
        title: work.title,
        status: job.status,
        done: job.done_segments,
        total: job.total_segments,
        to: `/tts/${work.id}`,
      })
    }
  }
  return listenJobs
}

/**
 * Translate: /inbox trả sẵn danh sách đang chạy (rẻ) → hỏi /jobs/:id lấy tiến độ cho ≤3 job.
 * TTS: /jobs/active (fallback: suy ra, xem loadListenJobsDerived).
 */
async function loadActiveJobs(): Promise<ActiveJobs> {
  const [inbox, listenDirect] = await Promise.allSettled([translateApi.getInbox(), loadListenJobsDirect()])

  const translateRows = inbox.status === "fulfilled" ? inbox.value.running : []
  const translateJobs = await Promise.all(
    translateRows.slice(0, 3).map(async (row): Promise<ActiveJob> => {
      let done = 0
      let total = 0
      let status = row.job_status ?? "running"
      if (row.job_id) {
        try {
          const job = await translateApi.getJob(row.job_id)
          done = job.done_segments
          total = job.total_segments
          status = job.status
        } catch {
          /* giữ số 0 — vẫn hiện là đang chạy */
        }
      }
      return {
        key: `tr-${row.variant_id}`,
        kind: "translate",
        title: row.work_title,
        status,
        done,
        total,
        to: row.job_id ? `/translate/${row.work_id}/jobs/${row.job_id}` : `/translate/${row.work_id}`,
      }
    }),
  )

  const direct = listenDirect.status === "fulfilled" ? listenDirect.value : []
  const listenJobs = direct ?? (await loadListenJobsDerived())

  return {
    jobs: [...translateJobs, ...listenJobs],
    translateCount: translateRows.length,
    listenCount: listenJobs.length,
  }
}

const EMPTY: ActiveJobs = { jobs: [], translateCount: 0, listenCount: 0 }

/**
 * Việc dịch/đọc đang chạy cho sidebar. Poll tự lên lịch: lượt sau chỉ hẹn
 * 5s SAU khi lượt trước xong, dừng hẳn khi tab ẩn, gọi lại ngay khi tab hiện.
 * Chỉ một nơi nên gọi với `poll = true` (AppLayout); nơi khác đọc chung cache.
 */
export function useActiveJobs(poll = false): ActiveJobs {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ACTIVE_JOBS_KEY,
    queryFn: loadActiveJobs,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    staleTime: POLL_MS,
  })

  useEffect(() => {
    if (!poll) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    let inflight = false

    const tick = async () => {
      timer = undefined
      if (stopped || inflight || document.hidden) return
      inflight = true
      try {
        await qc.fetchQuery({ queryKey: ACTIVE_JOBS_KEY, queryFn: loadActiveJobs, staleTime: 0 })
      } catch {
        /* service tắt — thử lại lượt sau */
      } finally {
        inflight = false
      }
      if (!stopped && !document.hidden) timer = setTimeout(tick, POLL_MS)
    }
    const onVisibility = () => {
      if (document.hidden) {
        if (timer) clearTimeout(timer)
        timer = undefined
      } else if (!timer) {
        void tick()
      }
    }

    timer = setTimeout(tick, POLL_MS)
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      document.removeEventListener("visibilitychange", onVisibility)
    }
  }, [poll, qc])

  return data ?? EMPTY
}
