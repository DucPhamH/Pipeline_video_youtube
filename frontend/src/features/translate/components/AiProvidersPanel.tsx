/** Quản lý danh sách AI đã lưu (registry backend) — dùng ở Settings và làm
 * nguồn cho AI picker trong modal "Bắt đầu dịch" / Job Detail. */
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "@/api/client"
import { translateApi } from "../api"
import { AI_CATALOG, KINDS_NO_KEY_REQUIRED, getCatalogEntry } from "../providerProfiles"
import type { AiProvider, AiProviderInput } from "../types"

type FormState = AiProviderInput

function blankForm(kind = "custom"): FormState {
  const cat = getCatalogEntry(kind)
  return {
    label: cat?.label ?? "",
    kind,
    base_url: cat?.base_url ?? "",
    model: cat?.default_model ?? "",
    api_key: "",
    api_keys: [],
    requires_api_key: !KINDS_NO_KEY_REQUIRED.has(kind),
  }
}

/** Danh sách key cuối cùng gửi lên API lúc TẠO MỚI: key chính + key phụ đã
 * thêm, không trùng lặp. */
function buildApiKeysPayload(f: FormState): string[] {
  return Array.from(
    new Set([f.api_key ?? "", ...(f.api_keys ?? [])].map((k) => k.trim()).filter(Boolean)),
  )
}

/** Blurb + link lấy API key theo từng loại AI (catalog đã có sẵn `docs_url`
 * nhưng trước đây chưa hiện ra chỗ nào — user phải tự đoán link). */
function CatalogKindHint({ kind }: { kind: string }) {
  const t = useT()
  const cat = getCatalogEntry(kind)
  if (!cat?.blurb && !cat?.docs_url) return null
  return (
    <p className="text-xs text-muted-foreground">
      {cat.blurb}
      {cat.blurb && cat.docs_url ? " — " : ""}
      {cat.docs_url ? (
        <a href={cat.docs_url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
          {t("translate.aiProviderGetKeyLink")}
        </a>
      ) : null}
    </p>
  )
}

/** Model field: tự xổ dropdown model gợi ý theo `kind` (không cần key) — vẫn
 * cho gõ tay khi chọn "Model khác" hoặc kind không có model gợi ý. 1 AI = 1
 * model duy nhất — pattern thật của AiNiee/Glossarion là xoay nhiều KEY cùng 1
 * model để né rate-limit, không xoay theo tên model (thường vẫn chung 1 hạn
 * mức nếu cùng 1 key/project). */
function ModelField({
  kind,
  value,
  onChange,
}: {
  kind: string
  value: string
  onChange: (model: string) => void
}) {
  const t = useT()
  const models = getCatalogEntry(kind)?.model_suggestions ?? []
  const inList = models.includes(value)

  if (models.length === 0) {
    return (
      <div className="space-y-1">
        <Label>{t("translate.modelDefault")}</Label>
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" placeholder="model-id" />
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <Label>{t("translate.modelDefault")}</Label>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-background px-2 font-mono text-xs"
        value={inList ? value : "__custom__"}
        onChange={(e) => onChange(e.target.value === "__custom__" ? "" : e.target.value)}
      >
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
        <option value="__custom__">{t("settings.customModel")}</option>
      </select>
      {!inList ? (
        <>
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="model-id"
            className="mt-1.5 h-9 font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">{t("translate.customModelHint")}</p>
        </>
      ) : null}
    </div>
  )
}

function maskKeyTail(key: string): string {
  const tail = key.trim().slice(-4)
  return tail ? `••••${tail}` : "••••"
}

/** Key phụ CÙNG tài khoản này (kiểu AiNiee/Glossarion: nhiều key né rate-limit
 * vì mỗi key thường có hạn mức riêng) — dùng lúc TẠO MỚI, client giữ tạm trong
 * state (chưa lưu, gõ gì cũng tự do). Key đã lưu (edit) dùng `LiveExtraKeysField`
 * riêng vì key là secret, không round-trip được. */
function ExtraKeysField({
  keys,
  onChange,
}: {
  keys: string[]
  onChange: (keys: string[]) => void
}) {
  const t = useT()
  const [input, setInput] = useState("")

  function add() {
    const v = input.trim()
    if (!v || keys.includes(v)) return
    onChange([...keys, v])
    setInput("")
  }

  return (
    <div className="space-y-1.5 sm:col-span-2">
      <Label>{t("translate.extraKeysLabel")}</Label>
      <p className="text-xs text-muted-foreground">{t("translate.extraKeysHint")}</p>
      {keys.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {keys.map((k, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-input bg-muted px-2 py-0.5 font-mono text-xs"
            >
              {maskKeyTail(k)}
              <button
                type="button"
                onClick={() => onChange(keys.filter((_, idx) => idx !== i))}
                className="text-muted-foreground hover:text-foreground"
                aria-label={t("common.confirmDelete")}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex gap-1.5">
        <Input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              add()
            }
          }}
          placeholder="sk-…"
          className="h-8 font-mono text-xs"
        />
        <Button type="button" size="sm" variant="outline" onClick={add}>
          {t("translate.modelAddCustom")}
        </Button>
      </div>
    </div>
  )
}

/** Key phụ của 1 AI ĐÃ LƯU — thêm/xoá gọi API ngay lập tức (không qua nút
 * "Lưu" của form), vì key là secret: client chỉ có hint bị che, không thể
 * gửi lại nguyên vẹn qua PUT full-replace. */
function LiveExtraKeysField({
  provider,
  onChanged,
}: {
  provider: AiProvider
  onChanged: (updated: AiProvider) => void
}) {
  const t = useT()
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const extraHints = provider.api_key_hints.slice(1) // index 0 = key chính

  async function add() {
    const v = input.trim()
    if (!v) return
    setBusy(true)
    try {
      const updated = await translateApi.addAiProviderKey(provider.id, v)
      onChanged(updated)
      setInput("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function remove(indexInFullList: number) {
    setBusy(true)
    try {
      onChanged(await translateApi.deleteAiProviderKey(provider.id, indexInFullList))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1.5 sm:col-span-2">
      <Label>{t("translate.extraKeysLabel")}</Label>
      <p className="text-xs text-muted-foreground">{t("translate.extraKeysHintEdit")}</p>
      {extraHints.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {extraHints.map((hint, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-input bg-muted px-2 py-0.5 font-mono text-xs"
            >
              …{hint.replace(/^…/, "")}
              <button
                type="button"
                disabled={busy}
                onClick={() => void remove(i + 1)}
                className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                aria-label={t("common.confirmDelete")}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex gap-1.5">
        <Input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              void add()
            }
          }}
          placeholder="sk-…"
          className="h-8 font-mono text-xs"
          disabled={busy}
        />
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void add()}>
          {t("translate.modelAddCustom")}
        </Button>
      </div>
    </div>
  )
}

export function AiProvidersPanel() {
  const t = useT()
  const [items, setItems] = useState<AiProvider[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<FormState>(blankForm())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<FormState>(blankForm())
  const [busy, setBusy] = useState(false)

  function load() {
    translateApi
      .listAiProviders()
      .then(setItems)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("app.unknownError")))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function pickKind(kind: string, setter: (f: FormState) => void, current: FormState) {
    const cat = getCatalogEntry(kind)
    setter({
      ...current,
      kind,
      label: current.label.trim() ? current.label : cat?.label ?? kind,
      // BUG đã sửa: base_url trước đây "giữ nguyên nếu không rỗng" — nên đổi
      // từ OpenAI sang Gemini (hay bất kỳ loại khác) vẫn giữ base_url CŨ của
      // loại trước đó (vd https://api.openai.com/v1), gọi API sai hẳn endpoint
      // mà không báo lỗi rõ ràng. Đổi loại AI GIỜ LUÔN đồng bộ lại base_url
      // đúng theo loại mới chọn — muốn tự gõ URL riêng thì chọn "Khác/tự nhập".
      base_url: cat?.base_url ?? "",
      model: current.model?.trim() ? current.model : cat?.default_model ?? "",
      requires_api_key: !KINDS_NO_KEY_REQUIRED.has(kind),
    })
  }

  async function handleAdd() {
    if (!form.label.trim()) {
      toast.error(t("translate.aiProviderLabelNeed"))
      return
    }
    setBusy(true)
    try {
      await translateApi.createAiProvider({
        ...form,
        api_keys: buildApiKeysPayload(form),
      })
      toast.success(t("translate.aiProviderSaved"))
      setAdding(false)
      setForm(blankForm())
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  function startEdit(p: AiProvider) {
    setEditingId(p.id)
    setEditForm({
      label: p.label,
      kind: p.kind,
      base_url: p.base_url,
      model: p.model,
      api_key: "",
      requires_api_key: p.requires_api_key,
    })
  }

  async function handleSaveEdit(id: number) {
    setBusy(true)
    try {
      const body: Partial<AiProviderInput> = {
        label: editForm.label,
        kind: editForm.kind,
        base_url: editForm.base_url,
        model: editForm.model,
        requires_api_key: editForm.requires_api_key,
      }
      if (editForm.api_key?.trim()) body.api_key = editForm.api_key
      await translateApi.updateAiProvider(id, body)
      toast.success(t("translate.aiProviderSaved"))
      setEditingId(null)
      load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm(t("translate.aiProviderDeleteConfirm"))) return
    try {
      await translateApi.deleteAiProvider(id)
      setItems((list) => list.filter((p) => p.id !== id))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
    }
  }

  function updateItemInPlace(updated: AiProvider) {
    setItems((list) => list.map((it) => (it.id === updated.id ? updated : it)))
  }

  function keyStatus(p: AiProvider) {
    if (!p.requires_api_key) return t("translate.aiProviderNoKeyNeeded")
    if (!p.has_api_key) return t("translate.noKey")
    const base = `key …${p.api_key_hint.replace(/^…/, "")}`
    return p.key_count > 1 ? `${base} (+${p.key_count - 1})` : base
  }

  if (loadError) {
    return (
      <SectionCard title={t("settings.aiProviders")}>
        <p className="text-sm text-destructive">{loadError}</p>
      </SectionCard>
    )
  }

  return (
    <SectionCard
      title={t("settings.aiProviders")}
      description={t("translate.aiProviderManageHint")}
      actions={
        !adding ? (
          <Button type="button" size="sm" onClick={() => setAdding(true)}>
            {t("translate.aiProviderAdd")}
          </Button>
        ) : null
      }
    >
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      ) : (
        <ul className="divide-y divide-border text-sm">
          {items.map((p) =>
            editingId === p.id ? (
              <li key={p.id} className="space-y-3 py-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label>{t("translate.aiProviderKind")}</Label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={editForm.kind}
                      onChange={(e) => pickKind(e.target.value, setEditForm, editForm)}
                    >
                      {AI_CATALOG.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.label}
                        </option>
                      ))}
                      <option value="custom">{t("translate.aiProviderCustomKind")}</option>
                    </select>
                    <CatalogKindHint kind={editForm.kind} />
                  </div>
                  <div className="space-y-1">
                    <Label>{t("translate.aiProviderLabel")}</Label>
                    <Input
                      value={editForm.label}
                      onChange={(e) => setEditForm((f) => ({ ...f, label: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>{t("translate.baseUrlLabel")}</Label>
                    <Input
                      value={editForm.base_url}
                      onChange={(e) => setEditForm((f) => ({ ...f, base_url: e.target.value }))}
                      className="font-mono text-xs"
                    />
                    <p className="text-xs text-muted-foreground">{t("translate.baseUrlHint")}</p>
                  </div>
                  <ModelField
                    kind={editForm.kind}
                    value={editForm.model ?? ""}
                    onChange={(model) => setEditForm((f) => ({ ...f, model }))}
                  />
                  <div className="space-y-1 sm:col-span-2">
                    <Label>{t("translate.setApiKey")}</Label>
                    <Input
                      type="password"
                      autoComplete="off"
                      value={editForm.api_key}
                      onChange={(e) => setEditForm((f) => ({ ...f, api_key: e.target.value }))}
                      placeholder={p.has_api_key ? "•••• (giữ nguyên nếu để trống)" : "sk-…"}
                      className="font-mono text-sm"
                    />
                  </div>
                  <LiveExtraKeysField provider={p} onChanged={updateItemInPlace} />
                  <label className="flex items-center gap-2 text-sm sm:col-span-2">
                    <input
                      type="checkbox"
                      checked={editForm.requires_api_key}
                      onChange={(e) =>
                        setEditForm((f) => ({ ...f, requires_api_key: e.target.checked }))
                      }
                    />
                    {t("translate.aiProviderRequiresKey")}
                  </label>
                </div>
                <div className="flex gap-2">
                  <Button type="button" size="sm" disabled={busy} onClick={() => handleSaveEdit(p.id)}>
                    {t("common.save")}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setEditingId(null)}
                  >
                    {t("common.cancel")}
                  </Button>
                </div>
              </li>
            ) : (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {p.label}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">{p.kind}</span>
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {p.model || "—"} · {keyStatus(p)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button type="button" size="sm" variant="outline" onClick={() => startEdit(p)}>
                    {t("common.edit")}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => handleDelete(p.id)}>
                    {t("common.confirmDelete")}
                  </Button>
                </div>
              </li>
            ),
          )}
        </ul>
      )}

      {adding ? (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>{t("translate.aiProviderKind")}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={form.kind}
                onChange={(e) => pickKind(e.target.value, setForm, form)}
              >
                {AI_CATALOG.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
                <option value="custom">{t("translate.aiProviderCustomKind")}</option>
              </select>
              <CatalogKindHint kind={form.kind} />
            </div>
            <div className="space-y-1">
              <Label>{t("translate.aiProviderLabel")}</Label>
              <Input value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>{t("translate.baseUrlLabel")}</Label>
              <Input
                value={form.base_url}
                onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                className="font-mono text-xs"
              />
              <p className="text-xs text-muted-foreground">{t("translate.baseUrlHint")}</p>
            </div>
            <ModelField kind={form.kind} value={form.model ?? ""} onChange={(model) => setForm((f) => ({ ...f, model }))} />
            <div className="space-y-1 sm:col-span-2">
              <Label>{t("translate.setApiKey")}</Label>
              <Input
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                placeholder="sk-…"
                className="font-mono text-sm"
              />
            </div>
            <ExtraKeysField
              keys={form.api_keys ?? []}
              onChange={(api_keys) => setForm((f) => ({ ...f, api_keys }))}
            />
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                checked={form.requires_api_key}
                onChange={(e) => setForm((f) => ({ ...f, requires_api_key: e.target.checked }))}
              />
              {t("translate.aiProviderRequiresKey")}
            </label>
            {!form.requires_api_key ? (
              <p className="text-xs text-muted-foreground sm:col-span-2">
                {t("translate.aiProviderLocalHint")}
              </p>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button type="button" disabled={busy} onClick={() => void handleAdd()}>
              {busy ? t("common.saving") : t("common.save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setAdding(false)
                setForm(blankForm())
              }}
            >
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}
    </SectionCard>
  )
}
