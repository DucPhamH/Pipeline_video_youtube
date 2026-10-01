import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom"
import { ArrowLeft, BookOpen, ChevronLeft, ChevronRight, Minus, Plus, Type } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { EmptyState } from "@/components/EmptyState"
import { PageSkeleton, Skeleton } from "@/components/Skeleton"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { cn } from "@/lib/utils"
import { readPosition, rememberRead } from "@/lib/progress"
import { translateApi } from "@/features/translate/api"
import { writeApi } from "@/features/write/api"

type Chapter = { index: number; title: string }
type Body = { text: string; source?: string }
type Book = {
  kind: "translate" | "write"
  id: number
  title: string
  backTo: string
  chapters: Chapter[]
  load: (index: number) => Promise<Body>
}

type Theme = "light" | "sepia" | "dark"
type Prefs = { size: number; theme: Theme; bilingual: boolean }

const PREFS_KEY = "folio.reader.prefs"
const SIZES = [15, 17, 19, 21, 24]
const THEMES: Record<Theme, { bg: string; fg: string; muted: string; accent: string }> = {
  light: { bg: "#fbfbf8", fg: "#1f221d", muted: "#5f665c", accent: "#0B8F6B" },
  sepia: { bg: "#f3ead8", fg: "#3d3020", muted: "#75634a", accent: "#9a5b12" },
  dark: { bg: "#131815", fg: "#d9ddd3", muted: "#929b8e", accent: "#2BD4A0" },
}

function loadPrefs(): Prefs {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}")
    return {
      size: SIZES.includes(p.size) ? p.size : 19,
      theme: p.theme in THEMES ? p.theme : "light",
      bilingual: Boolean(p.bilingual),
    }
  } catch {
    return { size: 19, theme: "light", bilingual: false }
  }
}

function useBook(): { book: Book | null; error: string | null } {
  const { workId, jobId, storyId } = useParams()
  const [book, setBook] = useState<Book | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    const fail = (err: unknown) => {
      if (!stale) setError(err instanceof ApiError ? err.message : String(err))
    }
    if (workId && jobId) {
      Promise.all([translateApi.getWork(Number(workId)), translateApi.listSegments(Number(jobId))])
        .then(([work, segments]) => {
          if (stale) return
          const byChapter = new Map<number, number[]>()
          for (const s of segments) byChapter.set(s.chapter_index, [...(byChapter.get(s.chapter_index) ?? []), s.id])
          setBook({
            kind: "translate",
            id: Number(jobId),
            title: work.title,
            backTo: `/translate/${work.id}`,
            chapters: work.chapters
              .filter((c) => byChapter.has(c.index))
              .map((c) => ({ index: c.index, title: c.title })),
            load: async (index) => {
              const parts = await Promise.all((byChapter.get(index) ?? []).map((id) => translateApi.getSegment(id)))
              return {
                text: parts.map((p) => p.output_text ?? "").join("\n\n"),
                source: parts.map((p) => p.source_text).join("\n\n"),
              }
            },
          })
        })
        .catch(fail)
    } else if (storyId) {
      writeApi
        .get(Number(storyId))
        .then((story) => {
          if (stale) return
          const written = story.chapters.filter((c) => c.text.trim())
          setBook({
            kind: "write",
            id: story.id,
            title: story.title,
            backTo: `/write/${story.id}`,
            chapters: written.map((c) => ({ index: c.index, title: c.title })),
            load: async (index) => ({ text: written.find((c) => c.index === index)?.text ?? "" }),
          })
        })
        .catch(fail)
    }
    return () => {
      stale = true
    }
  }, [workId, jobId, storyId])

  return { book, error }
}

export function ReaderPage() {
  const t = useT()
  const { book, error } = useBook()
  const [params, setParams] = useSearchParams()
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
  const [body, setBody] = useState<Body | null>(null)
  const { pathname } = useLocation()

  const chapterParam = params.get("ch")
  const position = useMemo(() => {
    if (!book || book.chapters.length === 0) return 0
    const wanted =
      chapterParam != null ? Number(chapterParam) : (readPosition(book.kind, book.id)?.chapter ?? book.chapters[0].index)
    const at = book.chapters.findIndex((c) => c.index === wanted)
    return at < 0 ? 0 : at
  }, [book, chapterParam])
  const chapter = book?.chapters[position] ?? null

  useEffect(() => {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  }, [prefs])

  useEffect(() => {
    if (!book || !chapter) return
    let stale = false
    setBody(null)
    book
      .load(chapter.index)
      .then((next) => {
        if (stale) return
        setBody(next)
        rememberRead({
          kind: book.kind,
          id: book.id,
          path: pathname,
          title: book.title,
          chapter: chapter.index,
          chapterTitle: chapter.title,
        })
        window.scrollTo({ top: 0 })
      })
      .catch(() => {
        if (!stale) setBody({ text: t("reader.loadFailed") })
      })
    return () => {
      stale = true
    }
  }, [book, chapter, pathname, t])

  const goTo = useCallback(
    (offset: number) => {
      if (!book) return
      const next = book.chapters[position + offset]
      if (next) setParams({ ch: String(next.index) })
    },
    [book, position, setParams],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      if (e.key === "ArrowLeft") goTo(-1)
      if (e.key === "ArrowRight") goTo(1)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [goTo])

  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!settingsOpen) return
    const onDown = (e: MouseEvent) => {
      if (!settingsRef.current?.contains(e.target as Node)) setSettingsOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSettingsOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [settingsOpen])

  // Thanh tiến độ đọc trong chương (theo vị trí cuộn) — ghi thẳng vào style, không re-render.
  const barRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const el = barRef.current
      if (!el) return
      const max = document.documentElement.scrollHeight - window.innerHeight
      const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 1
      el.style.transform = `scaleX(${ratio})`
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll)
    return () => {
      if (frame) cancelAnimationFrame(frame)
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [body])

  if (error) {
    return (
      <EmptyState
        tone="neutral"
        icon={BookOpen}
        title={t("reader.loadFailed")}
        hint={error}
        action={
          <Link to="/" className="text-sm font-semibold text-accent-foreground hover:underline dark:text-primary">
            {t("reader.backShelf")}
          </Link>
        }
      />
    )
  }
  if (!book) return <PageSkeleton />
  if (!chapter) {
    return (
      <EmptyState
        tone="neutral"
        icon={BookOpen}
        title={book.title}
        hint={t("reader.empty")}
        action={
          <Link to={book.backTo} className="text-sm font-semibold text-accent-foreground hover:underline dark:text-primary">
            ← {book.title}
          </Link>
        }
      />
    )
  }

  const theme = THEMES[prefs.theme]
  const sizeAt = SIZES.indexOf(prefs.size)
  const bilingual = book.kind === "translate" && prefs.bilingual
  const paragraphs = (text: string) =>
    text
      .split(/\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
  const prev = book.chapters[position - 1] ?? null
  const next = book.chapters[position + 1] ?? null
  const line = `${theme.muted}33`
  const iconBtn =
    "inline-flex size-9 shrink-0 items-center justify-center rounded-[9px] transition-colors hover:bg-black/5 disabled:pointer-events-none disabled:opacity-35 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none dark:hover:bg-white/10"

  return (
    <div
      className="-mx-4 -mt-6 min-h-[calc(100dvh-3.5rem)] sm:-mx-6 lg:-mx-9 lg:-mt-8 lg:min-h-dvh"
      style={{ backgroundColor: theme.bg, color: theme.fg, colorScheme: prefs.theme === "dark" ? "dark" : "light" }}
    >
      <div
        className="sticky top-14 z-30 border-b backdrop-blur-md lg:top-0"
        style={{ backgroundColor: `${theme.bg}eb`, borderColor: line }}
      >
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-1.5 px-2 sm:gap-2 sm:px-4">
          <Link
            to={book.backTo}
            aria-label={book.title}
            title={book.title}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-[9px] px-1.5 py-1 text-sm font-semibold hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <ArrowLeft className="size-4 shrink-0" aria-hidden />
            <span className="font-display truncate text-[15px]">{book.title}</span>
          </Link>
          <button type="button" className={iconBtn} aria-label={t("reader.prev")} disabled={!prev} onClick={() => goTo(-1)}>
            <ChevronLeft className="size-4" />
          </button>
          <select
            aria-label={t("reader.chapter")}
            className="h-9 w-[7.5rem] min-w-0 truncate rounded-[9px] border bg-transparent px-2 text-[13px] sm:w-[14rem]"
            style={{ borderColor: `${theme.muted}55`, color: theme.fg, backgroundColor: theme.bg }}
            value={chapter.index}
            onChange={(e) => setParams({ ch: e.target.value })}
          >
            {book.chapters.map((c) => (
              <option key={c.index} value={c.index}>
                {c.index}. {c.title}
              </option>
            ))}
          </select>
          <button type="button" className={iconBtn} aria-label={t("reader.next")} disabled={!next} onClick={() => goTo(1)}>
            <ChevronRight className="size-4" />
          </button>
          <div className="relative" ref={settingsRef}>
            <button
              type="button"
              className={cn(iconBtn, settingsOpen && "bg-black/5 dark:bg-white/10")}
              aria-label={t("reader.settings")}
              aria-expanded={settingsOpen}
              aria-haspopup="dialog"
              onClick={() => setSettingsOpen((v) => !v)}
            >
              <Type className="size-4" />
            </button>
            {settingsOpen ? (
              <div
                role="dialog"
                aria-label={t("reader.settings")}
                className="rise absolute right-0 z-40 mt-2 w-[min(18rem,calc(100vw-2rem))] space-y-4 rounded-2xl border bg-popover p-4 text-popover-foreground shadow-lg"
              >
                <div className="space-y-2">
                  <p className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">{t("reader.textSize")}</p>
                  <div className="flex items-center justify-between gap-2 rounded-xl bg-muted p-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("reader.smaller")}
                      disabled={sizeAt <= 0}
                      onClick={() => setPrefs((p) => ({ ...p, size: SIZES[sizeAt - 1] }))}
                    >
                      <Minus className="size-4" />
                    </Button>
                    <span className="font-mono text-sm tabular-nums">{prefs.size}px</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("reader.larger")}
                      disabled={sizeAt >= SIZES.length - 1}
                      onClick={() => setPrefs((p) => ({ ...p, size: SIZES[sizeAt + 1] }))}
                    >
                      <Plus className="size-4" />
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">{t("reader.theme")}</p>
                  <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("reader.theme")}>
                    {(Object.keys(THEMES) as Theme[]).map((key) => (
                      <button
                        key={key}
                        type="button"
                        role="radio"
                        aria-checked={prefs.theme === key}
                        className={cn(
                          "flex h-12 flex-col items-center justify-center rounded-xl border text-xs font-semibold transition-shadow focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                          prefs.theme === key && "ring-2 ring-primary",
                        )}
                        style={{ backgroundColor: THEMES[key].bg, color: THEMES[key].fg, borderColor: `${THEMES[key].muted}55` }}
                        onClick={() => setPrefs((p) => ({ ...p, theme: key }))}
                      >
                        <span className="font-reading text-[15px] leading-none">Aa</span>
                        {t(`reader.theme_${key}`)}
                      </button>
                    ))}
                  </div>
                </div>
                {book.kind === "translate" ? (
                  <label className="flex items-center justify-between gap-3 text-sm font-medium">
                    {t("reader.bilingual")}
                    <Switch
                      checked={prefs.bilingual}
                      onCheckedChange={(checked) => setPrefs((p) => ({ ...p, bilingual: checked }))}
                    />
                  </label>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        <div aria-hidden className="h-0.5 w-full" style={{ backgroundColor: line }}>
          <div
            ref={barRef}
            className="h-full origin-left transition-transform duration-150 ease-out"
            style={{ backgroundColor: theme.accent, transform: "scaleX(0)" }}
          />
        </div>
      </div>

      <article
        key={chapter.index}
        className={cn("rise mx-auto px-5 pt-12 pb-16 sm:px-8 sm:pt-16", bilingual ? "max-w-6xl" : "max-w-[68ch]")}
      >
        <header className="mb-10 space-y-3 text-center">
          <p className="font-mono text-xs tracking-[0.12em] uppercase" style={{ color: theme.muted }}>
            {t("reader.chapterOf", { current: position + 1, total: book.chapters.length })}
          </p>
          <h1 className="font-display text-[28px] leading-[1.15] font-semibold text-balance sm:text-[36px]">{chapter.title}</h1>
          <div aria-hidden className="mx-auto h-0.5 w-10 rounded-full" style={{ backgroundColor: theme.accent }} />
        </header>
        {body == null ? (
          <div role="status" className="space-y-4">
            <span className="sr-only">{t("app.loading")}</span>
            {Array.from({ length: 7 }, (_, i) => (
              <Skeleton key={i} className={cn("h-4 opacity-60", i % 3 === 2 ? "w-3/5" : "w-full")} />
            ))}
          </div>
        ) : bilingual ? (
          <div className="rise grid gap-8 md:grid-cols-2">
            <div className="font-reading space-y-4" style={{ fontSize: prefs.size, lineHeight: 1.8 }}>
              {paragraphs(body.text).map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            <div
              className="space-y-4 border-t pt-6 md:border-t-0 md:border-l md:pt-0 md:pl-8"
              style={{ fontSize: Math.max(14, prefs.size - 2), lineHeight: 1.8, color: theme.muted, borderColor: line }}
            >
              {paragraphs(body.source ?? "").map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="font-reading rise space-y-[1.1em] text-pretty"
            style={{ fontSize: prefs.size, lineHeight: 1.8, fontWeight: 400, letterSpacing: 0 }}
          >
            {paragraphs(body.text).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        )}
        <nav className="mt-16 grid gap-3 border-t pt-8 sm:grid-cols-2" style={{ borderColor: line }} aria-label={t("reader.chapter")}>
          {prev ? (
            <ChapterLink dir="prev" label={t("reader.prev")} title={prev.title} line={line} muted={theme.muted} onClick={() => goTo(-1)} />
          ) : (
            <span className="hidden sm:block" />
          )}
          {next ? (
            <ChapterLink dir="next" label={t("reader.next")} title={next.title} line={line} muted={theme.muted} onClick={() => goTo(1)} />
          ) : (
            <p className="self-center text-center text-sm sm:text-right" style={{ color: theme.muted }}>
              {t("reader.endOfBook")}
            </p>
          )}
        </nav>
        <p className="mt-6 hidden text-center text-xs sm:block" style={{ color: theme.muted }}>
          {t("reader.keys")}
        </p>
      </article>
    </div>
  )
}

function ChapterLink({
  dir,
  label,
  title,
  line,
  muted,
  onClick,
}: {
  dir: "prev" | "next"
  label: string
  title: string
  line: string
  muted: string
  onClick: () => void
}) {
  const Icon = dir === "prev" ? ChevronLeft : ChevronRight
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex min-w-0 items-center gap-3 rounded-2xl border px-4 py-3.5 transition-colors hover:bg-black/[0.03] focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none dark:hover:bg-white/5",
        dir === "next" ? "flex-row-reverse text-right" : "text-left",
      )}
      style={{ borderColor: line }}
    >
      <Icon
        className={cn(
          "size-5 shrink-0 transition-transform",
          dir === "next" ? "group-hover:translate-x-0.5" : "group-hover:-translate-x-0.5",
        )}
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold tracking-[0.08em] uppercase" style={{ color: muted }}>
          {label}
        </span>
        <span className="font-display block truncate text-[16px] font-semibold">{title}</span>
      </span>
    </button>
  )
}
