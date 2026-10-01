import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarClock, Filter, Network } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { ListSkeleton } from "@/components/Skeleton"
import { useT } from "@/i18n"
import { queryKeys } from "@/lib/query-client"
import { ApiError } from "../../../api/client"
import { crawlApi, perSiteSettingKey } from "../api"
import { SettingGroup, SettingRow } from "./SettingRow"

const NONE_VALUE = "__none__"
const GENRE_SELECT_LIMIT = 100

// Setting quyết định CÁCH QUÉT của riêng site này (mục 9.0) — khác site
// khác có thể có tốc độ/độ dài truyện phổ biến khác nhau.

type SettingFieldDef =
  | { type: "number"; key: string; default: number; labelKey: string; hintKey: string }
  | {
      type: "select"
      key: string
      default: string
      labelKey: string
      hintKey: string
      options: Array<{ value: string; labelKey: string }>
    }

type SettingField =
  | { type: "number"; key: string; label: string; hint: string; default: number }
  | {
      type: "select"
      key: string
      label: string
      hint: string
      default: string
      options: Array<{ value: string; label: string }>
    }

const SITE_SETTING_FIELD_DEFS: SettingFieldDef[] = [
  {
    type: "number",
    key: "scan_window",
    default: 5,
    labelKey: "site.fieldScanWindow",
    hintKey: "site.fieldScanWindowHint",
  },
  {
    type: "number",
    key: "max_chapters_per_story",
    default: 50,
    labelKey: "site.fieldMaxChapters",
    hintKey: "site.fieldMaxChaptersHint",
  },
  {
    type: "number",
    key: "max_pages_per_scan",
    default: 3,
    labelKey: "site.fieldMaxPages",
    hintKey: "site.fieldMaxPages",
  },
  {
    type: "number",
    key: "max_consecutive_errors",
    default: 5,
    labelKey: "site.fieldMaxErrors",
    hintKey: "site.fieldMaxErrors",
  },
  {
    type: "select",
    key: "narration_filter",
    default: "first_person",
    labelKey: "site.fieldNarration",
    hintKey: "site.fieldNarrationHint",
    options: [
      { value: "any", labelKey: "site.optAny" },
      { value: "first_person", labelKey: "site.optFirstPerson" },
      { value: "third_person", labelKey: "site.optThirdPerson" },
    ],
  },
  {
    type: "select",
    key: "completion_filter",
    default: "completed_only",
    labelKey: "site.fieldCompletion",
    hintKey: "site.fieldCompletionHint",
    options: [
      { value: "completed_only", labelKey: "site.optCompleted" },
      { value: "ongoing_only", labelKey: "site.optOngoing" },
      { value: "any", labelKey: "site.optAny" },
    ],
  },
  {
    type: "select",
    key: "opencc_mode",
    default: "none",
    labelKey: "site.fieldOpencc",
    hintKey: "site.fieldOpenccHint",
    options: [
      { value: "none", labelKey: "site.optOpenccNone" },
      { value: "t2s", labelKey: "site.optOpenccT2s" },
      { value: "s2t", labelKey: "site.optOpenccS2t" },
      { value: "s2tw", labelKey: "site.optOpenccS2tw" },
      { value: "tw2s", labelKey: "site.optOpenccTw2s" },
    ],
  },
]

type SiteSettingValue = number | string | boolean

const DAILY_SETTING_DEFAULTS: Record<string, SiteSettingValue> = {
  daily_enabled: false,
  daily_hour: 6,
  daily_minute: 0,
  daily_genre_key: "",
  http_proxy: "",
}

/** Preset lọc quét — chỉ đụng field filter, giữ nguyên lịch daily. */
const SCAN_FILTER_PRESETS: Array<{
  id: string
  labelKey: string
  hintKey: string
  values: Record<string, SiteSettingValue>
}> = [
  {
    id: "short_video_cn",
    labelKey: "site.presetShortVideo",
    hintKey: "site.presetShortVideoHint",
    values: {
      scan_window: 5,
      max_chapters_per_story: 40,
      max_pages_per_scan: 3,
      max_consecutive_errors: 5,
      narration_filter: "first_person",
      completion_filter: "completed_only",
    },
  },
  {
    id: "short_any_voice",
    labelKey: "site.presetShortAny",
    hintKey: "site.presetShortAnyHint",
    values: {
      scan_window: 5,
      max_chapters_per_story: 50,
      max_pages_per_scan: 3,
      max_consecutive_errors: 5,
      narration_filter: "any",
      completion_filter: "completed_only",
    },
  },
  {
    id: "wider",
    labelKey: "site.presetWider",
    hintKey: "site.presetWiderHint",
    values: {
      scan_window: 8,
      max_chapters_per_story: 80,
      max_pages_per_scan: 5,
      max_consecutive_errors: 8,
      narration_filter: "any",
      completion_filter: "completed_only",
    },
  },
]

export function SiteSettingsDialog({
  sourceKey,
  open,
  onOpenChange: setOpen,
}: {
  sourceKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const t = useT()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Record<string, SiteSettingValue> | null>(null)

  const siteSettingFields = useMemo((): SettingField[] => {
    return SITE_SETTING_FIELD_DEFS.map((def) => {
      if (def.type === "number") {
        return {
          type: "number",
          key: def.key,
          label: t(def.labelKey),
          hint: t(def.hintKey),
          default: def.default,
        }
      }
      return {
        type: "select",
        key: def.key,
        label: t(def.labelKey),
        hint: t(def.hintKey),
        default: def.default,
        options: def.options.map((opt) => ({ value: opt.value, label: t(opt.labelKey) })),
      }
    })
  }, [t])

  const { data: settings } = useQuery({
    queryKey: queryKeys.settings,
    queryFn: () => crawlApi.getSettings(),
    enabled: open,
  })

  const { data: genresData } = useQuery({
    queryKey: queryKeys.genres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    queryFn: () => crawlApi.listGenres({ sourceKey, limit: GENRE_SELECT_LIMIT, offset: 0 }),
    enabled: open,
  })
  const genres = genresData?.items ?? []

  const values =
    draft ??
    (settings
      ? Object.fromEntries([
          ...siteSettingFields.map((field) => {
            const raw = settings.values[perSiteSettingKey(field.key, sourceKey)]
            return [field.key, (raw as SiteSettingValue | undefined) ?? field.default]
          }),
          ...Object.entries(DAILY_SETTING_DEFAULTS).map(([key, def]) => {
            const raw = settings.values[perSiteSettingKey(key, sourceKey)]
            return [key, (raw as SiteSettingValue | undefined) ?? def]
          }),
        ])
      : null)

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, SiteSettingValue>) => crawlApi.updateSettings(payload),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings })
      toast.success(t("site.settingsSaved"))
      setOpen(false)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  function patchDraft(key: string, value: SiteSettingValue) {
    setDraft((prev) => ({ ...(prev ?? values ?? {}), [key]: value }))
  }

  function handleNumberChange(key: string, raw: string) {
    const n = Number(raw)
    if (!Number.isFinite(n)) return
    patchDraft(key, n)
  }

  function handleSelectChange(key: string, v: string | null) {
    if (!v) return
    patchDraft(key, v)
  }

  function applyScanPreset(presetId: string) {
    const preset = SCAN_FILTER_PRESETS.find((p) => p.id === presetId)
    if (!preset) return
    setDraft((prev) => ({
      ...(prev ?? values ?? {}),
      ...preset.values,
    }))
    toast.message(t("site.presetApplied", { name: t(preset.labelKey) }))
  }

  function handleTimeChange(raw: string) {
    const [h, m] = raw.split(":").map((p) => Number(p))
    if (!Number.isFinite(h) || !Number.isFinite(m)) return
    setDraft((prev) => ({
      ...(prev ?? values ?? {}),
      daily_hour: Math.min(23, Math.max(0, Math.trunc(h))),
      daily_minute: Math.min(59, Math.max(0, Math.trunc(m))),
    }))
  }

  function handleSave() {
    if (!values) return
    const payload: Record<string, SiteSettingValue> = {}
    for (const key of Object.keys(values)) {
      payload[perSiteSettingKey(key, sourceKey)] = values[key] as SiteSettingValue
    }
    saveMutation.mutate(payload)
  }

  const dailyEnabled = Boolean(values?.daily_enabled)
  const timeValue = values
    ? `${String(Number(values.daily_hour ?? 6)).padStart(2, "0")}:${String(Number(values.daily_minute ?? 0)).padStart(2, "0")}`
    : "06:00"
  const genreKeyValue = String(values?.daily_genre_key ?? "") || NONE_VALUE

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setDraft(null)
      }}
    >
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="shrink-0 space-y-1 border-b px-6 py-5 pr-12">
          <DialogTitle className="text-lg">{t("site.settingsDialogTitle")}</DialogTitle>
          <DialogDescription>{t("site.settingsDialogDesc")}</DialogDescription>
        </DialogHeader>

        {values === null ? (
          <div className="px-6 py-6">
            <ListSkeleton />
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-8 overflow-y-auto px-6 py-6">
            <SettingGroup
              icon={<CalendarClock className="size-4" />}
              title={t("site.dailySectionTitle")}
              description={t("site.dailySectionHint")}
            >
              <SettingRow label={t("site.dailyEnabled")} hint={t("site.dailyEnabledHint")} htmlFor={`${sourceKey}-daily-enabled`}>
                <Switch
                  id={`${sourceKey}-daily-enabled`}
                  checked={dailyEnabled}
                  onCheckedChange={(checked) => patchDraft("daily_enabled", checked === true)}
                />
              </SettingRow>
              <SettingRow label={t("site.dailyTime")} hint={t("site.dailyTimeHint")} htmlFor={`${sourceKey}-daily-time`}>
                <Input
                  id={`${sourceKey}-daily-time`}
                  type="time"
                  value={timeValue}
                  disabled={!dailyEnabled}
                  onChange={(e) => handleTimeChange(e.target.value)}
                  className="h-10 w-full sm:w-40"
                />
              </SettingRow>
              <SettingRow label={t("site.dailyGenre")} hint={t("site.dailyGenreHint")} htmlFor={`${sourceKey}-daily-genre`}>
                <Select
                  value={genreKeyValue}
                  disabled={!dailyEnabled}
                  onValueChange={(v) => handleSelectChange("daily_genre_key", v === NONE_VALUE ? "" : (v ?? ""))}
                >
                  <SelectTrigger id={`${sourceKey}-daily-genre`} className="h-10 w-full">
                    <SelectValue>
                      {(v: string) =>
                        v === NONE_VALUE
                          ? t("site.dailyGenreNone")
                          : (genres.find((g) => g.genre_key === v)?.label ?? v)
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE_VALUE}>{t("site.dailyGenreNone")}</SelectItem>
                    {genres.map((g) => (
                      <SelectItem key={g.genre_key} value={g.genre_key}>
                        {g.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </SettingRow>
              <SettingRow label={t("site.fieldScanWindow")} hint={t("site.fieldScanWindowHint")} htmlFor={`${sourceKey}-scan_window`}>
                <Input
                  id={`${sourceKey}-scan_window`}
                  type="number"
                  min={1}
                  value={Number(values.scan_window ?? 5)}
                  onChange={(e) => handleNumberChange("scan_window", e.target.value)}
                  className="h-10 w-full font-mono sm:w-32"
                />
              </SettingRow>
            </SettingGroup>

            <SettingGroup
              icon={<Filter className="size-4" />}
              title={t("site.filtersSectionTitle")}
              description={t("site.filtersSectionHint")}
            >
              <SettingRow label={t("site.presetTitle")}>
                <div className="flex flex-wrap gap-2">
                  {SCAN_FILTER_PRESETS.map((preset) => (
                    <Button
                      key={preset.id}
                      type="button"
                      size="sm"
                      variant="outline"
                      title={t(preset.hintKey)}
                      onClick={() => applyScanPreset(preset.id)}
                    >
                      {t(preset.labelKey)}
                    </Button>
                  ))}
                </div>
              </SettingRow>
              {siteSettingFields
                .filter((field) => field.key !== "scan_window")
                .map((field) => (
                  <SettingRow
                    key={field.key}
                    label={field.label}
                    hint={field.hint !== field.label ? field.hint : undefined}
                    htmlFor={`${sourceKey}-${field.key}`}
                  >
                    {field.type === "number" ? (
                      <Input
                        id={`${sourceKey}-${field.key}`}
                        type="number"
                        min={1}
                        value={Number(values[field.key] ?? field.default)}
                        onChange={(e) => handleNumberChange(field.key, e.target.value)}
                        className="h-10 w-full font-mono sm:w-32"
                      />
                    ) : (
                      <Select
                        value={String(values[field.key] ?? field.default)}
                        onValueChange={(v) => handleSelectChange(field.key, v)}
                      >
                        <SelectTrigger id={`${sourceKey}-${field.key}`} className="h-10 w-full">
                          <SelectValue>
                            {(v: string) => field.options.find((o) => o.value === v)?.label ?? v}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {field.options.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </SettingRow>
                ))}
            </SettingGroup>

            <SettingGroup
              icon={<Network className="size-4" />}
              title={t("site.proxySectionTitle")}
              description={t("site.proxySectionHint")}
            >
              <SettingRow label={t("site.fieldHttpProxy")} hint={t("site.fieldHttpProxyHint")} htmlFor={`${sourceKey}-http_proxy`}>
                <Input
                  id={`${sourceKey}-http_proxy`}
                  type="text"
                  value={String(values.http_proxy ?? "")}
                  onChange={(e) => patchDraft("http_proxy", e.target.value)}
                  placeholder="http://127.0.0.1:7890"
                  className="h-10 w-full font-mono text-sm"
                />
              </SettingRow>
            </SettingGroup>
          </div>
        )}

        <DialogFooter className="-mx-0 -mb-0 rounded-none border-t px-6 py-4">
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="button" onClick={handleSave} disabled={saveMutation.isPending || values === null}>
            {saveMutation.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
