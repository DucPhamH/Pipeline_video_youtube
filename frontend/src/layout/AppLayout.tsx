import { useEffect, useRef, useState, type ComponentType } from "react"
import { Link, NavLink, Outlet, useLocation } from "react-router-dom"
import { useTheme } from "next-themes"
import {
  Globe2,
  Headphones,
  Languages,
  LibraryBig,
  Menu,
  Moon,
  MoreHorizontal,
  PenLine,
  Search,
  Settings,
  Sun,
  Wrench,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Progress } from "@/components/ui/progress"
import { percent } from "@/lib/utils"
import { LanguageSwitcher } from "@/i18n/LanguageSwitcher"
import { useT } from "@/i18n"
import { usePlayerInset } from "@/features/player/PlayerProvider"
import { CommandPalette } from "./CommandPalette"
import { useActiveJobs, type ActiveJob } from "./useActiveJobs"

type Stage = "collect" | "translate" | "listen" | "write"

type NavItem = {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  also?: string[]
  exact?: boolean
  stage?: Stage
  count?: number
}

const STAGE_DOT: Record<Stage, string> = {
  collect: "bg-stage-collect",
  translate: "bg-stage-translate",
  listen: "bg-stage-listen",
  write: "bg-stage-write",
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable
}

function BrandMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-[10px] bg-[#0B8F6B] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2)]",
        className,
      )}
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="size-[70%]">
        <path
          fill="currentColor"
          d="M8.2 9.4c2.5-.9 5.1-.2 7.8 1.2 2.7-1.4 5.3-2.1 7.8-1.2v13.2c-2.5-.9-5.1-.2-7.8 1.2-2.7-1.4-5.3-2.1-7.8-1.2V9.4z"
        />
        <path stroke="#0B8F6B" strokeWidth="1.2" strokeLinecap="round" d="M16 10.9v13" />
      </svg>
    </div>
  )
}

/** Hai nút Sáng/Tối gọn cho chân sidebar (nền mực). */
function ThemeSwitch() {
  const t = useT()
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === "dark"
  const opt = (value: "light" | "dark", Icon: typeof Sun, label: string) => {
    const on = resolvedTheme != null && (value === "dark") === dark
    return (
      <button
        type="button"
        aria-pressed={on}
        aria-label={label}
        title={label}
        onClick={() => setTheme(value)}
        className={cn(
          "flex size-7 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none",
          on ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-muted hover:text-sidebar-accent-foreground",
        )}
      >
        <Icon className="size-4" />
      </button>
    )
  }
  return (
    <div role="group" aria-label={t("shell.theme")} className="flex items-center gap-0.5 rounded-lg border border-sidebar-border bg-sidebar-surface p-0.5">
      {opt("light", Sun, t("shell.light"))}
      {opt("dark", Moon, t("shell.dark"))}
    </div>
  )
}

function SidebarLink({ item, active, onNavigate }: { item: NavItem; active: boolean; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex h-[38px] items-center gap-[11px] rounded-[9px] px-3 text-[14px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
      )}
    >
      {active ? (
        <span aria-hidden className="absolute top-2 bottom-2 -left-3.5 w-[3px] rounded-full bg-sidebar-primary" />
      ) : null}
      {item.stage ? <span aria-hidden className={cn("size-[7px] shrink-0 rounded-full", STAGE_DOT[item.stage])} /> : null}
      <Icon className="size-[18px] shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
      {item.count ? (
        <span className="ml-auto rounded-full bg-sidebar-border px-[7px] py-0.5 font-mono text-[11px] leading-none text-[#9FE8CF]">
          {item.count}
        </span>
      ) : null}
    </NavLink>
  )
}

function RunningNow({ jobs, onNavigate }: { jobs: ActiveJob[]; onNavigate?: () => void }) {
  const t = useT()
  if (jobs.length === 0) return null
  return (
    <div className="rise flex flex-col gap-2.5 rounded-xl border border-sidebar-border bg-sidebar-surface p-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-[#E6EEEB]">
        <span aria-hidden className="dot-live size-[7px] rounded-full bg-glow" />
        {t("shell.runningNow")}
        <span className="ml-auto font-medium text-sidebar-muted tabular-nums">{jobs.length}</span>
      </div>
      {jobs.slice(0, 3).map((job) => {
        const pct = percent(job.done, job.total)
        return (
          <Link
            key={job.key}
            to={job.to}
            onClick={onNavigate}
            className="group flex flex-col gap-1.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring/60"
          >
            <span className="flex items-center gap-2 text-xs text-sidebar-foreground group-hover:text-sidebar-accent-foreground">
              <span className="min-w-0 truncate">
                {job.title} · {job.kind === "translate" ? t("shell.kindTranslate") : t("shell.kindListen")}
              </span>
              <span className="ml-auto shrink-0 font-mono text-sidebar-muted">
                {job.kind === "listen" && job.total ? `${job.done}/${job.total}` : pct != null ? `${pct}%` : "…"}
              </span>
            </span>
            <Progress
              value={pct}
              size="sm"
              live
              tone={job.kind === "translate" ? "glow" : "live"}
              trackClassName="bg-sidebar-border"
              label={job.title}
            />
          </Link>
        )
      })}
    </div>
  )
}

export function AppLayout() {
  const t = useT()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { pathname } = useLocation()
  const playerOpen = usePlayerInset()
  const active = useActiveJobs(true)

  const drawerRef = useRef<HTMLElement | null>(null)

  // Ctrl/⌘ K mở bảng lệnh ở mọi nơi (kể cả khi đang gõ); "/" chỉ khi không gõ vào ô nhập.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen((v) => !v)
        return
      }
      if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // Drawer mobile: Esc đóng, giữ focus bên trong (Tab vòng), khoá cuộn body,
  // đóng xong trả focus về nút mở.
  useEffect(() => {
    if (!mobileOpen) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    const focusables = () =>
      Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      )
    focusables()[0]?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileOpen(false)
        return
      }
      if (e.key !== "Tab") return
      const items = focusables()
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      const current = document.activeElement
      const inside = current instanceof Node && drawerRef.current?.contains(current)
      if (e.shiftKey && (current === first || !inside)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (current === last || !inside)) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prevOverflow
      previous?.focus()
    }
  }, [mobileOpen])

  const shelf: NavItem = { to: "/", label: t("nav.home"), icon: LibraryBig, also: ["/read"], exact: true }
  // /sites/:key và /novels/:id (chi tiết truyện crawl) thuộc bước Thu thập.
  const pipeline: NavItem[] = [
    { to: "/sites", label: t("shell.collect"), icon: Globe2, also: ["/novels"], stage: "collect" },
    { to: "/translate", label: t("nav.translate"), icon: Languages, stage: "translate", count: active.translateCount },
    { to: "/tts", label: t("nav.tts"), icon: Headphones, stage: "listen", count: active.listenCount },
    { to: "/write", label: t("nav.write"), icon: PenLine, stage: "write" },
  ]
  const utility: NavItem[] = [
    { to: "/settings", label: t("nav.settings"), icon: Settings },
    ...(import.meta.env.DEV ? [{ to: "/dev-tools", label: t("nav.devTools"), icon: Wrench }] : []),
  ]

  const isItemActive = (item: NavItem) =>
    (item.exact ? pathname === item.to : false) ||
    [...(item.exact ? [] : [item.to]), ...(item.also ?? [])].some((p) => pathname === p || pathname.startsWith(`${p}/`))

  const paletteItems = [shelf, ...pipeline, ...utility].map(({ to, label, icon }) => ({ to, label, icon }))

  const searchButton = (
    <button
      type="button"
      onClick={() => setPaletteOpen(true)}
      className="flex h-[38px] w-full items-center gap-2.5 rounded-[9px] border border-sidebar-border bg-sidebar-surface px-3 text-[13px] text-sidebar-muted transition-colors hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none"
    >
      <Search className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{t("shell.search")}</span>
      <kbd className="ml-auto shrink-0 font-mono text-[11px] text-[#5D6C67]">{t("shell.shortcut")}</kbd>
    </button>
  )

  const navBody = (onNavigate?: () => void) => (
    <>
      <nav className="flex flex-col gap-1" aria-label={t("nav.main")}>
        <SidebarLink item={shelf} active={isItemActive(shelf)} onNavigate={onNavigate} />
        <div className="px-3 pt-4 pb-1.5 text-[11px] font-semibold tracking-[0.08em] text-[#5D6C67] uppercase">
          {t("shell.pipeline")}
        </div>
        {pipeline.map((item) => (
          <SidebarLink key={item.to} item={item} active={isItemActive(item)} onNavigate={onNavigate} />
        ))}
      </nav>
      <div className="min-h-4 flex-1" />
      <RunningNow jobs={active.jobs} onNavigate={onNavigate} />
      <nav className="flex flex-col gap-1 pt-3" aria-label={t("nav.settings")}>
        {utility.map((item) => (
          <SidebarLink key={item.to} item={item} active={isItemActive(item)} onNavigate={onNavigate} />
        ))}
      </nav>
      <div className="mt-3 flex items-center gap-2 border-t border-sidebar-border pt-3">
        <ThemeSwitch />
        <LanguageSwitcher className="ml-auto h-8 w-auto min-w-0 border-sidebar-border bg-sidebar-surface text-[13px] text-sidebar-foreground" />
      </div>
    </>
  )

  const brand = (
    <div className="flex items-center gap-2.5 px-2 pt-0.5 pb-[18px]">
      <BrandMark className="size-[34px]" />
      <div className="min-w-0">
        <div className="font-display text-[20px] leading-none text-white">{t("app.title")}</div>
        <div className="mt-1 truncate text-[11px] text-sidebar-muted">{t("app.tagline")}</div>
      </div>
    </div>
  )

  const tabs: Array<{ item: NavItem; label: string }> = [
    { item: shelf, label: t("shell.shelf") },
    { item: pipeline[0], label: t("shell.collect") },
    { item: pipeline[1], label: t("nav.translate") },
    { item: pipeline[2], label: t("nav.tts") },
  ]
  const moreActive = !tabs.some((tab) => isItemActive(tab.item))

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop sidebar — mực tối, cố định */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[252px] flex-col overflow-y-auto bg-sidebar px-3.5 py-5 [scrollbar-width:none] lg:flex dark:border-r dark:border-sidebar-border">
        {brand}
        <div className="mb-3.5">{searchButton}</div>
        {navBody()}
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-40 flex h-14 items-center gap-2.5 bg-sidebar px-4 text-white lg:hidden">
        <Link to="/" className="flex min-w-0 items-center gap-2.5 rounded-md focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none">
          <BrandMark className="size-[30px] rounded-[9px]" />
          <span className="font-display truncate text-[18px] leading-none">{t("app.title")}</span>
        </Link>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label={t("shell.search")}
            className="flex size-10 items-center justify-center rounded-lg text-sidebar-foreground hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none"
          >
            <Search className="size-5" />
          </button>
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label={t("nav.openMenu")}
            aria-expanded={mobileOpen}
            className="flex size-10 items-center justify-center rounded-lg text-sidebar-foreground hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none"
          >
            <Menu className="size-5" />
          </button>
        </div>
      </header>

      {/* Mobile drawer (More) */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-[rgb(8_13_11/0.5)] backdrop-blur-[4px] animate-in fade-in-0"
            aria-label={t("nav.closeMenu")}
            onClick={() => setMobileOpen(false)}
          />
          <aside
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.main")}
            className="absolute inset-y-0 left-0 flex w-[min(288px,86vw)] flex-col overflow-y-auto bg-sidebar px-3.5 py-4 shadow-2xl animate-in slide-in-from-left duration-200"
          >
            <div className="flex items-start justify-between">
              {brand}
              <button
                type="button"
                aria-label={t("common.close")}
                onClick={() => setMobileOpen(false)}
                className="flex size-9 items-center justify-center rounded-lg text-sidebar-foreground hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-sidebar-ring/60 focus-visible:outline-none"
              >
                <X className="size-5" />
              </button>
            </div>
            {navBody(() => setMobileOpen(false))}
          </aside>
        </div>
      ) : null}

      <main
        className={cn(
          "min-w-0 px-4 pt-6 pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:px-6 lg:pl-[calc(252px+2.25rem)] lg:pr-9 lg:pt-8 lg:pb-10",
          playerOpen && "pb-[calc(10rem+env(safe-area-inset-bottom))] lg:pb-28",
        )}
      >
        <div key={pathname} className="page-enter w-full">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom tab bar */}
      <nav
        aria-label={t("nav.main")}
        className="fixed inset-x-0 bottom-0 z-40 grid h-[calc(4rem+env(safe-area-inset-bottom))] grid-cols-5 border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm lg:hidden"
      >
        {tabs.map(({ item, label }) => {
          const Icon = item.icon
          const on = isItemActive(item)
          return (
            <NavLink
              key={item.to}
              to={item.to}
              aria-current={on ? "page" : undefined}
              className={cn(
                "relative flex flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
                on ? "text-accent-foreground dark:text-primary" : "text-muted-foreground",
              )}
            >
              <Icon className="size-5" aria-hidden />
              <span className="max-w-full truncate px-1">{label}</span>
              {item.count ? (
                <span className="absolute top-2 left-[calc(50%+6px)] rounded-full bg-live px-1.5 font-mono text-[10px] leading-4 text-[#101614]">
                  {item.count}
                </span>
              ) : null}
            </NavLink>
          )
        })}
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className={cn(
            "flex flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
            moreActive ? "text-accent-foreground dark:text-primary" : "text-muted-foreground",
          )}
        >
          <MoreHorizontal className="size-5" aria-hidden />
          {t("shell.more")}
        </button>
      </nav>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} navItems={paletteItems} />
    </div>
  )
}
