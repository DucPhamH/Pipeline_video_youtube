import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import { AlertCircle, BookOpen, Headphones, ListTree, PenLine, Save, Sparkles, Square } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { StatusPill } from "@/components/StatusPill"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader, PageShell, SectionCard } from "@/components/PageChrome"
import { cn } from "@/lib/utils"
import { useConfirm } from "@/components/useConfirm"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "@/features/translate/api"
import type { AiProvider } from "@/features/translate/types"
import { ttsApi } from "@/features/tts/api"
import { writeApi, type Story, type StoryCharacter, type StoryChapter } from "../api"
import { CharacterFields } from "../CharacterFields"
import { selectClass } from "../formStyles"
import { PageSkeleton } from "@/components/Skeleton"

export function WriteStoryPage() {
  const t = useT()
  const navigate = useNavigate()
  const { storyId } = useParams()
  const id = Number(storyId)
  const [confirm, confirmDialog] = useConfirm()
  const [story, setStory] = useState<Story | null>(null)
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [title, setTitle] = useState("")
  const [premise, setPremise] = useState("")
  const [ending, setEnding] = useState("")
  const [chapterCount, setChapterCount] = useState(8)
  const [providerId, setProviderId] = useState("")
  const [characters, setCharacters] = useState<StoryCharacter[]>([])
  const [busy, setBusy] = useState(false)
  const [streamingIndex, setStreamingIndex] = useState<number | null>(null)

  const writing = story?.status === "writing" || story?.status === "stopping"

  function hydrate(next: Story) {
    setTitle(next.title)
    setPremise(next.premise)
    setEnding(next.ending)
    setChapterCount(next.chapter_count)
    setProviderId(next.provider_id == null ? "" : String(next.provider_id))
    setCharacters(next.characters)
  }

  function apply(next: Story) {
    setStory(next)
    if (next.status === "writing" || next.status === "stopping") return
    hydrate(next)
  }

  useEffect(() => {
    if (!Number.isFinite(id)) return
    let stale = false
    writeApi
      .get(id)
      .then((next) => {
        if (stale) return
        setStory(next)
        hydrate(next)
      })
      .catch((err) => {
        if (!stale) toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
      })
    translateApi
      .listAiProviders()
      .then((rows) => {
        if (!stale) setProviders([...rows].sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock")))
      })
      .catch(() => setProviders([]))
    return () => {
      stale = true
    }
  }, [id, t])

  useEffect(() => {
    if (!writing || !Number.isFinite(id)) return
    let stale = false
    const timer = window.setInterval(() => {
      writeApi
        .get(id)
        .then((next) => {
          if (!stale) apply(next)
        })
        .catch(() => undefined)
    }, 2000)
    return () => {
      stale = true
      window.clearInterval(timer)
    }
  }, [writing, id])

  async function saveSetup() {
    setBusy(true)
    try {
      apply(
        await writeApi.patch(id, {
          title: title.trim(),
          premise: premise.trim(),
          ending: ending.trim(),
          chapter_count: chapterCount,
          provider_id: Number(providerId),
          characters: characters.filter((c) => c.name.trim()),
        }),
      )
      toast.success(t("write.saved"))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function outline() {
    const hasBeat = story?.chapters.some((c) => c.beat.trim())
    if (hasBeat) {
      const ok = await confirm({ title: t("write.outlineReplace"), description: t("write.outlineConfirm") })
      if (!ok) return
    }
    setBusy(true)
    try {
      apply(await writeApi.outline(id, Boolean(hasBeat)))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function writeOne(index: number, hasText: boolean) {
    if (hasText) {
      const ok = await confirm({ title: t("write.rewriteChapter"), description: t("write.rewriteConfirm") })
      if (!ok) return
    }
    setBusy(true)
    setStreamingIndex(index)
    try {
      await writeApi.streamChapter(id, index, hasText, (text) => {
        setStory((prev) =>
          prev
            ? { ...prev, chapters: prev.chapters.map((c) => (c.index === index ? { ...c, text } : c)) }
            : prev,
        )
      })
      apply(await writeApi.get(id))
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : t("app.unknownError")
      toast.error(message)
    } finally {
      setBusy(false)
      setStreamingIndex(null)
    }
  }

  async function writeAll() {
    setBusy(true)
    try {
      setStory(await writeApi.writeAll(id))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function stop() {
    try {
      setStory(await writeApi.stop(id))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function saveChapter(index: number, body: { title?: string; beat?: string; text?: string }) {
    try {
      const saved = (await writeApi.patchChapter(id, index, body)).chapters.find((c) => c.index === index)
      if (!saved) return
      // Chỉ ghi đè trường vừa lưu — chương khác có thể đang gõ dở.
      const fields = Object.fromEntries(Object.keys(body).map((k) => [k, saved[k as keyof typeof body]]))
      setStory((prev) =>
        prev ? { ...prev, chapters: prev.chapters.map((c) => (c.index === index ? { ...c, ...fields } : c)) } : prev,
      )
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  async function sendRead() {
    if (!story) return
    const chapters = story.chapters.filter((c) => c.text.trim())
    if (chapters.length === 0) {
      toast.error(t("tts.needChapters"))
      return
    }
    setBusy(true)
    try {
      const created = await ttsApi.fromTranslate({
        title: story.title,
        author: "",
        lang: "vi",
        external_id: `write:story:${story.id}`,
        chapters: chapters.map((c) => ({ index: c.index, title: c.title, text: c.text })),
      })
      toast.success(created.created ? t("tts.sent") : t("tts.alreadyThere"))
      navigate(`/tts/${created.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  if (!story) return <PageSkeleton />

  const filled = story.chapters.filter((c) => c.text.trim()).length
  const current = story.chapters.find((c) => !c.text.trim())?.index ?? story.chapter_count
  const total = story.chapter_count
  const hasOutline = story.chapters.some((c) => c.beat.trim())
  const mockSelected = providers.find((p) => String(p.id) === providerId)?.kind === "mock"

  function editChapter(index: number, patch: Partial<StoryChapter>) {
    setStory((prev) =>
      prev ? { ...prev, chapters: prev.chapters.map((c) => (c.index === index ? { ...c, ...patch } : c)) } : prev,
    )
  }

  return (
    <PageShell>
      {confirmDialog}
      <PageHeader
        breadcrumbs={[{ label: t("write.title"), to: "/write" }, { label: story.title }]}
        eyebrow={t("write.storyEyebrow")}
        stage="write"
        title={story.title}
        meta={
          <>
            {writing ? <StatusPill status={story.status} /> : filled >= total && total > 0 ? <StatusPill status="completed" /> : null}
            <span>
              {story.status === "writing"
                ? t("write.writing", { current, total })
                : story.status === "stopping"
                  ? t("write.stopping")
                  : t("write.filled", { filled, total })}
            </span>
          </>
        }
        secondaryActions={
          <>
            <Button type="button" variant="outline" disabled={busy || writing} onClick={() => void outline()}>
              <ListTree className="size-4" aria-hidden />
              {filled || hasOutline ? t("write.outlineReplace") : t("write.outline")}
            </Button>
            {filled > 0 ? (
              <Link to={`/read/write/${story.id}`} className={buttonVariants({ variant: "outline" })}>
                <BookOpen className="size-4" aria-hidden />
                {t("reader.read")}
              </Link>
            ) : null}
            <Button type="button" variant="outline" disabled={busy || filled === 0} onClick={() => void sendRead()}>
              <Headphones className="size-4" aria-hidden />
              {t("write.sendRead")}
            </Button>
          </>
        }
        primaryAction={
          story.status === "writing" ? (
            <Button type="button" variant="outline" onClick={() => void stop()}>
              <Square className="size-3.5 fill-current" aria-hidden />
              {t("write.stop")}
            </Button>
          ) : (
            <Button type="button" disabled={busy || writing} onClick={() => void writeAll()}>
              <Sparkles className="size-4" aria-hidden />
              {t("write.writeAll")}
            </Button>
          )
        }
      />
      <Progress
        value={total > 0 ? (filled / total) * 100 : 0}
        tone="write"
        live={writing}
        label={t("write.filled", { filled, total })}
      />
      {story.write_error ? (
        <div role="alert" className="flex items-start gap-2.5 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">{story.write_error}</span>
        </div>
      ) : null}

      <div className="grid items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <SectionCard title={t("write.setup")} className="lg:sticky lg:top-8">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="story-title">{t("write.storyTitle")}</Label>
              <Input id="story-title" value={title} disabled={writing} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="story-premise">{t("write.premise")}</Label>
              <Textarea id="story-premise" value={premise} disabled={writing} rows={4} onChange={(e) => setPremise(e.target.value)} />
            </div>
            <div className="grid grid-cols-[1fr_6rem] gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="story-ending">{t("write.ending")}</Label>
                <Input id="story-ending" value={ending} disabled={writing} onChange={(e) => setEnding(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="story-count">{t("write.chapters")}</Label>
                <Input
                  id="story-count"
                  type="number"
                  min={4}
                  max={40}
                  value={chapterCount}
                  disabled={writing}
                  className="font-mono"
                  onChange={(e) => setChapterCount(Number(e.target.value))}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="story-ai">{t("write.ai")}</Label>
              <select
                id="story-ai"
                className={selectClass}
                value={providerId}
                disabled={writing}
                onChange={(e) => setProviderId(e.target.value)}
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                    {p.kind === "mock" ? ` ${t("write.mockSuffix")}` : ""}
                  </option>
                ))}
              </select>
              {mockSelected ? (
                <p className="rounded-[10px] bg-warning-soft px-3 py-2 text-[13px] text-warning">{t("write.mockWarning")}</p>
              ) : null}
            </div>
            <CharacterFields characters={characters} onChange={setCharacters} disabled={writing} />
            <Button type="button" variant="outline" className="w-full" disabled={busy || writing} onClick={() => void saveSetup()}>
              <Save className="size-4" aria-hidden />
              {t("write.save")}
            </Button>
          </div>
        </SectionCard>

        <section className="min-w-0 space-y-4" aria-label={t("write.chapters")}>
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-display text-[22px] font-semibold">{t("write.chapters")}</h2>
            <span className="font-mono text-[13px] text-muted-foreground">
              {filled}/{total}
            </span>
          </div>
          <ol className="stagger space-y-4">
            {story.chapters.map((chapter) => {
              const hasText = Boolean(chapter.text.trim())
              const streaming = streamingIndex === chapter.index
              const inProgress = streaming || (story.status === "writing" && !hasText && chapter.index === current)
              return (
                <li
                  key={chapter.index}
                  className={cn(
                    "rounded-2xl border bg-card p-4 transition-[border-color,box-shadow] sm:p-5",
                    inProgress ? "border-stage-write/50 shadow-sm" : "border-border",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full font-mono text-sm font-medium",
                        hasText ? "bg-stage-write text-white" : "bg-stage-write-soft text-stage-write",
                      )}
                    >
                      {chapter.index}
                    </span>
                    <div className="min-w-0 flex-1 space-y-2.5">
                      <div className="flex items-center gap-2">
                        <Input
                          value={chapter.title}
                          disabled={writing}
                          aria-label={t("write.chapterTitle")}
                          className="font-display h-10 min-w-0 flex-1 border-transparent bg-transparent px-2 text-[18px] font-semibold shadow-none hover:border-input focus-visible:border-ring"
                          onChange={(e) => editChapter(chapter.index, { title: e.target.value })}
                          onBlur={(e) => void saveChapter(chapter.index, { title: e.target.value })}
                        />
                        {inProgress ? <StatusPill status="writing" /> : null}
                      </div>
                      <Input
                        value={chapter.beat}
                        disabled={writing}
                        aria-label={t("write.beat")}
                        placeholder={t("write.beat")}
                        onChange={(e) => editChapter(chapter.index, { beat: e.target.value })}
                        onBlur={(e) => void saveChapter(chapter.index, { beat: e.target.value })}
                      />
                      <Textarea
                        value={chapter.text}
                        disabled={writing}
                        rows={8}
                        aria-label={t("write.chapterText")}
                        placeholder={t("write.chapterTextPlaceholder")}
                        className="font-reading min-h-40 text-[16px] leading-[1.75]"
                        onChange={(e) => editChapter(chapter.index, { text: e.target.value })}
                        onBlur={(e) => void saveChapter(chapter.index, { text: e.target.value })}
                      />
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {hasText ? t("write.words", { count: countWords(chapter.text) }) : ""}
                        </span>
                        <Button
                          type="button"
                          variant={hasText ? "outline" : "secondary"}
                          size="sm"
                          disabled={busy || writing}
                          onClick={() => void writeOne(chapter.index, hasText)}
                        >
                          <PenLine className="size-4" aria-hidden />
                          {streaming ? t("write.streaming") : hasText ? t("write.rewriteChapter") : t("write.writeChapter")}
                        </Button>
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      </div>
    </PageShell>
  )
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}
