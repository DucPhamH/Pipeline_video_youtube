import { useEffect, useMemo, useState, type ComponentType, type ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowRight, BookOpen, FileUp, Globe, Headphones, Plus } from "lucide-react"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { PageHeader, PageShell, SegmentedTabs, type StageTone } from "@/components/PageChrome"
import { Skeleton } from "@/components/Skeleton"
import { StatusPill } from "@/components/StatusPill"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { recentListens, recentReads } from "@/lib/progress"
import type { Novel } from "@/api/types"
import { crawlApi, type Pipeline } from "@/features/crawl/api"
import { translateApi } from "@/features/translate/api"
import type { Inbox, Work } from "@/features/translate/types"
import { ttsApi, type TtsWorkListItem } from "@/features/tts/api"
import { usePlayer } from "@/features/player/PlayerProvider"
import { writeApi, type StoryListItem } from "@/features/write/api"
import { useActiveJobs } from "@/layout/useActiveJobs"

function readTarget(work: Work): string | null {
  const done = work.variants.find((v) => v.status === "ready" && v.latest_job_id != null)
  return done ? `/read/translate/${work.id}/${done.latest_job_id}` : null
}

const pct = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : null)

// ---------------------------------------------------------------------------
// Bảng pipeline: dữ liệu rẻ từ các API có sẵn (inbox dịch, truyện đang crawl/lỗi, pipeline).

type BoardData = {
  inbox: Inbox | null
  crawling: Novel[]
  errored: Novel[]
  pipelines: Pipeline[]
  novelTotal: number
}

async function loadBoard(): Promise<BoardData> {
  const [inbox, crawling, errored, pipelines, any] = await Promise.allSettled([
    translateApi.getInbox(),
    crawlApi.listNovels({ status: "crawling", limit: 6 }),
    crawlApi.listNovels({ status: "error", limit: 6 }),
    crawlApi.listPipelines(),
    crawlApi.listNovels({ limit: 1 }),
  ])
  return {
    inbox: inbox.status === "fulfilled" ? inbox.value : null,
    crawling: crawling.status === "fulfilled" ? crawling.value.items : [],
    errored: errored.status === "fulfilled" ? errored.value.items : [],
    pipelines: pipelines.status === "fulfilled" ? pipelines.value.items : [],
    novelTotal: any.status === "fulfilled" ? any.value.total : 0,
  }
}

type BoardItem = {
  key: string
  title: string
  to: string
  /** Phần bên phải: "24/39", StatusPill… */
  meta?: ReactNode
  progress?: number | null
  /** Dòng gợi ý cho cột "Cần bạn". */
  hint?: string
  action?: string
}

type ContinueItem = {
  key: string
  kind: "read" | "listen"
  stage: StageTone
  title: string
  detail: string
  current: number | null
  total: number | null
  at: number
  to?: string
  onOpen?: () => void
  workspace: string | null
}

export function HomePage() {
  const t = useT()
  const navigate = useNavigate()
  const player = usePlayer()
  const [reads] = useState(recentReads)
  const [listens] = useState(recentListens)
  const [works, setWorks] = useState<Work[] | null>(null)
  const [books, setBooks] = useState<TtsWorkListItem[] | null>(null)
  const [stories, setStories] = useState<StoryListItem[] | null>(null)
  const active = useActiveJobs()
  const board = useQuery({ queryKey: ["home", "board"], queryFn: loadBoard, refetchInterval: 10_000 })

  useEffect(() => {
    let stale = false
    translateApi
      .listWorks()
      .then((r) => !stale && setWorks(r.items))
      .catch(() => !stale && setWorks([]))
    ttsApi
      .listWorks()
      .then((r) => !stale && setBooks(r.items))
      .catch(() => !stale && setBooks([]))
    writeApi
      .list()
      .then((r) => !stale && setStories(r.items))
      .catch(() => !stale && setStories([]))

    return () => {
      stale = true
    }
  }, [])

  async function resumeListen(workId: number, segmentId: number, time: number) {
    const work = await ttsApi.getWork(workId)
    const jobId = work.readings[0]?.latest_job?.id
    if (!jobId) return
    const segs = (await ttsApi.segments(jobId)).filter((s) => s.has_audio)
    const at = segs.findIndex((s) => s.id === segmentId)
    player.play(
      {
        workId,
        title: work.title,
        tracks: segs.map((s) => ({ segmentId: s.id, title: s.title, url: ttsApi.audioUrl(s.id) })),
      },
      Math.max(0, at),
      at >= 0 ? time : 0,
    )
  }

  // --- Đọc / nghe dở -------------------------------------------------------
  const continues = useMemo<ContinueItem[]>(() => {
    const rows: ContinueItem[] = []
    for (const r of reads) {
      let current: number | null = null
      let total: number | null = null
      let workspace: string | null = null
      if (r.kind === "translate") {
        const work = works?.find((w) => w.variants.some((v) => v.latest_job_id === r.id))
        if (work) {
          workspace = `/translate/${work.id}`
          const at = work.chapters.findIndex((c) => c.index === r.chapter)
          total = work.chapters.length
          current = at >= 0 ? at + 1 : null
        }
      } else {
        workspace = `/write/${r.id}`
        const story = stories?.find((s) => s.id === r.id)
        if (story) {
          total = story.chapter_count
          current = r.chapter
        }
      }
      rows.push({
        key: `r-${r.kind}-${r.id}`,
        kind: "read",
        stage: r.kind === "write" ? "write" : "translate",
        title: r.title,
        detail: r.chapterTitle,
        current,
        total,
        at: r.at,
        to: `${r.path}?ch=${r.chapter}`,
        workspace,
      })
    }
    for (const l of listens) {
      const book = books?.find((b) => b.id === l.workId)
      rows.push({
        key: `l-${l.workId}`,
        kind: "listen",
        stage: "listen",
        title: l.title,
        detail: l.chapterTitle,
        current: null,
        total: book?.chapter_count ?? null,
        at: l.at,
        onOpen: () => void resumeListen(l.workId, l.segmentId, l.time),
        workspace: `/tts/${l.workId}`,
      })
    }
    return rows.sort((a, b) => b.at - a.at)
    // resumeListen chỉ đóng gói player — không cần làm phụ thuộc.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reads, listens, works, books, stories])

  // --- Các cột pipeline ----------------------------------------------------
  const columns = useMemo(() => {
    const data = board.data
    const collecting: BoardItem[] = []
    const translating: BoardItem[] = []
    const listening: BoardItem[] = []
    const needs: BoardItem[] = []

    for (const n of data?.crawling ?? []) {
      const done = n.crawled_chapters ?? n.last_chapter_index
      const total = n.total_chapters ?? 0
      collecting.push({
        key: `cr-${n.id}`,
        title: n.title,
        to: `/novels/${n.id}`,
        meta: total > 0 ? `${done}/${total}` : <StatusPill status="crawling" />,
        progress: total > 0 ? pct(done, total) : undefined,
      })
      if (n.failed_chapters) {
        needs.push({
          key: `cf-${n.id}`,
          title: n.title,
          to: `/novels/${n.id}`,
          hint: t("home.failedChapters", { count: n.failed_chapters }),
          action: t("home.takeLook"),
        })
      }
    }
    for (const p of data?.pipelines ?? []) {
      if (p.stage === "smoothing") {
        collecting.push({ key: `sm-${p.novel_id}`, title: p.title, to: `/novels/${p.novel_id}`, meta: <StatusPill status="smoothing" /> })
      }
      if (p.stage === "error") {
        needs.push({
          key: `pe-${p.novel_id}`,
          title: p.title,
          to: `/novels/${p.novel_id}`,
          hint: t("home.pipelineError"),
          action: t("home.takeLook"),
        })
      }
    }

    const tracked = new Set<string>()
    for (const j of active.jobs) {
      tracked.add(j.key)
      const item: BoardItem = {
        key: j.key,
        title: j.title,
        to: j.to,
        meta: j.total > 0 ? `${j.done}/${j.total}` : <StatusPill status={j.status} />,
        progress: j.total > 0 ? pct(j.done, j.total) : undefined,
      }
      if (j.kind === "translate") translating.push(item)
      else listening.push(item)
    }
    for (const row of data?.inbox?.running ?? []) {
      const key = `tr-${row.variant_id}`
      if (tracked.has(key)) continue
      translating.push({
        key,
        title: row.work_title,
        to: row.job_id ? `/translate/${row.work_id}/jobs/${row.job_id}` : `/translate/${row.work_id}`,
        meta: <StatusPill status={row.job_status ?? "running"} />,
      })
    }
    for (const row of data?.inbox?.needs_review ?? []) {
      needs.push({
        key: `rv-${row.variant_id}`,
        title: row.work_title,
        to: row.job_id ? `/translate/${row.work_id}/jobs/${row.job_id}` : `/translate/${row.work_id}`,
        hint: row.unreviewed ? t("home.toReview", { count: row.unreviewed }) : t("home.awaitingReview"),
        action: t("home.review"),
      })
    }
    for (const n of data?.errored ?? []) {
      needs.push({
        key: `ce-${n.id}`,
        title: n.title,
        to: `/novels/${n.id}`,
        hint: n.failed_chapters ? t("home.failedChapters", { count: n.failed_chapters }) : t("home.crawlError"),
        action: t("home.takeLook"),
      })
    }
    return { collecting, translating, listening, needs }
  }, [board.data, active.jobs, t])

  // --- Kệ sách -------------------------------------------------------------
  type ShelfKind = "all" | "translate" | "listen" | "write"
  const [shelfKind, setShelfKind] = useState<ShelfKind>("all")
  const shelfLoading = works == null || books == null || stories == null
  const shelf = useMemo(() => {
    const rows: Array<{ key: string; kind: Exclude<ShelfKind, "all">; title: string; caption: string; to: string }> = []
    for (const w of works ?? []) {
      rows.push({
        key: `t-${w.id}`,
        kind: "translate",
        title: w.title,
        caption: `${w.lang_src} → ${w.lang_tgt} · ${t("home.chaptersShort", { count: w.chapters.length })}`,
        to: readTarget(w) ?? `/translate/${w.id}`,
      })
    }
    for (const b of books ?? []) {
      rows.push({
        key: `a-${b.id}`,
        kind: "listen",
        title: b.title,
        caption: `${b.author || b.lang} · ${t("home.chaptersShort", { count: b.chapter_count })}`,
        to: `/tts/${b.id}`,
      })
    }
    for (const s of stories ?? []) {
      rows.push({
        key: `w-${s.id}`,
        kind: "write",
        title: s.title,
        caption: t("home.written", { filled: s.filled_count, total: s.chapter_count }),
        to: s.filled_count > 0 ? `/read/write/${s.id}` : `/write/${s.id}`,
      })
    }
    return rows
  }, [works, books, stories, t])
  const shelfCounts = {
    all: shelf.length,
    translate: works?.length ?? 0,
    listen: books?.length ?? 0,
    write: stories?.length ?? 0,
  }
  const shownShelf = shelfKind === "all" ? shelf : shelf.filter((s) => s.kind === shelfKind)

  const brandNew =
    !shelfLoading && shelf.length === 0 && continues.length === 0 && board.isSuccess && board.data.novelTotal === 0

  const hero = continues[0] ?? null
  const nextStep = hero
    ? (columns.needs.find((n) => n.title === hero.title) ?? columns.needs[0] ?? null)
    : null

  const addMenu = (
    <ActionMenu
      variant="default"
      size="default"
      label={
        <>
          <Plus className="size-4" aria-hidden />
          {t("home.addBook")}
        </>
      }
    >
      <ActionMenuItem onSelect={() => navigate("/sites")}>{t("home.addCollect")}</ActionMenuItem>
      <ActionMenuItem onSelect={() => navigate("/translate")}>{t("home.addTranslate")}</ActionMenuItem>
      <ActionMenuItem onSelect={() => navigate("/tts")}>{t("home.addListen")}</ActionMenuItem>
    </ActionMenu>
  )

  return (
    <PageShell className="space-y-8">
      <PageHeader title={t("home.title")} description={t("home.subtitle")} primaryAction={addMenu} />

      {brandNew ? (
        <Onboarding />
      ) : (
        <>
          {hero ? <ContinueHero item={hero} nextStep={nextStep} /> : null}

          {continues.length > 1 ? (
            <section className="space-y-3" aria-label={t("home.alsoReading")}>
              <h2 className="text-[13px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                {t("home.alsoReading")}
              </h2>
              <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {continues.slice(1, 5).map((c) => (
                  <ContinueChip key={c.key} item={c} />
                ))}
              </div>
            </section>
          ) : null}

          <section className="space-y-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
              <h2 className="font-display text-[22px] font-semibold">{t("home.shelfTitle")}</h2>
              {!shelfLoading ? (
                <span className="text-[13px] text-muted-foreground">{t("home.bookCount", { count: shelf.length })}</span>
              ) : null}
              {shelfKind !== "all" ? (
                <Link
                  to={shelfKind === "translate" ? "/translate" : shelfKind === "listen" ? "/tts" : "/write"}
                  className="ml-auto text-[13px] font-semibold text-accent-foreground hover:underline dark:text-primary"
                >
                  {t("home.seeAll")}
                </Link>
              ) : null}
            </div>
            {shelf.length > 0 ? (
              <SegmentedTabs
                value={shelfKind}
                onChange={setShelfKind}
                items={[
                  { value: "all", label: t("home.filterAll"), count: shelfCounts.all },
                  { value: "translate", label: t("home.shelfTranslate"), count: shelfCounts.translate },
                  { value: "listen", label: t("home.shelfListen"), count: shelfCounts.listen },
                  { value: "write", label: t("home.shelfWrite"), count: shelfCounts.write },
                ]}
              />
            ) : null}
            {shelfLoading ? (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-5 sm:grid-cols-[repeat(auto-fill,minmax(140px,1fr))]">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="aspect-[2/3] w-full rounded-[6px_12px_12px_6px]" />
                ))}
              </div>
            ) : shelf.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border bg-card">
                <EmptyState
                  compact
                  icon={BookOpen}
                  title={t("home.shelfEmpty")}
                  hint={t("home.shelfEmptyHint")}
                  action={
                    <Link to="/sites" className={buttonVariants({ variant: "outline", size: "sm" })}>
                      {t("home.addCollect")}
                    </Link>
                  }
                />
              </div>
            ) : (
              <div
                key={shelfKind}
                className="stagger grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-x-5 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(140px,1fr))]"
              >
                {shownShelf.map((b) => (
                  <Link key={b.key} to={b.to} className="group block min-w-0 space-y-2.5 rounded-lg focus-visible:outline-none">
                    <BookCover title={b.title} subtitle={b.caption} className="group-focus-visible:ring-2 group-focus-visible:ring-ring" />
                    <div className="space-y-0.5">
                      <p className="truncate text-sm font-semibold group-hover:underline">{b.title}</p>
                      <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                        <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", STAGE_DOT[b.kind])} />
                        <span className="truncate">{b.caption}</span>
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-4" aria-label={t("home.board")}>
            <h2 className="font-display text-[22px] font-semibold">{t("home.board")}</h2>
            <div className="grid items-start gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
              <BoardColumn stage="collect" title={t("home.colCollect")} items={columns.collecting} loading={board.isPending} />
              <BoardColumn stage="translate" title={t("home.colTranslate")} items={columns.translating} loading={board.isPending} />
              <BoardColumn stage="listen" title={t("home.colListen")} items={columns.listening} loading={board.isPending} />
              <BoardColumn stage="write" title={t("home.colNeeds")} items={columns.needs} loading={board.isPending} needs />
            </div>
          </section>
        </>
      )}
    </PageShell>
  )
}

const STAGE_DOT: Record<StageTone, string> = {
  collect: "bg-stage-collect",
  translate: "bg-stage-translate",
  listen: "bg-stage-listen",
  write: "bg-stage-write",
}

function ContinueHero({ item, nextStep }: { item: ContinueItem; nextStep: BoardItem | null }) {
  const t = useT()
  const progress = item.current != null && item.total ? pct(item.current, item.total) : null
  const ctaLabel =
    item.kind === "listen"
      ? t("home.keepListening")
      : item.current != null
        ? t("home.readChapter", { n: item.current })
        : t("home.keepReading")
  const CtaIcon = item.kind === "listen" ? Headphones : BookOpen
  const cta =
    item.to != null ? (
      <Link to={item.to} className={buttonVariants({ variant: "default" })}>
        <CtaIcon className="size-4" aria-hidden />
        {ctaLabel}
      </Link>
    ) : (
      <Button type="button" onClick={item.onOpen}>
        <CtaIcon className="size-4" aria-hidden />
        {ctaLabel}
      </Button>
    )

  return (
    <section className="rise relative flex flex-col gap-6 overflow-hidden rounded-[20px] bg-sidebar p-5 text-white sm:p-7 md:flex-row md:items-stretch md:gap-7">
      <div aria-hidden className="pointer-events-none absolute -top-[120px] -right-20 size-[420px] rounded-full bg-primary opacity-25" />
      <div className="relative flex min-w-0 flex-1 gap-5 sm:gap-7">
        <BookCover title={item.title} subtitle="" lift={false} className="w-[88px] shrink-0 self-start sm:w-[132px]" />
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.1em] text-glow uppercase">
            {item.kind === "listen" ? t("home.listening") : t("home.continue")}
          </div>
          <h2 className="font-display text-[26px] leading-tight font-semibold break-words sm:text-[34px]">{item.title}</h2>
          <p className="text-sm text-sidebar-foreground">
            {item.current != null && item.total
              ? t("home.chapterOf", { current: item.current, total: item.total })
              : item.total
                ? t("home.chaptersShort", { count: item.total })
                : null}
            {item.detail ? (
              <>
                {item.total ? " · " : null}
                <span className="text-white/90">{item.detail}</span>
              </>
            ) : null}
          </p>
          {progress != null ? (
            <Progress
              value={progress}
              tone="glow"
              trackClassName="bg-sidebar-border"
              className="max-w-[520px]"
              label={t("home.chapterOf", { current: item.current ?? 0, total: item.total ?? 0 })}
            />
          ) : null}
          <div className="mt-auto flex flex-wrap gap-2.5 pt-2">
            {cta}
            {item.workspace ? (
              <Link to={item.workspace} className={buttonVariants({ variant: "outline" })}>
                {t("home.openWorkspace")}
              </Link>
            ) : null}
          </div>
        </div>
      </div>
      {nextStep ? (
        <div className="relative flex w-full flex-col gap-2 md:w-[260px] md:shrink-0">
          <div className="text-xs font-semibold tracking-[0.1em] text-sidebar-muted uppercase">{t("home.nextStep")}</div>
          <div className="rounded-xl border border-sidebar-border bg-sidebar-surface p-3.5 text-sm leading-relaxed text-[#C9D3CF]">
            <span className="font-semibold text-white">{nextStep.title}</span>
            {" — "}
            {nextStep.hint}{" "}
            <Link to={nextStep.to} className="inline-flex items-center gap-1 font-semibold text-glow hover:underline">
              {nextStep.action}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function ContinueChip({ item }: { item: ContinueItem }) {
  const t = useT()
  const Icon = item.kind === "listen" ? Headphones : BookOpen
  const body = (
    <>
      <BookCover title={item.title} subtitle="" className="w-11 shrink-0" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon className="size-3.5" aria-hidden />
          {item.kind === "listen" ? t("home.listening") : t("home.reading")}
        </p>
        <p className="truncate text-sm font-semibold">{item.title}</p>
        <p className="truncate text-xs text-muted-foreground">{item.detail}</p>
      </div>
    </>
  )
  const cls =
    "group flex w-full items-center gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
  return item.to != null ? (
    <Link to={item.to} className={cls}>
      {body}
    </Link>
  ) : (
    <button type="button" onClick={item.onOpen} className={cls}>
      {body}
    </button>
  )
}

const COLUMN_TONE: Record<StageTone, { bg: string; text: string }> = {
  collect: { bg: "bg-stage-collect-soft", text: "text-stage-collect" },
  translate: { bg: "bg-stage-translate-soft", text: "text-stage-translate" },
  listen: { bg: "bg-stage-listen-soft", text: "text-stage-listen" },
  write: { bg: "bg-stage-write-soft", text: "text-stage-write" },
}

const COLUMN_LIMIT = 4

function BoardColumn({
  stage,
  title,
  items,
  loading,
  needs = false,
}: {
  stage: StageTone
  title: string
  items: BoardItem[]
  loading: boolean
  needs?: boolean
}) {
  const t = useT()
  const tone = COLUMN_TONE[stage]
  const shown = items.slice(0, COLUMN_LIMIT)
  const rest = items.length - shown.length
  return (
    <div className={cn("flex min-w-0 flex-col gap-2.5 rounded-2xl p-3.5", tone.bg)}>
      <div className={cn("flex items-center gap-2 text-[13px] font-bold", tone.text)}>
        {title}
        <span className="ml-auto font-mono">{loading ? "–" : items.length}</span>
      </div>
      {loading ? (
        <Skeleton className="h-[52px] w-full rounded-xl" />
      ) : items.length === 0 ? (
        <p className="px-1 py-2 text-[13px] text-muted-foreground">{t("home.colEmpty")}</p>
      ) : (
        <ul className="stagger flex flex-col gap-2.5">
          {shown.map((item) => (
            <li key={item.key}>
              <Link
                to={item.to}
                className="flex flex-col gap-2 rounded-xl border border-border bg-card px-3.5 py-3 transition-[border-color,box-shadow] hover:border-primary/40 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">{item.title}</span>
                  {item.meta != null ? (
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">{item.meta}</span>
                  ) : null}
                </div>
                {item.progress != null ? (
                  <Progress value={item.progress} tone={stage} live size="sm" label={item.title} />
                ) : null}
                {needs && item.hint ? <span className="text-xs text-muted-foreground">{item.hint}</span> : null}
              </Link>
            </li>
          ))}
          {rest > 0 ? (
            <li className="px-1 text-xs font-medium text-muted-foreground">{t("home.more", { count: rest })}</li>
          ) : null}
        </ul>
      )}
    </div>
  )
}

function Onboarding() {
  const t = useT()
  const steps: Array<{
    to: string
    icon: ComponentType<{ className?: string }>
    stage: StageTone
    title: string
    hint: string
    cta: string
  }> = [
    { to: "/sites", icon: Globe, stage: "collect", title: t("home.addCollect"), hint: t("home.onboardCollect"), cta: t("home.onboardCollectCta") },
    { to: "/translate", icon: FileUp, stage: "translate", title: t("home.addTranslate"), hint: t("home.onboardTranslate"), cta: t("home.onboardTranslateCta") },
    { to: "/tts", icon: Headphones, stage: "listen", title: t("home.addListen"), hint: t("home.onboardListen"), cta: t("home.onboardListenCta") },
  ]
  return (
    <section className="rise space-y-6 rounded-[20px] border border-border bg-card p-5 sm:p-8">
      <EmptyState icon={BookOpen} title={t("home.welcomeTitle")} hint={t("home.welcomeHint")} className="py-6" />
      <div className="stagger grid gap-3.5 md:grid-cols-3">
        {steps.map((s) => (
          <Link
            key={s.to}
            to={s.to}
            className={cn(
              "lift group flex flex-col gap-3 rounded-2xl p-5 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              COLUMN_TONE[s.stage].bg,
            )}
          >
            <span className={cn("flex size-10 items-center justify-center rounded-full bg-card", COLUMN_TONE[s.stage].text)}>
              <s.icon className="size-5" />
            </span>
            <span className="text-[17px] font-semibold text-foreground">{s.title}</span>
            <span className="text-sm text-muted-foreground">{s.hint}</span>
            <span className={cn("mt-auto inline-flex items-center gap-1 text-sm font-semibold", COLUMN_TONE[s.stage].text)}>
              {s.cta}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}
