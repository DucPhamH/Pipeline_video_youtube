import { useQuery } from "@tanstack/react-query"
import { crawlApi } from "@/features/crawl/api"
import { translateApi } from "@/features/translate/api"
import type { InboxItem } from "@/features/translate/types"
import { writeApi } from "@/features/write/api"

export type Running = {
  key: string
  label: string
  kind: "translate" | "crawl" | "write" | "smooth" | "speak"
  to: string
}

async function loadRunning(): Promise<Running[]> {
  const [inbox, crawling, written, pipelines] = await Promise.allSettled([
    translateApi.getInbox(),
    crawlApi.listNovels({ status: "crawling", limit: 5 }),
    writeApi.list(),
    crawlApi.listPipelines(),
  ])
  const rows: Running[] = []
  if (inbox.status === "fulfilled") {
    for (const item of inbox.value.running as InboxItem[]) {
      rows.push({
        key: `tr-${item.variant_id}`,
        label: item.work_title,
        kind: "translate",
        to: item.job_id ? `/translate/${item.work_id}/jobs/${item.job_id}` : `/translate/${item.work_id}`,
      })
    }
  }
  if (crawling.status === "fulfilled") {
    for (const n of crawling.value.items) {
      rows.push({ key: `cr-${n.id}`, label: n.title, kind: "crawl", to: `/novels/${n.id}` })
    }
  }
  if (written.status === "fulfilled") {
    for (const s of written.value.items.filter((s) => s.status === "writing" || s.status === "stopping")) {
      rows.push({ key: `wr-${s.id}`, label: s.title, kind: "write", to: `/write/${s.id}` })
    }
  }
  if (pipelines.status === "fulfilled") {
    for (const p of pipelines.value.items) {
      if (p.stage === "smoothing") {
        rows.push({ key: `sm-${p.novel_id}`, label: p.title, kind: "smooth", to: `/novels/${p.novel_id}` })
      }
      if (p.stage === "speaking") {
        rows.push({ key: `sp-${p.novel_id}`, label: p.title, kind: "speak", to: `/novels/${p.novel_id}` })
      }
    }
  }
  return rows
}

/** Việc đang chạy ở mọi service. Dùng chung một query nên header và trang chủ không gọi trùng. */
export function useRunning(): Running[] {
  const { data } = useQuery({ queryKey: ["running"], queryFn: loadRunning, refetchInterval: 5000 })
  return data ?? []
}
