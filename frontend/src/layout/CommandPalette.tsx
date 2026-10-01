import { useEffect, useMemo, useRef, useState, type ComponentType, type KeyboardEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import { BookOpen, CornerDownLeft, Globe2, Headphones, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { useT } from "@/i18n"
import { translateApi } from "@/features/translate/api"
import { ttsApi } from "@/features/tts/api"
import { crawlApi } from "@/features/crawl/api"

export type PaletteNavItem = {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
}

type Entry = {
  id: string
  group: string
  label: string
  hint?: string
  to: string
  icon: ComponentType<{ className?: string }>
  dot?: string
}

function normalize(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase()
}

const MAX_PER_GROUP = 8

/** Bảng lệnh Ctrl/⌘ K: lọc trang + tác phẩm dịch + tác phẩm đọc + site. Dữ liệu chỉ tải khi mở. */
export function CommandPalette({
  open,
  onOpenChange,
  navItems,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  navItems: PaletteNavItem[]
}) {
  const t = useT()
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLDivElement | null>(null)

  const translateWorks = useQuery({
    queryKey: ["palette", "translate-works"],
    queryFn: () => translateApi.listWorks(),
    enabled: open,
    staleTime: 60_000,
  })
  const ttsWorks = useQuery({
    queryKey: ["palette", "tts-works"],
    queryFn: () => ttsApi.listWorks(),
    enabled: open,
    staleTime: 60_000,
  })
  const sites = useQuery({
    queryKey: ["palette", "sites"],
    queryFn: () => crawlApi.listSites({ limit: 100 }),
    enabled: open,
    staleTime: 5 * 60_000,
  })

  const entries = useMemo<Entry[]>(() => {
    const pages: Entry[] = navItems.map((n) => ({
      id: `nav-${n.to}`,
      group: t("shell.groupPages"),
      label: n.label,
      to: n.to,
      icon: n.icon,
    }))
    const tr: Entry[] = (translateWorks.data?.items ?? []).map((w) => ({
      id: `tr-${w.id}`,
      group: t("shell.groupTranslate"),
      label: w.title,
      hint: `${w.lang_src} → ${w.lang_tgt}`,
      to: `/translate/${w.id}`,
      icon: BookOpen,
      dot: "bg-stage-translate",
    }))
    const tts: Entry[] = (ttsWorks.data?.items ?? []).map((w) => ({
      id: `tts-${w.id}`,
      group: t("shell.groupListen"),
      label: w.title,
      hint: w.lang,
      to: `/tts/${w.id}`,
      icon: Headphones,
      dot: "bg-stage-listen",
    }))
    const st: Entry[] = (sites.data?.items ?? []).map((s) => ({
      id: `site-${s.key}`,
      group: t("shell.groupSites"),
      label: s.name,
      hint: s.key,
      to: `/sites/${encodeURIComponent(s.key)}`,
      icon: Globe2,
      dot: "bg-stage-collect",
    }))
    const q = normalize(query.trim())
    const match = (e: Entry) => !q || normalize(`${e.label} ${e.hint ?? ""}`).includes(q)
    return [
      ...pages.filter(match),
      ...tr.filter(match).slice(0, MAX_PER_GROUP),
      ...tts.filter(match).slice(0, MAX_PER_GROUP),
      ...st.filter(match).slice(0, MAX_PER_GROUP),
    ]
  }, [navItems, translateWorks.data, ttsWorks.data, sites.data, query, t])

  const loading = translateWorks.isLoading || ttsWorks.isLoading || sites.isLoading

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" })
  }, [active])

  const setOpen = (next: boolean) => {
    if (!next) {
      setQuery("")
      setActive(0)
    }
    onOpenChange(next)
  }

  const go = (entry: Entry | undefined) => {
    if (!entry) return
    setOpen(false)
    navigate(entry.to)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActive((i) => (entries.length ? (i + 1) % entries.length : 0))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActive((i) => (entries.length ? (i - 1 + entries.length) % entries.length : 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      go(entries[active])
    }
  }

  let lastGroup = ""

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-[rgb(8_13_11/0.4)] duration-200 supports-backdrop-filter:backdrop-blur-[4px] data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup
          aria-label={t("shell.paletteTitle")}
          className="fixed top-[12vh] left-1/2 z-50 flex max-h-[min(560px,76vh)] w-[min(640px,calc(100%-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-[16px] border border-border bg-popover text-popover-foreground shadow-[0_24px_64px_-24px_rgb(8_13_11/0.5)] duration-200 ease-[cubic-bezier(.2,.8,.2,1)] outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-96 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-96"
        >
          <DialogPrimitive.Title className="sr-only">{t("shell.paletteTitle")}</DialogPrimitive.Title>
          <div className="flex items-center gap-3 border-b border-border px-4">
            <Search className="size-5 shrink-0 text-muted-foreground" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setActive(0)
              }}
              onKeyDown={onKeyDown}
              placeholder={t("shell.searchPlaceholder")}
              role="combobox"
              aria-expanded
              aria-controls="command-palette-list"
              aria-activedescendant={entries[active] ? `cp-${entries[active].id}` : undefined}
              className="h-14 min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-muted-foreground"
            />
            <kbd className="hidden rounded-md border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground sm:block">
              Esc
            </kbd>
          </div>
          <div ref={listRef} id="command-palette-list" role="listbox" className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
            {entries.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">
                {loading ? t("shell.searching") : t("shell.noResults", { q: query })}
              </p>
            ) : (
              entries.map((entry, index) => {
                const header = entry.group !== lastGroup ? entry.group : null
                lastGroup = entry.group
                const Icon = entry.icon
                const selected = index === active
                return (
                  <div key={entry.id}>
                    {header ? (
                      <div className="px-3 pt-3 pb-1.5 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                        {header}
                      </div>
                    ) : null}
                    <div
                      id={`cp-${entry.id}`}
                      role="option"
                      aria-selected={selected}
                      data-index={index}
                      onMouseMove={() => setActive(index)}
                      onClick={() => go(entry)}
                      className={cn(
                        "flex h-11 cursor-pointer items-center gap-3 rounded-[10px] px-3 text-[14px]",
                        selected ? "bg-accent text-accent-foreground" : "text-foreground",
                      )}
                    >
                      <Icon className="size-4 shrink-0 opacity-80" aria-hidden />
                      {entry.dot ? <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", entry.dot)} /> : null}
                      <span className="min-w-0 truncate font-medium">{entry.label}</span>
                      {entry.hint ? (
                        <span className="ml-auto shrink-0 truncate font-mono text-xs text-muted-foreground">{entry.hint}</span>
                      ) : null}
                      {selected ? <CornerDownLeft className={cn("size-3.5 shrink-0 opacity-70", !entry.hint && "ml-auto")} aria-hidden /> : null}
                    </div>
                  </div>
                )
              })
            )}
          </div>
          <div className="border-t border-border px-4 py-2 text-xs text-muted-foreground">{t("shell.paletteHint")}</div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
