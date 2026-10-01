import { useNavigate } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { useT } from "@/i18n"
import { useRunning } from "./useRunning"

const KIND_LABEL = {
  translate: "home.runTranslate",
  crawl: "home.runCrawl",
  write: "home.runWrite",
  smooth: "home.runSmooth",
  speak: "home.runSpeak",
} as const

export function ActivityTray() {
  const t = useT()
  const navigate = useNavigate()
  const running = useRunning()
  if (running.length === 0) return null
  return (
    <ActionMenu
      variant="ghost"
      showChevron={false}
      label={
        <span className="flex items-center gap-1.5" title={t("home.running")}>
          <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
          <span className="tabular-nums">{running.length}</span>
          <span className="sr-only">{t("home.running")}</span>
        </span>
      }
    >
      <p className="px-2.5 pt-1 pb-1.5 text-xs font-medium text-muted-foreground">{t("home.running")}</p>
      {running.map((r) => (
        <ActionMenuItem key={r.key} onSelect={() => navigate(r.to)}>
          <span className="flex w-64 max-w-[70vw] items-center justify-between gap-3">
            <span className="min-w-0 truncate">{r.label}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{t(KIND_LABEL[r.kind])}</span>
          </span>
        </ActionMenuItem>
      ))}
    </ActionMenu>
  )
}
