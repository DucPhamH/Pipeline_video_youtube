import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"
import {
  ArrowLeft,
  Download,
  Headphones,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RotateCcw,
  SkipBack,
  SkipForward,
  Sparkles,
  Square,
  Trash2,
  Volume2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Progress } from "@/components/ui/progress"
import { PageHeader, PageShell, SegmentedTabs } from "@/components/PageChrome"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { StatusPill } from "@/components/StatusPill"
import { useConfirm } from "@/components/useConfirm"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { cn } from "@/lib/utils"
import { translateApi } from "@/features/translate/api"
import type { AiProvider } from "@/features/translate/types"
import { useStatusLabels } from "@/features/translate/hooks/useStatusLabels"
import { usePlayer, usePlayerProgress } from "@/features/player/PlayerProvider"
import { formatTime } from "@/features/player/formatTime"
import { listenPosition } from "@/lib/progress"
import { ttsApi, type TtsCastDraft, type TtsPreset, type TtsSegment, type TtsVoice, type TtsWork } from "../api"
import { PageSkeleton } from "@/components/Skeleton"

const selectClass =
  "h-10 w-full min-w-0 rounded-[10px] border border-input bg-card px-3 text-sm focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-50"
/** Ít giọng thì hiện ô chọn (tile); nhiều thì dùng <select>. */
const MAX_VOICE_TILES = 6
const RATE_MIN = -50
const RATE_MAX = 50
const AVATAR_TINTS = [
  "bg-stage-collect-soft text-stage-collect",
  "bg-stage-write-soft text-stage-write",
  "bg-stage-translate-soft text-stage-translate",
  "bg-stage-listen-soft text-stage-listen",
]

function ratePct(rate: string): number {
  const n = Number.parseInt(rate, 10)
  return Number.isFinite(n) ? Math.max(RATE_MIN, Math.min(RATE_MAX, n)) : 0
}
function pctRate(n: number): string {
  return `${n >= 0 ? "+" : ""}${n}%`
}

/** "vi-VN-HoaiMyNeural" → "HoaiMy"; giọng khác: label từ danh sách. */
function shortVoice(id: string, voices: TtsVoice[]): string {
  if (!id) return ""
  const m = /-([A-Za-z]+?)(?:Multilingual)?Neural$/.exec(id)
  if (m) return m[1]
  return voices.find((v) => v.id === id)?.label ?? id
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  return (parts.length === 1 ? parts[0].slice(0, 1) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}
function tintFor(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return AVATAR_TINTS[h % AVATAR_TINTS.length]
}
const POLL_MS = 1500
const POLL_HIDDEN_MS = 5000
const POLL_MAX_BACKOFF_MS = 15000
const TRANSLATE_VARIANT_RE = /^translate:variant:(\d+)$/

/** Hàng cast đang sửa + key ổn định (không dùng name/index — gõ tên sẽ remount input). */
type CastRow = TtsCastDraft & { key: number }

let castKeySeq = 0
function toCastRows(members: TtsCastDraft[]): CastRow[] {
  return members.map((row) => ({ name: row.name, gender: row.gender, voice: row.voice, key: ++castKeySeq }))
}
type PreviewRef = { current: { audio: HTMLAudioElement; url: string } | null }

/** Dừng preview đang phát và thu hồi blob URL của nó. */
function releasePreview(ref: PreviewRef) {
  const cur = ref.current
  if (!cur) return
  cur.audio.pause()
  cur.audio.removeAttribute("src")
  URL.revokeObjectURL(cur.url)
  ref.current = null
}

function toCastDrafts(rows: CastRow[]): TtsCastDraft[] {
  return rows.map(({ name, gender, voice }) => ({ name, gender, voice }))
}

export function TtsWorkPage() {
  const t = useT()
  const { jobStatusLabel, segmentStatusLabel } = useStatusLabels()
  const { workId } = useParams<{ workId: string }>()
  const id = Number(workId)
  const [work, setWork] = useState<TtsWork | null>(null)
  const [segments, setSegments] = useState<TtsSegment[]>([])
  const [voices, setVoices] = useState<TtsVoice[]>([])
  const [presets, setPresets] = useState<TtsPreset[]>([])
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [vieneuReady, setVieneuReady] = useState(false)
  const [vieneuGpu, setVieneuGpu] = useState(false)
  const [device, setDevice] = useState("cpu")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [engine, setEngine] = useState("edge")
  const [presetId, setPresetId] = useState("")
  const [voice, setVoice] = useState("")
  const [dialogueVoice, setDialogueVoice] = useState("")
  const [maleVoice, setMaleVoice] = useState("")
  const [femaleVoice, setFemaleVoice] = useState("")
  const [rate, setRate] = useState("+0%")
  const [pitch, setPitch] = useState("+0Hz")
  const [volume, setVolume] = useState("+0%")
  const [style, setStyle] = useState("")
  const [useCast, setUseCast] = useState(false)
  const [providerId, setProviderId] = useState("")
  const [cast, setCast] = useState<CastRow[]>([])
  const [exporting, setExporting] = useState<string | null>(null)
  const previewRef = useRef<{ audio: HTMLAudioElement; url: string } | null>(null)
  const [castLoaded, setCastLoaded] = useState(false)
  const [cloneName, setCloneName] = useState("")
  /** null = reading mới nhất; chọn khác để xem lịch sử. */
  const [selectedReadingId, setSelectedReadingId] = useState<number | null>(null)
  const player = usePlayer()
  const progress = usePlayerProgress()
  const [confirm, confirmDialog] = useConfirm()
  const [translateLink, setTranslateLink] = useState<string | null>(null)
  const mountedRef = useRef(true)

  // Đổi work (điều hướng giữa 2 /tts/:id): reset state của work cũ ngay trong render.
  const [prevId, setPrevId] = useState(id)
  if (prevId !== id) {
    setPrevId(id)
    setWork(null)
    setSegments([])
    setLoadError(null)
    setCastLoaded(false)
    setCast([])
    setVoice("")
    setDialogueVoice("")
    setMaleVoice("")
    setFemaleVoice("")
    setPresetId("")
    setRate("+0%")
    setPitch("+0Hz")
    setVolume("+0%")
    setStyle("")
    setUseCast(false)
    setEngine("edge")
    setDevice("cpu")
    setVoices([])
    setPresets([])
    setSelectedReadingId(null)
    setTranslateLink(null)
  }

  const reading = work?.readings.find((r) => r.id === selectedReadingId) ?? work?.readings[0] ?? null
  const job = reading?.latest_job ?? null
  const jobId = job?.id
  const jobStatus = job?.status
  const active = jobStatus === "queued" || jobStatus === "running"
  const lang = work?.lang ?? ""
  const vietnamese = lang.toLowerCase().startsWith("vi")
  const vieneu = engine === "vieneu"
  const externalId = work?.external_id ?? ""

  // undefined = chưa biết (backend cũ không trả field) → không chặn nút M4B.
  const [hasFfmpeg, setHasFfmpeg] = useState<boolean | undefined>(undefined)
  useEffect(() => {
    let stale = false
    ttsApi
      .health()
      .then((h) => {
        if (!stale) setHasFfmpeg(h.ffmpeg)
      })
      .catch(() => {})
    return () => {
      stale = true
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let stale = false
    ttsApi
      .getWork(id)
      .then((next) => {
        if (!stale) setWork(next)
      })
      .catch((err) => {
        if (!stale) setLoadError(err instanceof ApiError ? err.message : t("app.unknownError"))
      })
    ttsApi
      .engines()
      .then((row) => {
        setVieneuReady(row.vieneu)
        setVieneuGpu(row.vieneu_gpu)
      })
      .catch(() => {
        setVieneuReady(false)
        setVieneuGpu(false)
      })
    translateApi
      .listAiProviders()
      .then((rows) => {
        const real = rows.filter((p) => p.kind !== "mock")
        setProviders(real)
        if (real[0]) setProviderId((cur) => cur || String(real[0].id))
      })
      .catch(() => setProviders([]))
    return () => {
      stale = true
    }
  }, [id, t])

  // Work gửi từ translate (external_id translate:variant:{id}) → tìm work dịch để link ngược.
  useEffect(() => {
    const m = TRANSLATE_VARIANT_RE.exec(externalId)
    if (!m) return
    const variantId = Number(m[1])
    let stale = false
    translateApi
      .listWorks()
      .then((list) => {
        if (stale) return
        const owner = list.items.find((w) => w.variants.some((v) => v.id === variantId))
        if (!owner) return
        const variant = owner.variants.find((v) => v.id === variantId)
        setTranslateLink(
          variant?.latest_job_id != null
            ? `/translate/${owner.id}/jobs/${variant.latest_job_id}`
            : `/translate/${owner.id}`,
        )
      })
      .catch(() => undefined)
    return () => {
      stale = true
    }
  }, [externalId])

  useEffect(() => {
    if (!work || castLoaded) return
    setCast(toCastRows(work.cast))
    setCastLoaded(true)
  }, [work, castLoaded])

  useEffect(() => {
    if (!lang) return
    // Đổi engine/lang nhanh: bỏ response của lượt cũ về muộn.
    let stale = false
    ttsApi
      .voices(lang, engine)
      .then((r) => {
        if (stale) return
        setVoices(r.voices)
        setVoice((current) => current || r.voices[0]?.id || "")
        setMaleVoice((current) => current || r.voices.find((v) => v.gender === "Male")?.id || "")
        setFemaleVoice((current) => current || r.voices.find((v) => v.gender === "Female")?.id || "")
      })
      .catch((err) => {
        if (!stale) toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
      })
    if (engine === "vieneu") {
      setPresets([])
      return () => {
        stale = true
      }
    }
    ttsApi
      .presets(lang)
      .then((rows) => {
        if (!stale) setPresets(rows)
      })
      .catch(() => {
        if (!stale) setPresets([])
      })
    return () => {
      stale = true
    }
    // id: đổi work cùng ngôn ngữ vẫn nạp lại để chọn giọng mặc định.
  }, [lang, engine, t, id])

  const stopPreview = () => releasePreview(previewRef)

  // Rời trang: dừng audio preview + thu hồi blob URL.
  useEffect(() => () => releasePreview(previewRef), [])

  // Tải segment khi đổi job / job đổi trạng thái (kể cả khi đã dừng).
  useEffect(() => {
    if (jobId == null) return
    let stop = false
    ttsApi
      .segments(jobId)
      .then((rows) => {
        if (!stop) setSegments(rows)
      })
      .catch(() => undefined)
    return () => {
      stop = true
    }
  }, [jobId, jobStatus])

  // Poll tự lên lịch (setTimeout) chỉ khi job đang chạy: không chồng request,
  // chậm lại khi tab ẩn, backoff khi lỗi liên tiếp — giống TranslateJobPage.
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
      try {
        const [next, rows] = await Promise.all([ttsApi.getWork(id), ttsApi.segments(jobId)])
        if (cancelled) return
        failures = 0
        setWork(next)
        setSegments(rows)
      } catch {
        if (cancelled) return
        failures += 1
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
    }
  }, [jobId, active, id])

  function applyPreset(nextId: string) {
    setPresetId(nextId)
    const preset = presets.find((p) => p.id === nextId)
    if (!preset) return
    setVoice(preset.voice)
    setDialogueVoice(preset.dialogue_voice)
    setRate(preset.rate)
    setPitch(preset.pitch)
    setVolume(preset.volume)
    setStyle(preset.style)
  }

  function changeEngine(next: string) {
    setEngine(next)
    setPresetId("")
    setVoice("")
    setDialogueVoice("")
    setMaleVoice("")
    setFemaleVoice("")
    setStyle("")
    setDevice("cpu")
  }

  function updateCast(key: number, patch: Partial<TtsCastDraft>) {
    setCast((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  async function handleDetect() {
    if (!work || !providerId) {
      toast.error(t("tts.detectNeedProvider"))
      return
    }
    setBusy(true)
    try {
      const next = await ttsApi.detectCast(work.id, Number(providerId))
      setWork(next)
      setCast(toCastRows(next.cast))
      setUseCast(true)
      toast.success(t("tts.castDetected"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveCast() {
    if (!work) return
    setBusy(true)
    try {
      const next = await ttsApi.saveCast(work.id, toCastDrafts(cast))
      setWork(next)
      setCast(toCastRows(next.cast))
      toast.success(t("tts.castSaved"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleClone(file: File | null) {
    if (!file) return
    setBusy(true)
    try {
      await ttsApi.cloneVoice(file, cloneName)
      const listed = await ttsApi.voices(lang || "vi", "vieneu")
      setVoices(listed.voices)
      toast.success(t("tts.cloneOk"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleStart() {
    if (!work || !voice) return
    if (useCast && !providerId) {
      toast.error(t("tts.detectNeedProvider"))
      return
    }
    setBusy(true)
    try {
      if (useCast) {
        const saved = await ttsApi.saveCast(work.id, toCastDrafts(cast))
        setWork(saved)
        setCast(toCastRows(saved.cast))
      }
      const next = await ttsApi.startReading(work.id, {
        engine,
        voice,
        dialogue_voice: useCast ? "" : dialogueVoice,
        rate,
        pitch,
        volume,
        style,
        device: vieneu ? device : "cpu",
        preset_id: presetId,
        male_voice: maleVoice,
        female_voice: femaleVoice,
        use_cast: useCast,
        provider_id: useCast ? Number(providerId) : null,
      })
      setWork(next)
      setSelectedReadingId(null)
      toast.success(t("tts.started"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handlePreview() {
    if (!work || !voice) return
    setBusy(true)
    try {
      const url = await ttsApi.preview({
        engine,
        voice,
        lang: work.lang,
        rate,
        pitch,
        volume,
        style,
        device: vieneu ? device : "cpu",
      })
      // Rời trang khi đang chờ preview → bỏ audio, thu hồi blob ngay.
      if (!mountedRef.current) {
        URL.revokeObjectURL(url)
        return
      }
      stopPreview()
      const audio = new Audio(url)
      previewRef.current = { audio, url }
      audio.addEventListener("ended", () => {
        if (previewRef.current?.audio === audio) stopPreview()
      })
      await audio.play()
    } catch (err) {
      if (mountedRef.current) toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  /** Chặn bấm export 2 lần khi file đang dựng/tải. */
  async function runExport(kind: string, fn: () => Promise<void>) {
    if (exporting) return
    setExporting(kind)
    try {
      await fn()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) toast.error(t("tts.exportBusy"))
      else toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setExporting(null)
    }
  }

  async function handleResume() {
    if (!job) return
    setBusy(true)
    try {
      await ttsApi.resume(job.id)
      const next = await ttsApi.getWork(id)
      setWork(next)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel() {
    if (!job) return
    const ok = await confirm({
      title: t("tts.cancelConfirmTitle"),
      description: t("tts.cancelConfirmBody"),
      confirmLabel: t("tts.cancel"),
    })
    if (!ok || !mountedRef.current) return
    setBusy(true)
    try {
      await ttsApi.cancel(job.id)
      const next = await ttsApi.getWork(id)
      setWork(next)
      toast.message(t("tts.cancelled"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  const jobSegments = job ? segments.filter((seg) => seg.job_id === job.id) : []
  const playable = jobSegments.filter((seg) => seg.has_audio)
  const resumeAt = work ? listenPosition(work.id) : undefined

  function playFrom(segmentId: number, time = 0) {
    if (!work) return
    const at = playable.findIndex((seg) => seg.id === segmentId)
    player.play(
      {
        workId: work.id,
        title: work.title,
        tracks: playable.map((seg) => ({ segmentId: seg.id, title: seg.title, url: ttsApi.audioUrl(seg.id) })),
      },
      Math.max(0, at),
      time,
    )
  }
  const progressPct =
    job && job.total_segments > 0 ? Math.round((job.done_segments / job.total_segments) * 100) : 0
  const canExport = reading != null && job != null && !active && job.done_segments > 0

  const selected = voices.find((v) => v.id === voice)
  const styles = selected?.styles ?? []
  const voiceOptions = voices.map((v) => (
    <option key={v.id} value={v.id}>
      {v.label} · {v.gender}
    </option>
  ))
  const genderLabel = (g: string) =>
    g.toLowerCase() === "male" ? t("tts.genderMale") : g.toLowerCase() === "female" ? t("tts.genderFemale") : g

  if (loadError) {
    return (
      <PageShell>
        <PageHeader breadcrumbs={[{ label: t("tts.title"), to: "/tts" }, { label: "—" }]} title={t("tts.title")} />
        <p className="text-sm text-destructive">{loadError}</p>
      </PageShell>
    )
  }
  if (!work) {
    return (
      <PageShell>
        <PageSkeleton />
      </PageShell>
    )
  }

  const thisWorkPlaying = player.current?.workId === work.id
  const currentSeg = thisWorkPlaying ? playable.find((seg) => seg.id === player.current?.segmentId) : undefined
  const resumeSeg = resumeAt ? playable.find((seg) => seg.id === resumeAt.segmentId) : undefined
  const cardSeg = currentSeg ?? resumeSeg ?? playable[0]
  const chapterName = (seg: TtsSegment) => t("tts.chapterNo", { n: seg.chapter_index })
  const cardEyebrow = cardSeg
    ? t(currentSeg ? (player.playing ? "tts.nowPlayingEyebrow" : "tts.pausedEyebrow") : "tts.upNextEyebrow", {
        chapter: chapterName(cardSeg),
      })
    : t("tts.noAudioTitle")
  const summarySource = job ?? { voice, dialogue_voice: dialogueVoice, rate, use_cast: useCast }
  const voiceSummary = [
    t("tts.voiceNarrator", { voice: shortVoice(summarySource.voice, voices) }),
    summarySource.use_cast
      ? t("tts.voiceByCharacter")
      : summarySource.dialogue_voice
        ? t("tts.voiceDialogue", { voice: shortVoice(summarySource.dialogue_voice, voices) })
        : null,
    `${(1 + ratePct(summarySource.rate) / 100).toFixed(2)}×`,
  ]
    .filter(Boolean)
    .join(" · ")

  function playCard() {
    if (currentSeg) player.toggle()
    else if (resumeAt && resumeSeg) playFrom(resumeSeg.id, resumeAt.time)
    else if (playable[0]) playFrom(playable[0].id)
  }

  const failedOrCancelled = job != null && (job.status === "failed" || job.status === "cancelled")
  const startDisabled = busy || active || !voice || (vieneu && !vieneuReady)
  const readyCount = job?.done_segments ?? 0
  const totalCount = job?.total_segments ?? work.chapters.length

  const primaryAction = active ? (
    <Button type="button" variant="destructive" disabled={busy} onClick={() => void handleCancel()}>
      <Square className="fill-current" aria-hidden />
      {t("tts.cancel")}
    </Button>
  ) : failedOrCancelled ? (
    <Button type="button" disabled={busy} onClick={() => void handleResume()}>
      <RotateCcw aria-hidden />
      {t("tts.resume")}
    </Button>
  ) : (
    <Button type="button" disabled={startDisabled} onClick={() => void handleStart()}>
      <Play className="fill-current" aria-hidden />
      {t("tts.readAll")}
    </Button>
  )

  const m4bBlocked = hasFfmpeg === false
  const secondaryActions = (
    <>
      {job ? (
        <>
          <Button
            type="button"
            variant="outline"
            disabled={!canExport || exporting != null}
            onClick={() => reading && void runExport("zip", () => ttsApi.exportZip(reading.id))}
          >
            <Download aria-hidden />
            {exporting === "zip" ? t("tts.exporting") : "ZIP"}
          </Button>
          {/* span giữ tooltip khi nút bị tắt (nút disabled không nhận hover). */}
          <span title={m4bBlocked ? t("tts.m4bNeedsFfmpeg") : undefined} className="inline-flex">
            <Button
              type="button"
              variant="outline"
              disabled={!canExport || exporting != null || m4bBlocked}
              aria-describedby={m4bBlocked ? "tts-m4b-hint" : undefined}
              onClick={() => reading && void runExport("m4b", () => ttsApi.exportM4b(reading.id))}
            >
              <Download aria-hidden />
              {exporting === "m4b" ? t("tts.exporting") : t("tts.exportM4b")}
            </Button>
          </span>
          {m4bBlocked ? (
            <span id="tts-m4b-hint" className="sr-only">
              {t("tts.m4bNeedsFfmpeg")}
            </span>
          ) : null}
        </>
      ) : null}
      {(failedOrCancelled || (resumeSeg && playable.length > 0)) ? (
        <ActionMenu
          label={<MoreHorizontal className="size-4" aria-label={t("tts.moreActions")} />}
          variant="ghost"
          size="default"
          showChevron={false}
        >
          {resumeSeg && playable.length > 0 ? (
            <ActionMenuItem onSelect={() => playFrom(playable[0].id)}>{t("tts.listenFromStart")}</ActionMenuItem>
          ) : null}
          {failedOrCancelled ? (
            <ActionMenuItem disabled={startDisabled} onSelect={() => void handleStart()}>
              {t("tts.readAgain")}
            </ActionMenuItem>
          ) : null}
        </ActionMenu>
      ) : null}
    </>
  )

  const voiceTiles = voices.length > 0 && voices.length <= MAX_VOICE_TILES

  return (
    <PageShell>
      {confirmDialog}
      <PageHeader
        breadcrumbs={[{ label: t("tts.title"), to: "/tts" }, { label: work.title }]}
        eyebrow={t("tts.eyebrow")}
        stage="listen"
        title={work.title}
        meta={
          <>
            {work.author ? <span>{work.author}</span> : null}
            <span className="font-mono uppercase">{work.lang}</span>
            <span className="font-mono tabular-nums">
              {work.chapters.length} {t("tts.chaptersShort")}
            </span>
            {translateLink ? (
              <Link to={translateLink} className="font-medium text-accent-foreground hover:underline dark:text-primary">
                {t("tts.backToTranslate")}
              </Link>
            ) : null}
          </>
        }
        secondaryActions={secondaryActions}
        primaryAction={primaryAction}
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          {/* Now playing */}
          <section
            aria-label={cardEyebrow}
            className="rise flex flex-col gap-5 rounded-[20px] bg-sidebar p-5 text-white sm:flex-row sm:items-center sm:gap-6 sm:p-6"
          >
            <div className="flex items-center gap-4 sm:block">
              <div className="w-20 shrink-0 sm:w-28">
                <BookCover title={work.title} subtitle={work.author || work.lang} lift={false} />
              </div>
            </div>
            <div className="min-w-0 flex-1 space-y-4">
              <div>
                <p className="text-xs font-semibold tracking-[0.1em] text-live uppercase">
                  {currentSeg && player.playing ? <span className="dot-live mr-2 inline-block size-1.5 rounded-full bg-live align-middle" aria-hidden /> : null}
                  {cardEyebrow}
                </p>
                <h2 className="mt-1.5 font-display text-[24px] leading-tight font-semibold text-balance sm:text-[28px]">
                  {cardSeg ? cardSeg.title : work.title}
                </h2>
                <p className="mt-1 text-[13px] text-sidebar-foreground">
                  {cardSeg ? voiceSummary : t("tts.noAudioHint")}
                </p>
              </div>
              {currentSeg ? (
                <div className="space-y-1.5">
                  <input
                    type="range"
                    aria-label={t("player.seek")}
                    aria-valuetext={`${formatTime(progress.time)} / ${formatTime(progress.duration)}`}
                    className="h-1.5 w-full cursor-pointer accent-live"
                    min={0}
                    max={progress.duration || 0}
                    step={1}
                    value={Math.min(progress.time, progress.duration || 0)}
                    onChange={(e) => player.seek(Number(e.target.value))}
                  />
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-3 sm:gap-3.5">
                <button
                  type="button"
                  aria-label={t("player.prev")}
                  disabled={!currentSeg || !player.hasPrev}
                  onClick={player.prev}
                  className="inline-flex size-10 items-center justify-center rounded-full border border-sidebar-border bg-sidebar-surface text-white transition-colors hover:bg-sidebar-accent focus-visible:ring-3 focus-visible:ring-live/50 focus-visible:outline-none disabled:opacity-35"
                >
                  <SkipBack className="size-4" />
                </button>
                <button
                  type="button"
                  aria-label={currentSeg && player.playing ? t("player.pause") : t("player.play")}
                  disabled={!cardSeg}
                  onClick={playCard}
                  className="inline-flex size-13 items-center justify-center rounded-full bg-live text-[#101614] shadow-[0_8px_20px_-8px_rgb(245_165_36/0.8)] transition-transform hover:scale-105 focus-visible:ring-3 focus-visible:ring-live/50 focus-visible:outline-none active:scale-95 disabled:opacity-40 disabled:hover:scale-100"
                >
                  {currentSeg && player.playing ? (
                    <Pause className="size-5 fill-current" />
                  ) : (
                    <Play className="ml-0.5 size-5 fill-current" />
                  )}
                </button>
                <button
                  type="button"
                  aria-label={t("player.next")}
                  disabled={!currentSeg || !player.hasNext}
                  onClick={player.next}
                  className="inline-flex size-10 items-center justify-center rounded-full border border-sidebar-border bg-sidebar-surface text-white transition-colors hover:bg-sidebar-accent focus-visible:ring-3 focus-visible:ring-live/50 focus-visible:outline-none disabled:opacity-35"
                >
                  <SkipForward className="size-4" />
                </button>
                <span className="font-mono text-[13px] text-sidebar-foreground tabular-nums">
                  {currentSeg
                    ? `${formatTime(progress.time)} / ${formatTime(progress.duration)}`
                    : resumeSeg && resumeAt
                      ? t("tts.resumeListen", { chapter: resumeAt.chapterTitle })
                      : null}
                </span>
              </div>
            </div>
          </section>

          {/* Chapters */}
          <section className="space-y-3" aria-labelledby="tts-chapters">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="flex items-baseline gap-3">
                <h2 id="tts-chapters" className="font-display text-xl font-semibold">
                  {t("tts.chapters")}
                </h2>
                {job ? (
                  <span className="text-[13px] text-muted-foreground">
                    <span className="font-mono tabular-nums">{t("tts.readyOf", { done: readyCount, total: totalCount })}</span>
                    {job.failed_segments ? (
                      <span className="text-destructive">
                        {" "}
                        · {job.failed_segments} {t("tts.failShort")}
                      </span>
                    ) : null}
                  </span>
                ) : null}
              </div>
              <div className="flex flex-1 flex-wrap items-center gap-3 sm:justify-end">
                {work.readings.length > 1 ? (
                  <label className="flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground">
                    <span className="shrink-0">{t("tts.readingPick")}</span>
                    <select
                      className={cn(selectClass, "h-9 max-w-64 text-[13px]")}
                      aria-describedby="tts-history-hint"
                      value={reading?.id ?? ""}
                      onChange={(e) => setSelectedReadingId(Number(e.target.value))}
                    >
                      {work.readings.map((r) => (
                        <option key={r.id} value={r.id}>
                          #{r.id} · {r.engine} · {shortVoice(r.voice, voices)} · {jobStatusLabel(r.latest_job?.status ?? r.status)}
                          {r.latest_job ? ` · ${r.latest_job.done_segments}/${r.latest_job.total_segments}` : ""}
                        </option>
                      ))}
                    </select>
                    <span id="tts-history-hint" className="sr-only">
                      {t("tts.historyHint")}
                    </span>
                  </label>
                ) : null}
                {job ? (
                  <Progress
                    className="w-full sm:w-56"
                    tone={job.status === "failed" ? "danger" : "listen"}
                    live={active}
                    value={progressPct}
                    label={t("tts.readyOf", { done: readyCount, total: totalCount })}
                  />
                ) : null}
              </div>
            </div>
            {job?.error ? <p className="text-sm text-destructive">{job.error}</p> : null}
            {job && job.status !== "completed" && job.done_segments > 0 && !active ? (
              <p className="text-[13px] text-muted-foreground">{t("tts.partialExportHint")}</p>
            ) : null}

            {job && jobSegments.length > 0 ? (
              <ul className="stagger space-y-2">
                {jobSegments.map((seg) => {
                  const isCurrent = player.current?.segmentId === seg.id
                  const isPlaying = isCurrent && player.playing
                  const done = seg.status === "done" || seg.status === "skipped_cache"
                  return (
                    <li
                      key={seg.id}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors sm:gap-4 sm:px-4",
                        isCurrent ? "border-stage-listen/40 bg-stage-listen-soft" : "border-border bg-card",
                      )}
                    >
                      <button
                        type="button"
                        disabled={!seg.has_audio}
                        aria-pressed={isCurrent}
                        aria-label={t(isPlaying ? "tts.pauseChapter" : "tts.playChapter", { chapter: seg.title })}
                        onClick={() => (isCurrent ? player.toggle() : playFrom(seg.id))}
                        className={cn(
                          "inline-flex size-9 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-40",
                          isCurrent
                            ? "bg-stage-listen text-white"
                            : "bg-muted text-foreground hover:bg-stage-listen-soft hover:text-stage-listen",
                        )}
                      >
                        {isPlaying ? <Pause className="size-4 fill-current" /> : <Play className="ml-0.5 size-4 fill-current" />}
                      </button>
                      <span className="w-7 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                        {String(seg.chapter_index).padStart(2, "0")}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{seg.title}</p>
                        {seg.error ? <p className="truncate text-xs text-destructive" title={seg.error}>{seg.error}</p> : null}
                      </div>
                      <span className="hidden font-mono text-[13px] text-muted-foreground tabular-nums sm:inline">
                        {isCurrent && progress.duration ? formatTime(progress.duration) : "—"}
                      </span>
                      {isCurrent ? (
                        <StatusPill status="running" tone="warning" live={isPlaying} label={t("tts.nowPlaying")} />
                      ) : (
                        <StatusPill
                          status={done ? "ready" : seg.status === "running" ? "speaking" : seg.status}
                          label={segmentStatusLabel(seg.status)}
                        />
                      )}
                    </li>
                  )
                })}
              </ul>
            ) : job ? (
              <div className="rounded-2xl border border-border bg-card">
                <PageSkeleton />
              </div>
            ) : work.chapters.length > 0 ? (
              <ul className="stagger space-y-2">
                {work.chapters.map((ch) => (
                  <li key={ch.index} className="flex items-center gap-3 rounded-xl border border-border bg-card px-3 py-2.5 sm:gap-4 sm:px-4">
                    <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground opacity-50" aria-hidden>
                      <Play className="ml-0.5 size-4 fill-current" />
                    </span>
                    <span className="w-7 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                      {String(ch.index).padStart(2, "0")}
                    </span>
                    <p className="min-w-0 flex-1 truncate text-sm font-semibold">{ch.title || t("tts.chapterNo", { n: ch.index })}</p>
                    <StatusPill status="idle" label={t("tts.notStarted")} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-2xl border border-border bg-card">
                <EmptyState icon={Headphones} tone="listen" compact title={t("tts.noAudioTitle")} hint={t("tts.noAudioHint")} />
              </div>
            )}
          </section>
        </div>

        {/* Right column */}
        <aside className="min-w-0 space-y-4">
          <section className="space-y-4 rounded-2xl border border-border bg-card p-5" aria-labelledby="tts-voice-title">
            <div className="flex items-center gap-3">
              <h3 id="tts-voice-title" className="text-[17px] font-semibold">
                {t("tts.readSettings")}
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="ml-auto"
                disabled={busy || !voice || (vieneu && !vieneuReady)}
                onClick={() => void handlePreview()}
              >
                <Volume2 aria-hidden />
                {t("tts.preview")}
              </Button>
            </div>
            <p className="text-[13px] text-muted-foreground">{t("tts.readHint")}</p>

            <div className="space-y-1.5">
              <p className="text-[13px] font-semibold" id="tts-engine-label">
                {t("tts.engine")}
              </p>
              <SegmentedTabs
                value={engine}
                onChange={changeEngine}
                className="flex w-full [&>button]:flex-1 [&>button]:justify-center"
                items={[
                  { value: "edge", label: "Edge" },
                  ...(vietnamese ? [{ value: "vieneu", label: "VieNeu" }] : []),
                  { value: "mock", label: "Mock" },
                ]}
              />
            </div>

            {vieneu ? (
              <div className="space-y-1.5">
                <Label htmlFor="tts-device">{t("tts.device")}</Label>
                <select id="tts-device" className={selectClass} value={device} onChange={(e) => setDevice(e.target.value)}>
                  <option value="cpu">{t("tts.deviceCpu")}</option>
                  <option value="gpu" disabled={!vieneuGpu}>
                    {t("tts.deviceGpu")}
                  </option>
                </select>
                <p className="text-xs text-muted-foreground">{t("tts.deviceHint")}</p>
                {!vieneuGpu ? <p className="text-xs text-muted-foreground">{t("tts.deviceGpuMissing")}</p> : null}
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="tts-preset">{t("tts.preset")}</Label>
                <select id="tts-preset" className={selectClass} value={presetId} onChange={(e) => applyPreset(e.target.value)}>
                  <option value="">{t("tts.presetCustom")}</option>
                  {presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {t(`tts.preset_${p.id}`)}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="space-y-1.5">
              {voiceTiles ? (
                <>
                  <p className="text-[13px] font-semibold" id="tts-narrator-label">
                    {t("tts.narrator")}
                  </p>
                  <div role="radiogroup" aria-labelledby="tts-narrator-label" className="grid grid-cols-2 gap-2">
                    {voices.map((v) => {
                      const on = v.id === voice
                      return (
                        <button
                          key={v.id}
                          type="button"
                          role="radio"
                          aria-checked={on}
                          title={v.label}
                          onClick={() => setVoice(v.id)}
                          className={cn(
                            "min-w-0 rounded-xl border px-3 py-2.5 text-left transition-colors focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none",
                            on
                              ? "border-stage-listen bg-stage-listen-soft ring-1 ring-stage-listen"
                              : "border-border bg-card hover:bg-muted",
                          )}
                        >
                          <span className="block truncate text-sm font-semibold">{shortVoice(v.id, voices)}</span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {genderLabel(v.gender)} · {v.locale}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </>
              ) : (
                <>
                  <Label htmlFor="tts-voice">{t("tts.narrator")}</Label>
                  <select id="tts-voice" className={selectClass} value={voice} onChange={(e) => setVoice(e.target.value)}>
                    <option value="" disabled>
                      {t("tts.voicePick")}
                    </option>
                    {voiceOptions}
                  </select>
                </>
              )}
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="tts-rate">{t("tts.speed")}</Label>
                <span className="font-mono text-[13px] text-muted-foreground tabular-nums">
                  {vieneu ? "1.00×" : `${(1 + ratePct(rate) / 100).toFixed(2)}× · ${rate}`}
                </span>
              </div>
              <input
                id="tts-rate"
                type="range"
                className="w-full cursor-pointer accent-stage-listen disabled:cursor-not-allowed disabled:opacity-50"
                min={RATE_MIN}
                max={RATE_MAX}
                step={5}
                disabled={vieneu}
                value={ratePct(rate)}
                aria-valuetext={`${(1 + ratePct(rate) / 100).toFixed(2)}×`}
                onChange={(e) => setRate(pctRate(Number(e.target.value)))}
              />
              {vieneu ? <p className="text-xs text-muted-foreground">{t("tts.speedFixed")}</p> : null}
            </div>

            {useCast ? null : (
              <div className="space-y-2">
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>{t("tts.dialogueToggle")}</span>
                  <Switch
                    checked={dialogueVoice !== ""}
                    onCheckedChange={(on) =>
                      setDialogueVoice(on ? (voices.find((v) => v.id !== voice)?.id ?? voice) : "")
                    }
                  />
                </label>
                {dialogueVoice !== "" ? (
                  <select
                    aria-label={t("tts.dialogue")}
                    className={selectClass}
                    value={dialogueVoice}
                    onChange={(e) => setDialogueVoice(e.target.value)}
                  >
                    {voiceOptions}
                  </select>
                ) : null}
              </div>
            )}

            {vieneu ? null : (
              <details className="group rounded-xl border border-border px-3 py-2.5">
                <summary className="flex cursor-pointer items-center gap-2 text-[13px] font-semibold select-none marker:content-none">
                  {t("tts.advanced")}
                  <span className="ml-auto truncate font-mono text-xs font-normal text-muted-foreground">
                    {[pitch, volume, style || t("tts.styleOff")].join(" · ")}
                  </span>
                </summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                  <div className="space-y-1.5">
                    <Label htmlFor="tts-pitch">{t("tts.pitch")}</Label>
                    <select id="tts-pitch" className={selectClass} value={pitch} onChange={(e) => setPitch(e.target.value)}>
                      {["-10Hz", "+0Hz", "+5Hz", "+10Hz"].map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tts-volume">{t("tts.volume")}</Label>
                    <select id="tts-volume" className={selectClass} value={volume} onChange={(e) => setVolume(e.target.value)}>
                      {["-10%", "+0%", "+10%"].map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tts-style">{t("tts.style")}</Label>
                    <select id="tts-style" className={selectClass} value={style} onChange={(e) => setStyle(e.target.value)}>
                      <option value="">{t("tts.styleOff")}</option>
                      {styles.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </details>
            )}

            {vieneu && !vieneuReady ? <p className="text-sm text-destructive">{t("tts.vieneuMissing")}</p> : null}
            {vieneu && vieneuReady ? (
              <div className="space-y-1.5 rounded-xl border border-dashed border-border p-3">
                <Label htmlFor="tts-clone-name">{t("tts.cloneTitle")}</Label>
                <div className="flex gap-2">
                  <input
                    id="tts-clone-name"
                    className={selectClass}
                    placeholder={t("tts.cloneName")}
                    value={cloneName}
                    onChange={(e) => setCloneName(e.target.value)}
                  />
                  <label className="inline-flex h-10 shrink-0 cursor-pointer items-center rounded-[10px] border border-input bg-card px-3 text-sm font-semibold hover:bg-muted focus-within:ring-3 focus-within:ring-ring/40">
                    {t("tts.cloneSave")}
                    <input
                      className="sr-only"
                      type="file"
                      accept="audio/wav,audio/mpeg,audio/mp3,.wav,.mp3"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0] ?? null
                        e.target.value = ""
                        void handleClone(file)
                      }}
                    />
                  </label>
                </div>
                <p className="text-xs text-muted-foreground">{t("tts.cloneHint")}</p>
              </div>
            ) : null}
          </section>

          <section className="space-y-4 rounded-2xl border border-border bg-card p-5" aria-labelledby="tts-cast-title">
            <div className="flex items-center gap-3">
              <h3 id="tts-cast-title" className="text-[17px] font-semibold">
                {t("tts.castTitle")}
              </h3>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="ml-auto"
                disabled={busy || active}
                onClick={() => void handleDetect()}
              >
                <Sparkles aria-hidden />
                {t("tts.detect")}
              </Button>
            </div>
            <p className="text-[13px] text-muted-foreground">{t("tts.castHint")}</p>
            <div className="space-y-1.5">
              <Label htmlFor="tts-provider">{t("tts.castProvider")}</Label>
              <select id="tts-provider" className={selectClass} value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                <option value="">{t("tts.pickAi")}</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center justify-between gap-3 text-sm font-medium">
              <span>{t("tts.useCast")}</span>
              <Switch checked={useCast} onCheckedChange={(on) => setUseCast(on)} />
            </label>
            {useCast ? (
              <div className="grid grid-cols-2 gap-2">
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="tts-male">{t("tts.maleVoice")}</Label>
                  <select id="tts-male" className={selectClass} value={maleVoice} onChange={(e) => setMaleVoice(e.target.value)}>
                    <option value="">{t("tts.voiceDefault")}</option>
                    {voiceOptions}
                  </select>
                </div>
                <div className="min-w-0 space-y-1.5">
                  <Label htmlFor="tts-female">{t("tts.femaleVoice")}</Label>
                  <select
                    id="tts-female"
                    className={selectClass}
                    value={femaleVoice}
                    onChange={(e) => setFemaleVoice(e.target.value)}
                  >
                    <option value="">{t("tts.voiceDefault")}</option>
                    {voiceOptions}
                  </select>
                </div>
              </div>
            ) : null}

            {cast.length === 0 ? (
              <p className="border-t border-border pt-3 text-sm text-muted-foreground">{t("tts.castEmpty")}</p>
            ) : (
              <ul className="divide-y divide-border border-t border-border">
                {cast.map((row) => (
                  <li key={row.key} className="flex items-start gap-3 py-3">
                    <span
                      aria-hidden
                      className={cn(
                        "mt-1 inline-flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                        tintFor(row.name),
                      )}
                    >
                      {initials(row.name)}
                    </span>
                    <div className="grid min-w-0 flex-1 gap-1.5">
                      <input
                        className="h-8 w-full min-w-0 rounded-md border border-transparent bg-transparent px-1.5 text-sm font-semibold hover:border-input focus-visible:border-input focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
                        aria-label={t("tts.castName")}
                        value={row.name}
                        onChange={(e) => updateCast(row.key, { name: e.target.value })}
                      />
                      <div className="grid grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)] gap-1.5">
                        <select
                          className={cn(selectClass, "h-8 px-2 text-xs")}
                          aria-label={t("tts.castGender")}
                          value={row.gender}
                          onChange={(e) => updateCast(row.key, { gender: e.target.value })}
                        >
                          <option value="male">{t("tts.genderMale")}</option>
                          <option value="female">{t("tts.genderFemale")}</option>
                          <option value="unknown">{t("tts.genderUnknown")}</option>
                        </select>
                        <select
                          className={cn(selectClass, "h-8 px-2 text-xs")}
                          aria-label={t("tts.castVoice")}
                          value={row.voice}
                          onChange={(e) => updateCast(row.key, { voice: e.target.value })}
                        >
                          <option value="">{t("tts.castVoiceDefault")}</option>
                          {voiceOptions}
                        </select>
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="mt-0.5 text-muted-foreground hover:text-destructive"
                      aria-label={`${t("tts.castRemove")} ${row.name}`.trim()}
                      onClick={() => setCast((rows) => rows.filter((r) => r.key !== row.key))}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy || active}
                onClick={() => setCast((rows) => [...rows, { name: "", gender: "unknown", voice: "", key: ++castKeySeq }])}
              >
                <Plus aria-hidden />
                {t("tts.castAdd")}
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={busy || active} onClick={() => void handleSaveCast()}>
                {t("tts.castSave")}
              </Button>
            </div>
          </section>

          <Link
            to="/tts"
            className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            {t("tts.title")}
          </Link>
        </aside>
      </div>
    </PageShell>
  )
}
