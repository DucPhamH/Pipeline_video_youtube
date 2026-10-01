import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { Moon, Pause, Play, RotateCcw, RotateCw, SkipBack, SkipForward, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import { rememberListen } from "@/lib/progress"
import { formatTime } from "./formatTime"

export type Track = { segmentId: number; title: string; url: string }

type Session = { workId: number; title: string; tracks: Track[] }

type PlayerApi = {
  /** Phát danh sách chương của một sách, bắt đầu ở `index` (và giây `time`). */
  play: (session: Session, index: number, time?: number) => void
  current: { workId: number; segmentId: number } | null
  playing: boolean
  toggle: () => void
  /** Chương trước/sau trong phiên đang phát (no-op ở hai đầu). */
  prev: () => void
  next: () => void
  hasPrev: boolean
  hasNext: boolean
  /** Tua tới giây `seconds` của chương đang phát. */
  seek: (seconds: number) => void
}

export type PlayerProgress = { time: number; duration: number }

const PlayerContext = createContext<PlayerApi | null>(null)
/** Tách riêng: đổi mỗi ~250ms, chỉ thành phần cần thanh tiến độ mới đăng ký. */
const PlayerProgressContext = createContext<PlayerProgress>({ time: 0, duration: 0 })

/** Giây hiện tại + độ dài chương đang phát (0/0 khi chưa phát). */
export function usePlayerProgress(): PlayerProgress {
  return useContext(PlayerProgressContext)
}

export function usePlayer(): PlayerApi {
  const ctx = useContext(PlayerContext)
  if (!ctx) throw new Error("usePlayer cần PlayerProvider")
  return ctx
}

const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2]
const RATE_KEY = "folio.player.rate"
const SKIP_SECONDS = 15
/** Nút/ô chọn trên nền mực của thanh player. */
const INK_BTN = "text-sidebar-foreground hover:bg-sidebar-accent hover:text-white aria-expanded:bg-sidebar-accent disabled:opacity-35"
const INK_SELECT =
  "h-8 rounded-lg border border-sidebar-border bg-sidebar-surface px-2 text-xs text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-live/50 focus-visible:outline-none [&>option]:bg-sidebar"

type Sleep = { kind: "minutes"; until: number } | { kind: "chapter" } | null

function savedRate(): number {
  const n = Number(localStorage.getItem(RATE_KEY))
  return RATES.includes(n) ? n : 1
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const t = useT()
  const audioRef = useRef<HTMLAudioElement>(null)
  const pendingSeek = useRef<number | null>(null)
  const lastSaved = useRef(0)
  const [session, setSession] = useState<Session | null>(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [rate, setRate] = useState(savedRate)
  const [sleep, setSleep] = useState<Sleep>(null)
  const [nonce, setNonce] = useState(0)

  const track = session?.tracks[index] ?? null

  const save = useCallback(
    (seconds: number) => {
      if (!session || !track) return
      rememberListen({
        workId: session.workId,
        title: session.title,
        segmentId: track.segmentId,
        chapterTitle: track.title,
        time: seconds,
      })
    },
    [session, track],
  )

  const play = useCallback((next: Session, start: number, at = 0) => {
    pendingSeek.current = at > 0 ? at : null
    setSession(next)
    setIndex(Math.max(0, Math.min(start, next.tracks.length - 1)))
    setPlaying(true)
    setNonce((n) => n + 1)
  }, [])

  const toggle = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) void audio.play().catch(() => setPlaying(false))
    else audio.pause()
  }, [])

  const go = useCallback(
    (delta: number) => {
      if (!session) return
      const next = index + delta
      if (next < 0 || next >= session.tracks.length) return
      pendingSeek.current = null
      setIndex(next)
      setPlaying(true)
    },
    [index, session],
  )

  const skip = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + seconds))
  }, [])

  const close = useCallback(() => {
    audioRef.current?.pause()
    if (audioRef.current) save(audioRef.current.currentTime)
    setSession(null)
    setPlaying(false)
    setSleep(null)
  }, [save])

  // Đổi chương: nạp file mới rồi phát nếu đang ở trạng thái phát.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !track) return
    audio.playbackRate = rate
    if (pendingSeek.current != null && audio.readyState >= 1) {
      audio.currentTime = pendingSeek.current
      pendingSeek.current = null
    }
    if (playing) void audio.play().catch(() => setPlaying(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy khi đổi file hoặc gọi play()
  }, [track?.url, nonce])

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate
    localStorage.setItem(RATE_KEY, String(rate))
  }, [rate])

  useEffect(() => {
    if (!sleep || sleep.kind !== "minutes") return
    const timer = window.setInterval(() => {
      if (Date.now() >= sleep.until) {
        audioRef.current?.pause()
        setSleep(null)
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [sleep])

  useEffect(() => {
    if (!("mediaSession" in navigator)) return
    const ms = navigator.mediaSession
    if (!session || !track) {
      ms.metadata = null
      return
    }
    ms.metadata = new MediaMetadata({ title: track.title, artist: session.title, album: "Folio" })
    ms.setActionHandler("play", toggle)
    ms.setActionHandler("pause", toggle)
    ms.setActionHandler("previoustrack", () => go(-1))
    ms.setActionHandler("nexttrack", () => go(1))
    ms.setActionHandler("seekbackward", () => skip(-SKIP_SECONDS))
    ms.setActionHandler("seekforward", () => skip(SKIP_SECONDS))
  }, [session, track, toggle, go, skip])

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (!audio || !Number.isFinite(seconds)) return
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, seconds))
  }, [])
  const prev = useCallback(() => go(-1), [go])
  const next = useCallback(() => go(1), [go])
  const hasPrev = session != null && index > 0
  const hasNext = session != null && index < session.tracks.length - 1

  const api = useMemo<PlayerApi>(
    () => ({
      play,
      toggle,
      playing,
      prev,
      next,
      hasPrev,
      hasNext,
      seek,
      current: session && track ? { workId: session.workId, segmentId: track.segmentId } : null,
    }),
    [play, toggle, playing, prev, next, hasPrev, hasNext, seek, session, track],
  )
  const progress = useMemo<PlayerProgress>(
    () => (session && track ? { time, duration } : { time: 0, duration: 0 }),
    [session, track, time, duration],
  )

  const sleepLeft = sleep?.kind === "minutes" ? Math.max(0, Math.ceil((sleep.until - Date.now()) / 60000)) : null

  return (
    <PlayerContext.Provider value={api}>
      <PlayerProgressContext.Provider value={progress}>{children}</PlayerProgressContext.Provider>
      {session && track ? (
        <div
          role="region"
          aria-label={t("player.label")}
          className="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-40 border-t border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[0_-12px_32px_-18px_rgb(8_13_11/0.6)] lg:bottom-0 lg:left-[252px]"
        >
          <input
            type="range"
            aria-label={t("player.seek")}
            aria-valuetext={`${formatTime(time)} / ${formatTime(duration)}`}
            className="peer absolute inset-x-0 -top-2 z-10 h-4 w-full cursor-pointer opacity-0"
            min={0}
            max={duration || 0}
            step={1}
            value={Math.min(time, duration || 0)}
            onChange={(e) => {
              if (audioRef.current) audioRef.current.currentTime = Number(e.target.value)
            }}
          />
          {/* Range trong suốt (tua) + thanh saffron hiển thị ngay sau nó (peer → focus/hover). */}
          <div className="absolute inset-x-0 -top-px h-1 bg-sidebar-border transition-[height] peer-hover:h-1.5 peer-focus-visible:h-1.5 peer-focus-visible:ring-2 peer-focus-visible:ring-live/60" aria-hidden>
            <div
              className="h-full bg-live transition-[width] duration-200"
              style={{ width: `${duration ? Math.min(100, (time / duration) * 100) : 0}%` }}
            />
          </div>
          <div className="flex items-center gap-2 px-3 py-2.5 sm:gap-4 sm:px-5">
            <div className="min-w-0 flex-1">
              <Link
                to={`/tts/${session.workId}`}
                className="block truncate text-sm font-semibold text-white hover:underline focus-visible:ring-2 focus-visible:ring-live/60 focus-visible:outline-none"
              >
                {track.title}
              </Link>
              <p className="truncate text-xs text-sidebar-muted">
                {session.title}
                <span className="font-mono tabular-nums"> · {formatTime(time)} / {formatTime(duration)}</span>
                {sleepLeft != null ? ` · ${t("player.sleepLeft", { min: sleepLeft })}` : ""}
                {sleep?.kind === "chapter" ? ` · ${t("player.sleepChapter")}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-0.5 sm:gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className={cn(INK_BTN, "hidden sm:inline-flex")}
                aria-label={t("player.prev")}
                disabled={index === 0}
                onClick={() => go(-1)}
              >
                <SkipBack className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className={cn(INK_BTN, "hidden sm:inline-flex")}
                aria-label={t("player.back15")}
                onClick={() => skip(-SKIP_SECONDS)}
              >
                <RotateCcw className="size-4" />
              </Button>
              <button
                type="button"
                className="mx-1 inline-flex size-10 items-center justify-center rounded-full bg-live text-[#101614] shadow-[0_8px_20px_-8px_rgb(245_165_36/0.8)] transition-transform hover:scale-105 focus-visible:ring-3 focus-visible:ring-live/50 focus-visible:outline-none active:scale-95"
                aria-label={playing ? t("player.pause") : t("player.play")}
                onClick={toggle}
              >
                {playing ? <Pause className="size-4 fill-current" /> : <Play className="ml-0.5 size-4 fill-current" />}
              </button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className={cn(INK_BTN, "hidden sm:inline-flex")}
                aria-label={t("player.forward15")}
                onClick={() => skip(SKIP_SECONDS)}
              >
                <RotateCw className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className={INK_BTN}
                aria-label={t("player.next")}
                disabled={index >= session.tracks.length - 1}
                onClick={() => go(1)}
              >
                <SkipForward className="size-4" />
              </Button>
            </div>
            <div className="hidden items-center gap-2 md:flex">
              <select
                aria-label={t("player.speed")}
                className={INK_SELECT}
                value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
              >
                {RATES.map((r) => (
                  <option key={r} value={r}>
                    {r}x
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-xs text-sidebar-muted">
                <Moon className={cn("size-3.5", sleep && "text-live")} aria-hidden />
                <select
                  aria-label={t("player.sleep")}
                  className={cn(INK_SELECT, sleep && "text-live")}
                  value={sleep ? (sleep.kind === "chapter" ? "chapter" : "on") : ""}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === "") setSleep(null)
                    else if (v === "chapter") setSleep({ kind: "chapter" })
                    else if (v !== "on") setSleep({ kind: "minutes", until: Date.now() + Number(v) * 60000 })
                  }}
                >
                  <option value="">{t("player.sleepOff")}</option>
                  {sleep?.kind === "minutes" ? <option value="on">{t("player.sleepLeft", { min: sleepLeft ?? 0 })}</option> : null}
                  {[15, 30, 60].map((m) => (
                    <option key={m} value={m}>
                      {t("player.sleepMinutes", { min: m })}
                    </option>
                  ))}
                  <option value="chapter">{t("player.sleepChapter")}</option>
                </select>
              </label>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" className={INK_BTN} aria-label={t("common.close")} onClick={close}>
              <X className="size-4" />
            </Button>
          </div>
          <audio
            ref={audioRef}
            src={track.url}
            preload="auto"
            onPlay={(e) => {
              setPlaying(true)
              save(e.currentTarget.currentTime)
            }}
            onPause={() => {
              setPlaying(false)
              if (audioRef.current) save(audioRef.current.currentTime)
            }}
            onLoadedMetadata={(e) => {
              setDuration(e.currentTarget.duration)
              e.currentTarget.playbackRate = rate
              if (pendingSeek.current != null) {
                e.currentTarget.currentTime = pendingSeek.current
                pendingSeek.current = null
              }
            }}
            onTimeUpdate={(e) => {
              const now = e.currentTarget.currentTime
              setTime(now)
              if (Math.abs(now - lastSaved.current) >= 5) {
                lastSaved.current = now
                save(now)
              }
            }}
            onEnded={() => {
              if (sleep?.kind === "chapter") {
                setSleep(null)
                setPlaying(false)
                return
              }
              if (index < session.tracks.length - 1) go(1)
              else setPlaying(false)
            }}
          />
        </div>
      ) : null}
    </PlayerContext.Provider>
  )
}

/** Chừa chỗ dưới cùng để thanh player không che nội dung. */
export function usePlayerInset(): boolean {
  return usePlayer().current != null
}
