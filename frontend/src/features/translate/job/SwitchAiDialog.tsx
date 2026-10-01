import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useT } from "@/i18n"
import { cn } from "@/lib/utils"
import type { AiProvider, Job } from "../types"

const SELECT_CLS = "h-10 w-full rounded-[10px] border border-input bg-card px-2.5 text-sm"

/** Đổi AI / model cho job: đang chạy → áp ngay; đã dừng → chọn rồi Resume. */
export function SwitchAiDialog({
  open,
  onOpenChange,
  job,
  providers,
  switchAiId,
  onSwitchAiId,
  switchModel,
  onSwitchModel,
  modelOptions,
  busy,
  active,
  canResume,
  onApply,
  onResume,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  job: Job
  providers: AiProvider[]
  switchAiId: number | null
  onSwitchAiId: (id: number | null) => void
  switchModel: string
  onSwitchModel: (m: string) => void
  modelOptions: string[]
  busy: boolean
  active: boolean
  canResume: boolean
  onApply: () => void
  onResume: () => void
}) {
  const t = useT()
  const slots = job.provider_slots ?? []
  const isMultiAi = slots.length >= 2
  const isFallback = isMultiAi && job.ai_mode === "fallback"
  const unchanged = switchAiId == null && (!switchModel.trim() || switchModel.trim() === job.model)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("translate.job.switchAiTitle")}</DialogTitle>
          <DialogDescription>
            {isMultiAi
              ? t(isFallback ? "translate.fallbackNoSwitchHint" : "translate.poolNoSwitchHint")
              : t("translate.switchAiHint")}
          </DialogDescription>
        </DialogHeader>

        {isMultiAi ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground">
              {t(isFallback ? "translate.fallbackJobLabel" : "translate.poolJobLabel")}
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {slots.map((s) => {
                const current = isFallback && s.slot_index === job.current_slot_index
                return (
                  <li
                    key={s.slot_index}
                    className={cn(
                      "rounded-lg border px-2.5 py-1 text-xs",
                      current ? "border-primary/40 bg-accent font-semibold text-accent-foreground" : "border-border bg-muted/50",
                    )}
                  >
                    {s.label || s.model}
                    {s.requires_api_key && !s.has_api_key ? ` — ${t("translate.noKey")}` : ""}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : (
          <div className="grid gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">{t("translate.switchAi")}</span>
              <select
                className={SELECT_CLS}
                value={switchAiId ?? ""}
                onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null
                  onSwitchAiId(id)
                  if (id != null) {
                    const p = providers.find((x) => x.id === id)
                    if (p) onSwitchModel(p.model)
                  } else {
                    onSwitchModel(job.model || "")
                  }
                }}
              >
                <option value="">{t("translate.switchAiKeep")}</option>
                {[...providers]
                  .sort((a, b) => Number(a.kind === "mock") - Number(b.kind === "mock"))
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                      {p.kind === "mock" ? ` ${t("translate.mockSuffix")}` : ""}
                      {p.requires_api_key && !p.has_api_key ? ` — ${t("translate.noKey")}` : ""}
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">{t("translate.jobModel")}</span>
              <select
                className={cn(SELECT_CLS, "font-mono text-xs")}
                value={modelOptions.includes(switchModel) ? switchModel : "__custom__"}
                onChange={(e) => {
                  const v = e.target.value
                  onSwitchModel(v === "__custom__" ? "" : v)
                }}
              >
                {modelOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value="__custom__">{t("settings.customModel")}</option>
              </select>
            </label>
            {!modelOptions.includes(switchModel) || switchModel === "" ? (
              <Input
                value={switchModel}
                onChange={(e) => onSwitchModel(e.target.value)}
                className="font-mono text-xs"
                placeholder="model-id"
                aria-label={t("translate.jobModel")}
              />
            ) : null}
          </div>
        )}

        {!isMultiAi ? (
          <DialogFooter>
            {active ? (
              <Button type="button" disabled={busy || unchanged} onClick={onApply}>
                {t("translate.applyAiMidRun")}
              </Button>
            ) : (
              <Button type="button" disabled={busy || !canResume} onClick={onResume}>
                {t("translate.job.resumeWithAi")}
              </Button>
            )}
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
