import { useEffect, useRef, useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { BookOpen, MoreHorizontal, PenLine, Plus, Trash2 } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { BookCover } from "@/components/BookCover"
import { EmptyState } from "@/components/EmptyState"
import { ListSkeleton } from "@/components/Skeleton"
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
import { writeApi, type StoryCharacter, type StoryListItem } from "../api"
import { CharacterFields } from "../CharacterFields"
import { selectClass } from "../formStyles"

export function WriteStoriesPage() {
  const t = useT()
  const navigate = useNavigate()
  const [confirm, confirmDialog] = useConfirm()
  const [items, setItems] = useState<StoryListItem[] | null>(null)
  const titleRef = useRef<HTMLInputElement>(null)
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [title, setTitle] = useState("")
  const [premise, setPremise] = useState("")
  const [ending, setEnding] = useState("")
  const [chapterCount, setChapterCount] = useState(8)
  const [providerId, setProviderId] = useState("")
  const [characters, setCharacters] = useState<StoryCharacter[]>([{ name: "", role: "" }])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    writeApi.list().then((r) => setItems(r.items)).catch(() => setItems([]))
    translateApi
      .listAiProviders()
      .then((rows) => {
        const ordered = [...rows].sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
        setProviders(ordered)
        const first = ordered.find((p) => p.kind !== "mock") ?? ordered[0]
        if (first) setProviderId(String(first.id))
      })
      .catch(() => setProviders([]))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!title.trim() || !premise.trim() || !providerId) {
      toast.error(t("write.needFields"))
      return
    }
    setSaving(true)
    try {
      const story = await writeApi.create({
        title: title.trim(),
        premise: premise.trim(),
        ending: ending.trim(),
        chapter_count: chapterCount,
        provider_id: Number(providerId),
        characters: characters.filter((c) => c.name.trim()),
      })
      navigate(`/write/${story.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number) {
    const ok = await confirm({ title: t("write.title"), description: t("write.deleteConfirm"), confirmLabel: t("write.delete"), destructive: true })
    if (!ok) return
    try {
      await writeApi.remove(id)
      setItems((prev) => (prev ?? []).filter((item) => item.id !== id))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  function focusForm() {
    const el = titleRef.current
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "center" })
    el.focus({ preventScroll: true })
  }

  const mockSelected = providers.find((p) => String(p.id) === providerId)?.kind === "mock"

  return (
    <PageShell>
      {confirmDialog}
      <PageHeader
        eyebrow={t("write.eyebrow")}
        stage="write"
        title={t("write.title")}
        description={t("write.subtitle")}
        meta={items ? <span>{t("write.storyCount", { count: items.length })}</span> : null}
        primaryAction={
          <Button type="button" onClick={focusForm}>
            <Plus className="size-4" aria-hidden />
            {t("write.newStory")}
          </Button>
        }
      />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="min-w-0 space-y-3" aria-label={t("write.yourStories")}>
          <h2 className="font-display text-[22px] font-semibold">{t("write.yourStories")}</h2>
          {items == null ? (
            <div className="rounded-2xl border border-border bg-card p-5">
              <ListSkeleton rows={3} />
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card">
              <EmptyState
                tone="write"
                icon={PenLine}
                title={t("write.empty")}
                hint={t("write.emptyHint")}
                action={
                  <Button type="button" variant="outline" onClick={focusForm}>
                    {t("write.newStory")}
                  </Button>
                }
              />
            </div>
          ) : (
            <ul className="stagger space-y-3">
              {items.map((item) => {
                const live = item.status === "writing" || item.status === "stopping"
                const done = item.chapter_count > 0 && item.filled_count >= item.chapter_count
                const value = item.chapter_count > 0 ? (item.filled_count / item.chapter_count) * 100 : 0
                return (
                  <li
                    key={item.id}
                    className="group flex items-center gap-4 rounded-2xl border border-border bg-card p-4 transition-[border-color,box-shadow] hover:border-primary/30 hover:shadow-sm"
                  >
                    <Link to={`/write/${item.id}`} className="w-14 shrink-0 sm:w-16" tabIndex={-1} aria-hidden>
                      <BookCover title={item.title} subtitle="" />
                    </Link>
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                        <Link
                          to={`/write/${item.id}`}
                          className="font-display min-w-0 truncate text-[18px] font-semibold hover:underline"
                        >
                          {item.title}
                        </Link>
                        {live ? <StatusPill status={item.status} /> : done ? <StatusPill status="completed" /> : null}
                      </div>
                      <div className="flex items-center gap-3">
                        <Progress value={value} tone="write" live={live} size="sm" className="max-w-[240px]" label={item.title} />
                        <span className="shrink-0 font-mono text-xs text-muted-foreground">
                          {t("write.filled", { filled: item.filled_count, total: item.chapter_count })}
                        </span>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {item.filled_count > 0 ? (
                        <Link
                          to={`/read/write/${item.id}`}
                          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "hidden sm:inline-flex")}
                        >
                          <BookOpen className="size-4" aria-hidden />
                          {t("reader.read")}
                        </Link>
                      ) : null}
                      <ActionMenu
                        variant="ghost"
                        size="sm"
                        showChevron={false}
                        label={
                          <>
                            <MoreHorizontal className="size-4" aria-hidden />
                            <span className="sr-only">{t("write.more")}</span>
                          </>
                        }
                      >
                        <ActionMenuItem onSelect={() => navigate(`/write/${item.id}`)}>{t("write.openEditor")}</ActionMenuItem>
                        {item.filled_count > 0 ? (
                          <ActionMenuItem onSelect={() => navigate(`/read/write/${item.id}`)}>{t("reader.read")}</ActionMenuItem>
                        ) : null}
                        <ActionMenuItem destructive onSelect={() => void handleDelete(item.id)}>
                          <Trash2 className="mr-2 size-4" aria-hidden />
                          {t("write.delete")}
                        </ActionMenuItem>
                      </ActionMenu>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <SectionCard title={t("write.newStory")} description={t("write.newStoryHint")} className="lg:sticky lg:top-8">
          <form className="space-y-4" onSubmit={(e) => void handleCreate(e)}>
            <div className="space-y-1.5">
              <Label htmlFor="write-title">{t("write.storyTitle")}</Label>
              <Input id="write-title" ref={titleRef} value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="write-premise">{t("write.premise")}</Label>
              <Textarea id="write-premise" value={premise} onChange={(e) => setPremise(e.target.value)} rows={4} />
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_7rem]">
              <div className="space-y-1.5">
                <Label htmlFor="write-ending">{t("write.ending")}</Label>
                <Input
                  id="write-ending"
                  value={ending}
                  placeholder={t("write.endingPlaceholder")}
                  onChange={(e) => setEnding(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="write-count">{t("write.chapters")}</Label>
                <Input
                  id="write-count"
                  type="number"
                  min={4}
                  max={40}
                  value={chapterCount}
                  className="font-mono"
                  onChange={(e) => setChapterCount(Number(e.target.value))}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="write-ai">{t("write.ai")}</Label>
              {providers.length === 0 ? (
                <p className="rounded-[10px] bg-warning-soft px-3 py-2 text-sm text-warning">{t("write.needAi")}</p>
              ) : (
                <select id="write-ai" className={selectClass} value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                      {p.kind === "mock" ? ` ${t("write.mockSuffix")}` : ""}
                    </option>
                  ))}
                </select>
              )}
              {mockSelected ? (
                <p className="rounded-[10px] bg-warning-soft px-3 py-2 text-[13px] text-warning">{t("write.mockWarning")}</p>
              ) : null}
            </div>
            <CharacterFields characters={characters} onChange={setCharacters} />
            <Button type="submit" className="w-full" disabled={saving || providers.length === 0}>
              <PenLine className="size-4" aria-hidden />
              {saving ? t("common.saving") : t("write.create")}
            </Button>
          </form>
        </SectionCard>
      </div>
    </PageShell>
  )
}
