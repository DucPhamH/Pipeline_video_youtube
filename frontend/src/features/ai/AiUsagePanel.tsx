import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { SectionCard } from "@/components/PageChrome"
import { ListSkeleton } from "@/components/Skeleton"
import { EmptyState } from "@/components/EmptyState"
import { BarChart3 } from "lucide-react"
import { useT } from "@/i18n"
import { Progress } from "@/components/ui/progress"
import { aiApi, type UsageRow } from "./api"

const RANGES = [7, 30, 90]
const CALLERS = ["translate", "write", "tts"]

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${Math.round(n / 1000)}k`
  return n.toLocaleString()
}

function Breakdown({ title, rows, name }: { title: string; rows: UsageRow[]; name: (r: UsageRow) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.prompt_tokens + r.completion_tokens))
  return (
    <div className="min-w-0 space-y-2">
      <p className="text-sm font-medium">{title}</p>
      <ul className="space-y-2">
        {rows.map((r) => {
          const tokens = r.prompt_tokens + r.completion_tokens
          return (
            <li key={r.key} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="truncate">{name(r)}</span>
                <span className="shrink-0 font-mono text-[13px] tabular-nums text-muted-foreground">
                  {fmt(tokens)} · {r.calls}×
                </span>
              </div>
              <Progress value={(tokens / max) * 100} tone="translate" size="sm" label={name(r)} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function AiUsagePanel() {
  const t = useT()
  const [days, setDays] = useState(30)
  const { data, isLoading } = useQuery({ queryKey: ["ai-usage", days], queryFn: () => aiApi.usage(days) })
  const peak = Math.max(1, ...(data?.by_day ?? []).map((d) => d.prompt_tokens + d.completion_tokens))
  const callerName = (r: UsageRow) =>
    CALLERS.includes(r.key) ? t(`usage.caller_${r.key}`) : t("usage.caller_other")

  return (
    <SectionCard
      title={t("usage.title")}
      description={t("usage.hint")}
      actions={
        <select
          aria-label={t("usage.title")}
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="h-9 w-32 rounded-lg border border-input bg-card px-2.5 text-sm"
        >
          {RANGES.map((n) => (
            <option key={n} value={n}>
              {t("usage.days", { n })}
            </option>
          ))}
        </select>
      }
    >
      {isLoading || !data ? (
        <ListSkeleton rows={3} />
      ) : data.total.calls === 0 ? (
        <EmptyState icon={BarChart3} tone="neutral" compact title={t("usage.empty")} />
      ) : (
        <div className="space-y-6">
          <dl className="grid grid-cols-3 gap-3">
            {[
              [t("usage.calls"), data.total.calls],
              [t("usage.input"), data.total.prompt_tokens],
              [t("usage.output"), data.total.completion_tokens],
            ].map(([label, value]) => (
              <div key={String(label)} className="min-w-0 rounded-xl bg-card px-3.5 py-2.5 ring-1 ring-border">
                <dt className="truncate text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">{label}</dt>
                <dd className="mt-0.5 font-mono text-xl font-medium tracking-tight tabular-nums">{fmt(Number(value))}</dd>
              </div>
            ))}
          </dl>
          <div className="flex h-24 items-end gap-1" aria-hidden>
            {data.by_day.map((d) => (
              <div
                key={d.key}
                title={`${d.key}: ${fmt(d.prompt_tokens + d.completion_tokens)} · ${d.calls}×`}
                className="min-w-1 flex-1 rounded-t-[3px] bg-stage-translate/70 transition-colors hover:bg-stage-translate"
                style={{ height: `${Math.max(4, ((d.prompt_tokens + d.completion_tokens) / peak) * 100)}%` }}
              />
            ))}
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            <Breakdown title={t("usage.byProvider")} rows={data.by_provider} name={(r) => r.label || r.key} />
            <Breakdown title={t("usage.byCaller")} rows={data.by_caller} name={callerName} />
          </div>
        </div>
      )}
    </SectionCard>
  )
}
