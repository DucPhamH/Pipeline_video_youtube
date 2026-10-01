import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import {
  AlertTriangle,
  ArrowRight,
  BookX,
  Download,
  ListChecks,
  MoreHorizontal,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Wand2,
} from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { EmptyState } from "@/components/EmptyState"
import { Breadcrumbs, PageHeader, PageShell, SegmentedTabs } from "@/components/PageChrome"
import { StatusPill } from "@/components/StatusPill"
import { useConfirm } from "@/components/useConfirm"
import { queryKeys } from "@/lib/query-client"
import { ApiError } from "../../../api/client"
import type { Chapter } from "../../../api/types"
import { crawlApi } from "../api"
import { translateApi } from "@/features/translate/api"
import { ChapterReviewDialog } from "../components/ChapterReviewDialog"
import { ChapterStatusPill, StatusBadge } from "../components/StatusBadge"
import { FollowCard } from "../components/FollowCard"
import { PipelineCard } from "../components/PipelineCard"
import { PageSkeleton } from "@/components/Skeleton"

const POLL_MS = 3000
const PROGRESS_POLL_MS = 1500
const PAGE_SIZE = 20

const STATUS_VALUES = ["all", "pending", "crawled", "failed"] as const
const REVIEW_VALUES = ["all", "reviewed", "unreviewed"] as const
const CLEANED_VALUES = ["all", "cleaned", "raw"] as const
const CHAPTER_PRESETS = ["all", "need_smooth", "need_review", "failed"] as const
type ChapterPreset = (typeof CHAPTER_PRESETS)[number]

function canSmoothChapter(ch: Chapter): boolean {
  return ch.status === "crawled"
}

function detectChapterPreset(
  status: (typeof STATUS_VALUES)[number],
  review: (typeof REVIEW_VALUES)[number],
  cleaned: (typeof CLEANED_VALUES)[number],
): ChapterPreset | "custom" {
  if (status === "all" && review === "all" && cleaned === "all") return "all"
  if (status === "crawled" && review === "all" && cleaned === "raw") return "need_smooth"
  if (status === "crawled" && review === "unreviewed" && cleaned === "cleaned") return "need_review"
  if (status === "failed" && review === "all" && cleaned === "all") return "failed"
  return "custom"
}

export function NovelDetailPage() {
  const { id } = useParams<{ id: string }>()
  const novelId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const t = useT()
  const [confirm, confirmDialog] = useConfirm()
  const [reviewingChapter, setReviewingChapter] = useState<{ id: number; title: string } | null>(null)
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_VALUES)[number]>("all")
  const [reviewFilter, setReviewFilter] = useState<(typeof REVIEW_VALUES)[number]>("all")
  const [cleanedFilter, setCleanedFilter] = useState<(typeof CLEANED_VALUES)[number]>("all")
  const [search, setSearch] = useState("")
  const [offset, setOffset] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [lastSmooth, setLastSmooth] = useState<{ summary: string; protectedCount: number; chapterIds?: number[] } | null>(null)
  const [confirmDeleteNovel, setConfirmDeleteNovel] = useState(false)
  const [confirmDeleteChapterId, setConfirmDeleteChapterId] = useState<number | null>(null)
  const debouncedSearch = useDebouncedValue(search.trim(), 350)

  const statusOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.statusAll") },
        { value: "pending", label: t("novel.statusPending") },
        { value: "crawled", label: t("novel.statusCrawled") },
        { value: "failed", label: t("novel.statusError") },
      ] as const,
    [t],
  )
  const reviewOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.reviewAll") },
        { value: "reviewed", label: t("novel.reviewDone") },
        { value: "unreviewed", label: t("novel.reviewPending") },
      ] as const,
    [t],
  )
  const cleanedOptions = useMemo(
    () =>
      [
        { value: "all", label: t("novel.cleanedAll") },
        { value: "cleaned", label: t("novel.cleanedYes") },
        { value: "raw", label: t("novel.cleanedNo") },
      ] as const,
    [t],
  )

  const effectiveStatus = statusFilter === "all" ? undefined : statusFilter
  const effectiveReviewed = reviewFilter === "all" ? undefined : reviewFilter === "reviewed"
  const effectiveCleaned = cleanedFilter === "all" ? undefined : cleanedFilter === "cleaned"

  // Đổi truyện/bộ lọc → reset trang + selection NGAY TRONG RENDER (không qua
  // useEffect) — tránh 1 request thừa với offset CŨ, và reset khi chuyển giữa
  // 2 truyện (`react(set-state-in-effect)`).
  const resetKey = `${novelId}|${effectiveStatus}|${effectiveReviewed}|${cleanedFilter}|${debouncedSearch}`
  const [prevResetKey, setPrevResetKey] = useState(resetKey)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setOffset(0)
    setSelectedIds(new Set())
  }

  const chapterParams = {
    status: effectiveStatus,
    search: debouncedSearch || undefined,
    reviewed: effectiveReviewed,
    has_cleaned: effectiveCleaned,
    limit: PAGE_SIZE,
    offset,
  }

  const { data: novel, error, isLoading } = useQuery({
    queryKey: queryKeys.novel(novelId),
    queryFn: () => crawlApi.getNovel(novelId),
    enabled: Number.isFinite(novelId),
    refetchInterval: (q) => (q.state.data?.lifecycle_status === "crawling" ? POLL_MS : false),
  })
  const isCrawling = novel?.lifecycle_status === "crawling"

  const { data: liveProgress } = useQuery({
    queryKey: ["novel-progress", novelId],
    queryFn: () => crawlApi.getNovelProgress(novelId),
    enabled: Number.isFinite(novelId) && isCrawling,
    refetchInterval: isCrawling ? PROGRESS_POLL_MS : false,
    retry: false,
  })
  const progress = isCrawling ? (liveProgress?.progress ?? null) : null

  const {
    data: chaptersData,
    error: chaptersError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.chapters(novelId, chapterParams),
    queryFn: () => crawlApi.listChapters(novelId, chapterParams),
    enabled: Number.isFinite(novelId),
    placeholderData: (prev) => prev,
    refetchInterval: () => (isCrawling ? POLL_MS : false),
  })

  const { data: exportStatus, refetch: refetchExportStatus } = useQuery({
    queryKey: ["export-status", novelId],
    queryFn: () => crawlApi.getExportStatus(novelId),
    enabled: Number.isFinite(novelId),
  })

  const { data: failedCountData } = useQuery({
    queryKey: ["chapters-failed-count", novelId],
    queryFn: () => crawlApi.listChapters(novelId, { status: "failed", limit: 1, offset: 0 }),
    enabled: Number.isFinite(novelId),
  })
  const failedChapterTotal = novel?.failed_chapters ?? failedCountData?.total ?? 0

  // Đã handoff sang translate → tìm Work có external_id "crawl:novel:{id}" để link sang.
  const handedOff =
    novel?.lifecycle_status === "translating" ||
    novel?.lifecycle_status === "ready_for_video" ||
    novel?.lifecycle_status === "produced"
  const { data: translateWorkId } = useQuery({
    queryKey: ["translate-work-for-novel", novelId],
    queryFn: async () => {
      const list = await translateApi.listWorks()
      return list.items.find((w) => w.external_id === `crawl:novel:${novelId}`)?.id ?? null
    },
    enabled: Number.isFinite(novelId) && handedOff,
    retry: false,
    staleTime: 60_000,
  })

  const chapters = useMemo(() => chaptersData?.items ?? [], [chaptersData])
  const total = chaptersData?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  const smoothableOnPage = useMemo(() => chapters.filter(canSmoothChapter), [chapters])
  const allSmoothableSelected =
    smoothableOnPage.length > 0 && smoothableOnPage.every((c) => selectedIds.has(c.id))
  const someSmoothableSelected =
    smoothableOnPage.some((c) => selectedIds.has(c.id)) && !allSmoothableSelected
  const selectedCount = selectedIds.size

  const canSmoothNovel =
    novel?.lifecycle_status === "fully_crawled" ||
    novel?.lifecycle_status === "error" ||
    novel?.lifecycle_status === "translating" ||
    novel?.lifecycle_status === "ready_for_video"

  const canSendToTranslate = canSmoothNovel
  const canRetryNovel = novel?.lifecycle_status === "error" || novel?.lifecycle_status === "fully_crawled"

  const activePreset = detectChapterPreset(statusFilter, reviewFilter, cleanedFilter)

  const pipelineStep = useMemo(() => {
    if (!exportStatus || exportStatus.crawled <= 0) return null
    if (exportStatus.cleaned < exportStatus.crawled) return "smooth" as const
    if (exportStatus.reviewed < exportStatus.cleaned) return "review" as const
    if (exportStatus.can_export_workbook || exportStatus.can_export_bundle) return "export" as const
    return null
  }, [exportStatus])

  const [selectingAll, setSelectingAll] = useState(false)

  function applyChapterPreset(preset: ChapterPreset) {
    setOffset(0)
    setSelectedIds(new Set())
    if (preset === "all") {
      setStatusFilter("all")
      setReviewFilter("all")
      setCleanedFilter("all")
    } else if (preset === "need_smooth") {
      setStatusFilter("crawled")
      setReviewFilter("all")
      setCleanedFilter("raw")
    } else if (preset === "need_review") {
      setStatusFilter("crawled")
      setReviewFilter("unreviewed")
      setCleanedFilter("cleaned")
    } else {
      setStatusFilter("failed")
      setReviewFilter("all")
      setCleanedFilter("all")
    }
  }

  async function openFirstUnreviewed() {
    try {
      const page = await crawlApi.listChapters(novelId, {
        status: "crawled",
        reviewed: false,
        has_cleaned: true,
        limit: 50,
        offset: 0,
      })
      const ch = page.items[0]
      if (!ch) {
        toast.message(t("novel.reviewAllNone"))
        return
      }
      setReviewingChapter({ id: ch.id, title: ch.title })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function goNextReview() {
    if (!reviewingChapter) return
    const items = chaptersData?.items ?? []
    const idx = items.findIndex((c) => c.id === reviewingChapter.id)
    const nextOnPage = items
      .slice(idx + 1)
      .find((c) => c.status === "crawled" && !c.reviewed && c.has_cleaned)
    if (nextOnPage) {
      setReviewingChapter({ id: nextOnPage.id, title: nextOnPage.title })
      return
    }
    try {
      const page = await crawlApi.listChapters(novelId, {
        status: "crawled",
        reviewed: false,
        has_cleaned: true,
        limit: 30,
        offset: 0,
      })
      const next = page.items.find((c) => c.id !== reviewingChapter.id)
      if (next) {
        setReviewingChapter({ id: next.id, title: next.title })
      } else {
        setReviewingChapter(null)
        toast.message(t("review.noMore"))
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  // Optimistic: luôn cho "Lưu & tiếp" — goNextReview tự đóng khi hết chương.
  const hasReviewNext = reviewingChapter != null

  async function selectAllCrawledChapters() {
    setSelectingAll(true)
    try {
      const ids: number[] = []
      let off = 0
      const limit = 100
      for (;;) {
        const page = await crawlApi.listChapters(novelId, { status: "crawled", limit, offset: off })
        for (const ch of page.items) ids.push(ch.id)
        if (off + limit >= page.total || page.items.length === 0) break
        off += limit
      }
      setSelectedIds(new Set(ids))
      toast.message(ids.length ? t("novel.selectedCrawled", { count: ids.length }) : t("novel.noCrawled"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSelectingAll(false)
    }
  }

  const onError = (err: unknown) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))

  const smoothMutation = useMutation({
    mutationFn: (vars: { chapterIds?: number[]; force?: boolean }) =>
      crawlApi.smoothNovel(novelId, vars.chapterIds, vars.force ?? false),
    onSuccess: (result, vars) => {
      const scope = vars.chapterIds?.length
        ? t("novel.smoothScopeSelected", { count: result.chapters_smoothed })
        : t("novel.smoothScopeAll")
      const summary =
        t("novel.smoothSummary", { count: result.chapters_smoothed, scope }) +
        (result.removed_lines ? t("novel.smoothRemoved", { count: result.removed_lines }) : "")
      const protectedCount = result.chapters_protected ?? 0
      setLastSmooth({ summary, protectedCount, chapterIds: vars.chapterIds })
      setSelectedIds(new Set())
      setStatusFilter("crawled")
      setReviewFilter("unreviewed")
      setCleanedFilter("cleaned")
      toast.success(summary, {
        description:
          protectedCount > 0 ? t("novel.smoothProtected", { count: protectedCount }) : t("novel.reviewHint"),
        action:
          result.chapter_ids.length > 0
            ? {
                label: t("novel.reviewFirst"),
                onClick: () => {
                  const firstId = result.chapter_ids[0]
                  const ch = chapters.find((c) => c.id === firstId)
                  setReviewingChapter({
                    id: firstId,
                    title: ch?.title ?? t("novel.chapterFallback", { id: firstId }),
                  })
                },
              }
            : undefined,
      })
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void refetch()
      void refetchExportStatus()
    },
    onError,
  })

  async function smoothForce(chapterIds?: number[]) {
    const ok = await confirm({
      title: t("novel.smoothForceTitle"),
      description: t("novel.smoothForceConfirm"),
      confirmLabel: t("novel.smoothForce"),
    })
    if (ok) smoothMutation.mutate({ chapterIds, force: true })
  }

  const sendToTranslateMutation = useMutation({
    mutationFn: (requireCleaned: boolean) =>
      crawlApi.sendToTranslate(novelId, { require_cleaned: requireCleaned, start_job: false }),
    onSuccess: (result) => {
      toast.success(t("novel.sendToTranslateOk"), {
        description:
          result.unreviewed > 0 ? t("novel.sendToTranslateUnreviewed", { count: result.unreviewed }) : undefined,
        action: {
          label: t("novel.openTranslate"),
          onClick: () => navigate(result.translate_path || `/translate/${result.work_id}`),
        },
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      navigate(result.translate_path || `/translate/${result.work_id}`)
    },
    onError,
  })

  const retryChapterMutation = useMutation({
    mutationFn: (chapterId: number) => crawlApi.retryChapter(chapterId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(result.novel_completed ? t("novel.retryOkNovel") : t("novel.retryOkChapter"))
      } else {
        toast.error(result.error ?? t("novel.retryFail"))
      }
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      // novel_completed = ghi chú "Thiếu N chương" (mục 9.2b) vừa được xoá
      // + lifecycle_status có thể vừa đổi -> cần load lại chính Novel.
      if (result.novel_completed) void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["chapters-failed-count", novelId] })
    },
    onError,
  })

  const invalidateNovel = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
    void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
    void queryClient.invalidateQueries({ queryKey: ["chapters-failed-count", novelId] })
    void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
    void queryClient.invalidateQueries({ queryKey: ["novels"] })
  }

  const retryNovelMutation = useMutation({
    mutationFn: () => crawlApi.retryNovel(novelId),
    onSuccess: () => {
      toast.message(t("novel.retryNovelQueued"))
      invalidateNovel()
    },
    onError,
  })

  const forceAcceptMutation = useMutation({
    mutationFn: () => crawlApi.forceAcceptNovel(novelId),
    onSuccess: (result) => {
      if (!result.success) {
        toast.error(result.error ?? t("lifecycle.error"))
        return
      }
      toast.message(t("site.toastForce"))
      invalidateNovel()
    },
    onError,
  })

  const deleteNovelMutation = useMutation({
    mutationFn: () => crawlApi.deleteNovel(novelId),
    onSuccess: () => {
      setConfirmDeleteNovel(false)
      toast.success(t("novel.deleteNovelOk"))
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
      if (novel?.source_key) navigate(`/sites/${novel.source_key}`)
      else navigate("/sites")
    },
    onError,
  })

  const deleteChapterMutation = useMutation({
    mutationFn: (chapterId: number) => crawlApi.deleteChapter(chapterId),
    onSuccess: () => {
      setConfirmDeleteChapterId(null)
      toast.success(t("novel.deleteChapterOk"))
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.novel(novelId) })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
    },
    onError,
  })

  const exportWorkbookMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelWorkbook(novelId),
    onSuccess: () => toast.success(t("novel.exportOk")),
    onError,
  })
  const exportTxtMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelTxt(novelId),
    onSuccess: () => toast.success(t("novel.exportTxtOk")),
    onError,
  })
  const exportEpubMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelEpub(novelId),
    onSuccess: () => toast.success(t("novel.exportEpubOk")),
    onError,
  })
  const exportBundleMutation = useMutation({
    mutationFn: () => crawlApi.exportNovelBundle(novelId),
    onSuccess: () => toast.success(t("novel.exportBundleOk")),
    onError,
  })

  const exportBusy =
    exportWorkbookMutation.isPending ||
    exportTxtMutation.isPending ||
    exportEpubMutation.isPending ||
    exportBundleMutation.isPending

  const reviewAllMutation = useMutation({
    mutationFn: () => crawlApi.reviewAllChapters(novelId),
    onSuccess: (result) => {
      if (result.chapters_reviewed > 0) {
        toast.success(t("novel.reviewAllOk", { count: result.chapters_reviewed }))
      } else {
        toast.message(t("novel.reviewAllNone"))
      }
      void queryClient.invalidateQueries({ queryKey: ["chapters", novelId] })
      void queryClient.invalidateQueries({ queryKey: ["export-status", novelId] })
    },
    onError,
  })

  function toggleOne(cid: number, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(cid)
      else next.delete(cid)
      return next
    })
  }

  function toggleAllOnPage(checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      for (const c of smoothableOnPage) {
        if (checked) next.add(c.id)
        else next.delete(c.id)
      }
      return next
    })
  }

  if (!Number.isFinite(novelId)) {
    return (
      <PageShell>
        <PageHeader
          breadcrumbs={[{ label: t("sites.title"), to: "/sites" }, { label: "?" }]}
          title={t("app.unknownError")}
          description={t("novel.invalidId")}
        />
      </PageShell>
    )
  }

  if (error) {
    return (
      <PageShell>
        <PageHeader breadcrumbs={[{ label: t("sites.title"), to: "/sites" }, { label: "?" }]} title={t("app.unknownError")} />
        <EmptyState
          icon={BookX}
          tone="neutral"
          title={error instanceof ApiError ? error.message : t("app.unknownError")}
          action={
            <Link to="/sites" className={buttonVariants({ variant: "outline" })}>
              {t("common.backSites")}
            </Link>
          }
        />
      </PageShell>
    )
  }
  if (isLoading || !novel) {
    return (
      <PageShell>
        <PageSkeleton />
      </PageShell>
    )
  }

  const crawledCount = novel.crawled_chapters ?? novel.last_chapter_index
  const crawlPct = novel.total_chapters ? (crawledCount / novel.total_chapters) * 100 : null
  const liveChapterPct =
    progress && progress.chapter_total > 0 ? (progress.chapter_index / progress.chapter_total) * 100 : null

  // ------ Hành động chính theo ngữ cảnh ------
  const sendMenuItems = (
    <>
      <ActionMenuItem disabled={sendToTranslateMutation.isPending} onSelect={() => sendToTranslateMutation.mutate(true)}>
        {t("novel.sendToTranslateCleaned")}
      </ActionMenuItem>
      <ActionMenuItem disabled={sendToTranslateMutation.isPending} onSelect={() => sendToTranslateMutation.mutate(false)}>
        {t("novel.sendToTranslateForce")}
      </ActionMenuItem>
    </>
  )

  let primaryAction: ReactNode = null
  let primaryIsRetry = false
  if (translateWorkId != null) {
    primaryAction = (
      <Link to={`/translate/${translateWorkId}`} className={buttonVariants({ variant: "default" })}>
        {t("novel.openTranslateWork")}
        <ArrowRight className="size-4" />
      </Link>
    )
  } else if (canSendToTranslate && novel.lifecycle_status !== "error") {
    primaryAction = (
      <ActionMenu
        label={
          <>
            <Send className="size-4" />
            {sendToTranslateMutation.isPending ? t("novel.sendingToTranslate") : t("novel.sendToTranslate")}
          </>
        }
        variant="default"
        size="default"
        disabled={sendToTranslateMutation.isPending}
      >
        {sendMenuItems}
      </ActionMenu>
    )
  } else if (canRetryNovel) {
    primaryIsRetry = true
    primaryAction = (
      <Button disabled={retryNovelMutation.isPending} onClick={() => retryNovelMutation.mutate()}>
        <RotateCcw className="size-4" />
        {retryNovelMutation.isPending ? t("novel.retryingNovel") : t("novel.retryNovel")}
      </Button>
    )
  } else if (novel.lifecycle_status === "rejected") {
    primaryAction = (
      <Button disabled={forceAcceptMutation.isPending} onClick={() => forceAcceptMutation.mutate()}>
        {forceAcceptMutation.isPending ? t("site.processing") : t("site.forceAccept")}
      </Button>
    )
  }
  // Lỗi nhưng vẫn gửi dịch được: "Thử lại" là chính, gửi dịch vào menu phụ.
  const sendInOverflow = canSendToTranslate && (translateWorkId != null || novel.lifecycle_status === "error")

  const secondaryActions = (
    <>
      {exportStatus?.can_export_workbook && (
        <ActionMenu
          label={
            <>
              <Download className="size-4" />
              {exportBusy ? t("novel.exporting") : t("novel.export")}
            </>
          }
          variant="outline"
          size="default"
          disabled={exportBusy}
        >
          <ActionMenuItem disabled={exportBusy} onSelect={() => exportBundleMutation.mutate()}>
            {t("novel.exportBundle")}
          </ActionMenuItem>
          <ActionMenuItem disabled={exportBusy} onSelect={() => exportWorkbookMutation.mutate()}>
            {t("novel.exportWorkbook")}
          </ActionMenuItem>
          <ActionMenuItem disabled={exportBusy} onSelect={() => exportTxtMutation.mutate()}>
            {t("novel.exportTxt")}
          </ActionMenuItem>
          <ActionMenuItem disabled={exportBusy} onSelect={() => exportEpubMutation.mutate()}>
            {t("novel.exportEpub")}
          </ActionMenuItem>
        </ActionMenu>
      )}
      {!isCrawling && (
        <ActionMenu
          label={
            <>
              <MoreHorizontal className="size-4" aria-hidden />
              <span className="sr-only">{t("novel.moreActions")}</span>
            </>
          }
          variant="outline"
          size="default"
          showChevron={false}
        >
          {sendInOverflow ? sendMenuItems : null}
          {canRetryNovel && !primaryIsRetry ? (
            <ActionMenuItem disabled={retryNovelMutation.isPending} onSelect={() => retryNovelMutation.mutate()}>
              {retryNovelMutation.isPending ? t("novel.retryingNovel") : t("novel.retryNovel")}
            </ActionMenuItem>
          ) : null}
          <ActionMenuItem destructive disabled={deleteNovelMutation.isPending} onSelect={() => setConfirmDeleteNovel(true)}>
            {t("novel.deleteNovel")}
          </ActionMenuItem>
        </ActionMenu>
      )}
    </>
  )

  // ------ Cảnh báo lỗi / bị loại ------
  const showProblem =
    Boolean(novel.error_message) ||
    novel.lifecycle_status === "error" ||
    novel.lifecycle_status === "rejected" ||
    failedChapterTotal > 0
  const problemTitle =
    novel.lifecycle_status === "rejected"
      ? t("novel.problemRejectedTitle")
      : novel.lifecycle_status === "error"
        ? t("novel.problemErrorTitle")
        : failedChapterTotal > 0
          ? t("novel.problemFailedTitle", { count: failedChapterTotal })
          : t("novel.problemNoteTitle")
  const problemExplain =
    novel.lifecycle_status === "rejected"
      ? t("novel.problemRejectedExplain")
      : novel.lifecycle_status === "error"
        ? t("novel.problemErrorExplain")
        : t("novel.failedChaptersHint", { count: failedChapterTotal })

  const stats = exportStatus && exportStatus.crawled > 0 ? exportStatus : null

  return (
    <PageShell>
      <Breadcrumbs
        items={[
          { label: t("sites.title"), to: "/sites" },
          { label: novel.source_key, to: `/sites/${novel.source_key}` },
          { label: novel.title },
        ]}
      />

      {/* ------ Đầu trang kiểu sách ------ */}
      <div className="flex flex-col gap-5 sm:flex-row sm:gap-7">
        <div className="w-28 shrink-0 sm:w-36">
          <BookCover title={novel.title} subtitle={novel.author || novel.source_key} url={novel.cover_url} lift={false} />
        </div>
        <div className="min-w-0 flex-1 space-y-4">
          <PageHeader
            eyebrow={t("sites.eyebrow")}
            stage="collect"
            title={novel.title}
            meta={
              <>
                <StatusBadge status={novel.lifecycle_status} />
                {novel.author ? <span>{novel.author}</span> : null}
                <Link
                  to={`/sites/${novel.source_key}`}
                  className="inline-flex h-6 items-center rounded-full bg-stage-collect-soft px-2.5 text-xs font-semibold text-stage-collect hover:underline"
                >
                  {novel.source_key}
                </Link>
                {novel.is_manual ? (
                  <span className="inline-flex h-6 items-center rounded-full bg-muted px-2.5 text-xs font-semibold text-muted-foreground">
                    {t("novel.manualChip")}
                  </span>
                ) : null}
              </>
            }
            secondaryActions={secondaryActions}
            primaryAction={primaryAction}
          />

          <div className="max-w-xl space-y-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px] text-muted-foreground">
              <span>{t("novel.chaptersCrawled")}</span>
              <span className="font-mono tabular-nums">
                <span className="text-foreground">{crawledCount}</span>/{novel.total_chapters ?? "?"}
                {crawlPct != null ? ` · ${Math.round(crawlPct)}%` : ""}
                {novel.failed_chapters ? (
                  <span className="text-danger">
                    {" · "}
                    {novel.failed_chapters} {t("novel.failedShort")}
                  </span>
                ) : null}
              </span>
            </div>
            <Progress
              value={crawlPct}
              tone={novel.lifecycle_status === "error" ? "danger" : "collect"}
              live={isCrawling}
              label={t("novel.chaptersCrawled")}
            />
            {isCrawling ? (
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <span aria-hidden className="dot-live size-1.5 rounded-full bg-live" />
                {progress?.chapter_total
                  ? t("novel.liveChapter", { index: progress.chapter_index, total: progress.chapter_total })
                  : progress?.message || t("novel.emptyCrawling")}
                {liveChapterPct != null ? <span className="font-mono">({Math.round(liveChapterPct)}%)</span> : null}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {/* ------ Lỗi / bị loại ------ */}
      {showProblem && (
        <Alert
          variant={novel.lifecycle_status === "rejected" ? "default" : "destructive"}
          className={cn(
            "gap-y-1.5 px-4 py-3.5 has-data-[slot=alert-action]:pr-4 sm:has-data-[slot=alert-action]:pr-72",
            novel.lifecycle_status === "rejected" ? "bg-muted/50" : "border-danger/25 bg-danger-soft",
          )}
        >
          <AlertTriangle className={novel.lifecycle_status === "rejected" ? "text-muted-foreground" : "text-danger"} />
          <AlertTitle className="text-foreground">{problemTitle}</AlertTitle>
          <AlertDescription className="space-y-2 text-foreground/80">
            <p>{problemExplain}</p>
            {novel.error_message ? (
              <p className="rounded-lg bg-card/70 px-3 py-2 font-mono text-[13px] break-words text-foreground">
                {novel.error_message}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2 pt-1 sm:hidden">{problemActions()}</div>
          </AlertDescription>
          <AlertAction className="top-3.5 right-4 hidden flex-wrap justify-end gap-2 sm:flex">{problemActions()}</AlertAction>
        </Alert>
      )}

      {/* ------ Chuẩn bị bản dịch: số liệu + bước kế tiếp + làm mượt ------ */}
      {(stats || canSmoothNovel) && (
        <section className="space-y-4 rounded-2xl border bg-card p-5 shadow-[0_1px_2px_rgb(16_22_20/0.04)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <h2 className="text-[17px] font-semibold">{t("novel.prepareTitle")}</h2>
              <p className="text-[13px] text-muted-foreground">{t("novel.smoothHint")}</p>
            </div>
            {canSmoothNovel ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={smoothMutation.isPending}
                  onClick={() => smoothMutation.mutate({})}
                  title={t("novel.smoothAllTitle")}
                >
                  <Wand2 className="size-4" />
                  {smoothMutation.isPending && selectedCount === 0 ? t("novel.smoothing") : t("novel.smoothAll")}
                </Button>
                <Button
                  variant="outline"
                  disabled={reviewAllMutation.isPending || (exportStatus?.cleaned ?? 0) === 0}
                  onClick={() => reviewAllMutation.mutate()}
                >
                  <ListChecks className="size-4" />
                  {reviewAllMutation.isPending ? t("novel.reviewingAll") : t("novel.reviewAllAction")}
                </Button>
              </div>
            ) : null}
          </div>

          {stats ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <StatMeter label={t("novel.statCrawled")} value={stats.crawled} total={novel.total_chapters ?? stats.crawled} tone="collect" />
              <StatMeter label={t("novel.statCleaned")} value={stats.cleaned} total={stats.crawled} tone="translate" />
              <StatMeter label={t("novel.statReviewed")} value={stats.reviewed} total={stats.cleaned || stats.crawled} tone="primary" />
            </div>
          ) : null}

          {pipelineStep === "smooth" && canSmoothNovel && (
            <NextStep
              icon={<Wand2 className="size-4" />}
              title={t("novel.pipelineSmoothTitle")}
              desc={t("novel.pipelineSmoothDesc", { cleaned: exportStatus?.cleaned ?? 0, crawled: exportStatus?.crawled ?? 0 })}
            >
              <Button size="sm" disabled={smoothMutation.isPending} onClick={() => smoothMutation.mutate({})}>
                {smoothMutation.isPending ? t("novel.smoothing") : t("novel.pipelineSmoothAction")}
              </Button>
            </NextStep>
          )}
          {pipelineStep === "review" && (
            <NextStep
              icon={<ListChecks className="size-4" />}
              title={t("novel.pipelineReviewTitle")}
              desc={t("novel.pipelineReviewDesc", { reviewed: exportStatus?.reviewed ?? 0, cleaned: exportStatus?.cleaned ?? 0 })}
            >
              <Button size="sm" onClick={() => void openFirstUnreviewed()}>
                {t("novel.pipelineReviewAction")}
              </Button>
            </NextStep>
          )}
          {pipelineStep === "export" && exportStatus?.can_export_workbook && (
            <NextStep icon={<Download className="size-4" />} title={t("novel.pipelineExportTitle")} desc={t("novel.pipelineExportDesc")}>
              <Button size="sm" disabled={exportBusy} onClick={() => exportBundleMutation.mutate()}>
                {exportBundleMutation.isPending ? t("novel.exporting") : t("novel.pipelineExportAction")}
              </Button>
            </NextStep>
          )}

          {lastSmooth && (
            <div className="space-y-2 rounded-xl bg-success-soft px-4 py-3 text-sm">
              <p className="flex items-center gap-2 font-medium">
                <Sparkles className="size-4 text-success" aria-hidden />
                {lastSmooth.summary}
              </p>
              {lastSmooth.protectedCount > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted-foreground">
                  <span>{t("novel.smoothProtected", { count: lastSmooth.protectedCount })}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={smoothMutation.isPending}
                    onClick={() => void smoothForce(lastSmooth.chapterIds)}
                  >
                    {t("novel.smoothForce")}
                  </Button>
                </div>
              ) : null}
            </div>
          )}
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-2 [&:empty]:hidden">
        <PipelineCard novelId={novel.id} enabled={canSendToTranslate} />
        <FollowCard novelId={novel.id} status={novel.lifecycle_status} />
      </div>

      {/* ------ Chương ------ */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[17px] font-semibold">{t("novel.chaptersTitle")}</h2>
          {total > 0 && (
            <span className="font-mono text-[13px] text-muted-foreground tabular-nums">
              {t("common.range", { from, to, total })}
              {isFetching ? " …" : ""}
            </span>
          )}
        </div>

        {/* Thanh lọc gộp: preset + tìm + lọc chi tiết */}
        <div className="space-y-3 rounded-2xl border bg-card p-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <SegmentedTabs
              value={activePreset}
              onChange={(v) => v !== "custom" && applyChapterPreset(v)}
              items={[
                { value: "all", label: t("novel.presetAll") },
                { value: "need_smooth", label: t("novel.presetNeedSmooth") },
                { value: "need_review", label: t("novel.presetNeedReview") },
                { value: "failed", label: t("novel.presetFailed"), count: failedChapterTotal > 0 ? failedChapterTotal : undefined },
                ...(activePreset === "custom" ? [{ value: "custom" as const, label: t("novel.presetCustom") }] : []),
              ]}
            />
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                placeholder={t("novel.searchChapters")}
                aria-label={t("novel.searchChapters")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-10 pl-9"
              />
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v as typeof statusFilter)}>
              <SelectTrigger className="h-9 w-full" aria-label={t("novel.colStatus")}>
                <SelectValue>{(v: string) => statusOptions.find((o) => o.value === v)?.label ?? v}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {statusOptions.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={cleanedFilter} onValueChange={(v) => v && setCleanedFilter(v as typeof cleanedFilter)}>
              <SelectTrigger className="h-9 w-full" aria-label={t("novel.colSmooth")}>
                <SelectValue>{(v: string) => cleanedOptions.find((o) => o.value === v)?.label ?? v}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {cleanedOptions.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={reviewFilter} onValueChange={(v) => v && setReviewFilter(v as typeof reviewFilter)}>
              <SelectTrigger className="h-9 w-full" aria-label={t("novel.colReview")}>
                <SelectValue>{(v: string) => reviewOptions.find((o) => o.value === v)?.label ?? v}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {reviewOptions.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Thanh chọn hàng loạt */}
        {selectedCount > 0 && canSmoothNovel && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl bg-accent px-3 py-2.5 text-sm text-accent-foreground">
            <span className="font-semibold">{t("novel.selectedCount", { count: selectedCount })}</span>
            <span className="flex-1" />
            <Button size="sm" disabled={smoothMutation.isPending} onClick={() => smoothMutation.mutate({ chapterIds: Array.from(selectedIds) })}>
              {smoothMutation.isPending ? t("novel.smoothing") : t("novel.smoothSelected")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={smoothMutation.isPending}
              onClick={() => void smoothForce(Array.from(selectedIds))}
            >
              {t("novel.smoothForce")}
            </Button>
            <Button size="sm" variant="outline" disabled={selectingAll || smoothMutation.isPending} onClick={() => void selectAllCrawledChapters()}>
              {selectingAll ? t("novel.selecting") : t("novel.selectAllPages")}
            </Button>
            <Button size="sm" variant="ghost" disabled={smoothMutation.isPending} onClick={() => setSelectedIds(new Set())}>
              {t("novel.clearSelection")}
            </Button>
          </div>
        )}

        {chaptersError && (
          <p className="text-sm text-destructive">
            {chaptersError instanceof ApiError ? chaptersError.message : t("app.unknownError")}
          </p>
        )}

        {chapters.length === 0 ? (
          <div className="rounded-2xl border border-dashed bg-card">
            <EmptyState
              compact
              icon={ListChecks}
              tone="collect"
              title={
                isCrawling && statusFilter === "all" && !debouncedSearch ? t("novel.emptyCrawling") : t("novel.emptyFilter")
              }
              action={
                activePreset !== "all" || debouncedSearch ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      applyChapterPreset("all")
                      setSearch("")
                    }}
                  >
                    {t("sites.clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <>
            {/* Mobile: thẻ */}
            <ul className="space-y-2 md:hidden">
              {chapters.map((ch) => {
                const smoothable = canSmoothChapter(ch)
                const checked = selectedIds.has(ch.id)
                return (
                  <li key={ch.id} className={cn("rounded-2xl border bg-card p-3.5", checked && "border-primary/40 bg-accent/40")}>
                    <div className="flex items-start gap-3">
                      <Checkbox
                        className="mt-1"
                        checked={checked}
                        disabled={!canSmoothNovel || !smoothable || smoothMutation.isPending}
                        onCheckedChange={(v) => toggleOne(ch.id, v === true)}
                        aria-label={t("novel.selectChapter", { index: ch.chapter_index })}
                      />
                      <div className="min-w-0 flex-1 space-y-2">
                        <p className="leading-snug font-semibold">
                          <span className="mr-1.5 font-mono text-xs text-muted-foreground">{ch.chapter_index}</span>
                          {ch.title}
                        </p>
                        <ChapterPills ch={ch} />
                        {ch.error_message ? <p className="text-[13px] break-words text-danger">{ch.error_message}</p> : null}
                      </div>
                    </div>
                    <div className="mt-2 flex justify-end">{chapterActions(ch)}</div>
                  </li>
                )
              })}
            </ul>

            {/* Desktop: bảng với header dính */}
            <div className="hidden max-h-[70vh] overflow-auto rounded-2xl border bg-card md:block">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-muted text-left text-xs font-semibold tracking-[0.06em] text-muted-foreground uppercase shadow-[0_1px_0_var(--color-border)]">
                  <tr>
                    <th className="w-10 px-3 py-3">
                      <Checkbox
                        checked={allSmoothableSelected}
                        indeterminate={someSmoothableSelected}
                        disabled={!canSmoothNovel || smoothableOnPage.length === 0 || smoothMutation.isPending}
                        onCheckedChange={(checked) => toggleAllOnPage(checked === true)}
                        aria-label={t("novel.selectAllPage")}
                      />
                    </th>
                    <th className="w-14 px-2 py-3">#</th>
                    <th className="w-[45%] px-3 py-3">{t("novel.colTitle")}</th>
                    <th className="px-3 py-3">{t("novel.colStatus")}</th>
                    <th className="px-3 py-3">{t("novel.colSmooth")}</th>
                    <th className="px-3 py-3">{t("novel.colReview")}</th>
                    <th className="px-3 py-3 text-right">{t("novel.colActions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {chapters.map((ch) => {
                    const smoothable = canSmoothChapter(ch)
                    const checked = selectedIds.has(ch.id)
                    return (
                      <tr key={ch.id} className={cn("transition-colors hover:bg-muted/40", checked && "bg-accent/40")}>
                        <td className="px-3 py-2.5">
                          <Checkbox
                            checked={checked}
                            disabled={!canSmoothNovel || !smoothable || smoothMutation.isPending}
                            onCheckedChange={(v) => toggleOne(ch.id, v === true)}
                            aria-label={t("novel.selectChapter", { index: ch.chapter_index })}
                          />
                        </td>
                        <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground tabular-nums">{ch.chapter_index}</td>
                        <td className="max-w-0 px-3 py-2.5">
                          <p className="truncate font-medium" title={ch.title}>
                            {ch.title}
                          </p>
                          {ch.error_message ? (
                            <p className="truncate text-[13px] text-danger" title={ch.error_message}>
                              {ch.error_message}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-3 py-2.5">
                          <ChapterStatusPill status={ch.status} />
                        </td>
                        <td className="px-3 py-2.5">
                          <SmoothPill ch={ch} />
                        </td>
                        <td className="px-3 py-2.5">
                          <ReviewPill ch={ch} />
                        </td>
                        <td className="px-3 py-2.5 text-right whitespace-nowrap">{chapterActions(ch)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {total > PAGE_SIZE && (
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>
              {t("common.prev")}
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((o) => o + PAGE_SIZE)}>
              {t("common.next")}
            </Button>
          </div>
        )}
      </section>

      {reviewingChapter && (
        <ChapterReviewDialog
          chapterId={reviewingChapter.id}
          chapterTitle={reviewingChapter.title}
          open={!!reviewingChapter}
          onOpenChange={(open) => !open && setReviewingChapter(null)}
          onSaved={() => {
            void refetch()
            void refetchExportStatus()
          }}
          hasNext={hasReviewNext}
          onSaveAndNext={() => goNextReview()}
        />
      )}

      <ConfirmDialog
        open={confirmDeleteNovel}
        onOpenChange={setConfirmDeleteNovel}
        title={t("common.deleteTitle")}
        description={t("novel.deleteNovelConfirm")}
        confirmLabel={t("novel.deleteNovel")}
        confirming={deleteNovelMutation.isPending}
        onConfirm={() => deleteNovelMutation.mutate()}
      />
      <ConfirmDialog
        open={confirmDeleteChapterId != null}
        onOpenChange={(open) => !open && setConfirmDeleteChapterId(null)}
        title={t("common.deleteTitle")}
        description={t("novel.deleteChapterConfirm")}
        confirmLabel={t("novel.deleteChapter")}
        confirming={deleteChapterMutation.isPending}
        onConfirm={() => {
          if (confirmDeleteChapterId != null) deleteChapterMutation.mutate(confirmDeleteChapterId)
        }}
      />
      {confirmDialog}
    </PageShell>
  )

  function problemActions() {
    if (!novel) return null
    return (
      <>
        {failedChapterTotal > 0 && (
          <Button size="sm" variant="outline" onClick={() => applyChapterPreset("failed")}>
            {t("novel.showFailed")}
          </Button>
        )}
        {novel.lifecycle_status === "rejected" && primaryAction == null ? (
          <Button size="sm" variant="outline" disabled={forceAcceptMutation.isPending} onClick={() => forceAcceptMutation.mutate()}>
            {t("site.forceAccept")}
          </Button>
        ) : null}
        {canRetryNovel && novel.lifecycle_status !== "error" && (
          <Button size="sm" variant="outline" disabled={retryNovelMutation.isPending} onClick={() => retryNovelMutation.mutate()}>
            {retryNovelMutation.isPending ? t("novel.retryingNovel") : t("novel.retryNovel")}
          </Button>
        )}
      </>
    )
  }

  function chapterActions(ch: Chapter) {
    if (!novel) return null
    const smoothable = canSmoothChapter(ch)
    const retrying = retryChapterMutation.isPending && retryChapterMutation.variables === ch.id
    const showMenu = (smoothable && canSmoothNovel) || novel.lifecycle_status !== "crawling"
    return (
      <div className="inline-flex items-center justify-end gap-1">
        {ch.status === "crawled" && (
          <Button size="sm" variant="outline" onClick={() => setReviewingChapter({ id: ch.id, title: ch.title })}>
            {t("novel.btnReview")}
          </Button>
        )}
        {(ch.status === "failed" || ch.status === "unsupported") && (
          <Button size="sm" variant="outline" disabled={retrying} onClick={() => retryChapterMutation.mutate(ch.id)}>
            <RotateCcw className="size-3.5" />
            {retrying ? t("novel.crawling") : t("novel.btnRetry")}
          </Button>
        )}
        {showMenu ? (
          <ActionMenu
            label={
              <>
                <MoreHorizontal className="size-4" aria-hidden />
                <span className="sr-only">{t("novel.moreActions")}</span>
              </>
            }
            size="sm"
            variant="ghost"
            align="end"
            showChevron={false}
          >
            {smoothable && canSmoothNovel ? (
              <>
                <ActionMenuItem disabled={smoothMutation.isPending} onSelect={() => smoothMutation.mutate({ chapterIds: [ch.id] })}>
                  {t("novel.btnSmooth")}
                </ActionMenuItem>
                {ch.reviewed ? (
                  <ActionMenuItem disabled={smoothMutation.isPending} onSelect={() => void smoothForce([ch.id])}>
                    {t("novel.smoothForce")}
                  </ActionMenuItem>
                ) : null}
              </>
            ) : null}
            {novel.lifecycle_status !== "crawling" ? (
              <ActionMenuItem
                destructive
                disabled={deleteChapterMutation.isPending && deleteChapterMutation.variables === ch.id}
                onSelect={() => setConfirmDeleteChapterId(ch.id)}
              >
                {t("novel.deleteChapter")}
              </ActionMenuItem>
            ) : null}
          </ActionMenu>
        ) : null}
      </div>
    )
  }
}

function SmoothPill({ ch }: { ch: Chapter }) {
  const t = useT()
  return ch.has_cleaned ? (
    <StatusPill status="smoothed" tone="info" label={t("novel.badgeCleaned")} live={false} />
  ) : (
    <StatusPill status="raw" tone="neutral" label={t("novel.badgeRaw")} />
  )
}

function ReviewPill({ ch }: { ch: Chapter }) {
  const t = useT()
  return ch.reviewed ? (
    <StatusPill status="reviewed" tone="success" label={t("novel.badgeReviewed")} />
  ) : (
    <StatusPill status="unreviewed" tone="neutral" label={t("novel.badgeUnreviewed")} />
  )
}

function ChapterPills({ ch }: { ch: Chapter }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <ChapterStatusPill status={ch.status} />
      <SmoothPill ch={ch} />
      <ReviewPill ch={ch} />
    </div>
  )
}

function StatMeter({
  label,
  value,
  total,
  tone,
}: {
  label: string
  value: number
  total: number
  tone: "collect" | "translate" | "primary"
}) {
  const pct = total > 0 ? (value / total) * 100 : 0
  return (
    <div className="space-y-2 rounded-xl bg-muted/50 px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">{label}</span>
        <span className="font-mono text-xl font-medium tabular-nums">
          {value}
          <span className="text-sm text-muted-foreground">/{total}</span>
        </span>
      </div>
      <Progress value={pct} tone={tone} size="sm" label={label} />
    </div>
  )
}

function NextStep({
  icon,
  title,
  desc,
  children,
}: {
  icon: ReactNode
  title: string
  desc: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/20 bg-accent/60 px-4 py-3">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-card text-accent-foreground">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-[13px] text-muted-foreground">{desc}</p>
        </div>
      </div>
      {children}
    </div>
  )
}
