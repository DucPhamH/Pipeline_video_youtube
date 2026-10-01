/** Tab "Tên" của work: bảng duyệt tên + bảng đổi vỏ (variant reskin) + lịch sử
 * batch thay thế. Skin map đặt ở đây (chọn variant) để mọi chỉnh tên/vỏ nằm
 * cùng một chỗ và dùng chung lịch sử hoàn tác. */
import { useCallback, useEffect, useState } from "react"
import { useT } from "@/i18n"
import { SectionCard } from "@/components/PageChrome"
import { translateApi } from "../api"
import { useModeLabel } from "./ModeParamsFields"
import { NamesBoard } from "./NamesBoard"
import { SkinMapEditor } from "./SkinMapEditor"
import { RenameHistory } from "./RenameShared"
import { preferredProviderId, renameErrorText } from "../renameUtils"
import type { AiProvider, NameItem, RenameBatch, Work } from "../types"
import { ListSkeleton } from "@/components/Skeleton"

export function NamesTab({
  work,
  skinVariantId,
  onSkinVariantChange,
  onNamesCount,
  onCandidatesCount,
}: {
  work: Work
  skinVariantId: number | null
  onSkinVariantChange: (id: number | null) => void
  onNamesCount?: (n: number) => void
  /** Số tên còn ở trạng thái ứng viên (chưa duyệt) — cho badge trên tab. */
  onCandidatesCount?: (n: number) => void
}) {
  const t = useT()
  const modeLabel = useModeLabel()
  const [names, setNames] = useState<NameItem[]>([])
  const [namesError, setNamesError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [batches, setBatches] = useState<RenameBatch[]>([])
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [providerId, setProviderId] = useState<number | null>(null)

  const reskinVariants = work.variants.filter((v) => v.mode === "reskin")
  const skinVariant =
    reskinVariants.find((v) => v.id === skinVariantId) ?? reskinVariants[0] ?? null

  const loadNames = useCallback(async () => {
    try {
      const list = await translateApi.listNames(work.id)
      setNames(list)
      setNamesError(null)
    } catch (err) {
      setNamesError(renameErrorText(err, t))
    } finally {
      setLoaded(true)
    }
  }, [work.id, t])

  const loadBatches = useCallback(async () => {
    try {
      setBatches(await translateApi.listRenameBatches(work.id))
    } catch {
      setBatches([])
    }
  }, [work.id])

  useEffect(() => {
    void loadNames()
    void loadBatches()
    translateApi
      .listAiProviders()
      .then((list) => {
        setProviders(list)
        setProviderId((cur) => cur ?? preferredProviderId(list))
      })
      .catch(() => setProviders([]))
  }, [loadNames, loadBatches])

  useEffect(() => {
    onNamesCount?.(names.length)
  }, [names.length, onNamesCount])

  const candidates = names.filter((n) => n.status === "candidate").length
  useEffect(() => {
    if (loaded) onCandidatesCount?.(candidates)
  }, [loaded, candidates, onCandidatesCount])

  function variantLabel(id: number) {
    const v = work.variants.find((x) => x.id === id)
    return v ? `#${v.id} ${modeLabel(v.mode)}` : `#${id}`
  }

  return (
    <div className="space-y-4">
      <SectionCard className="overflow-visible" title={t("translate.namesTitle")} description={t("translate.namesHint")}>
        {!loaded ? (
          <ListSkeleton />
        ) : namesError ? (
          <p className="text-sm text-destructive">{namesError}</p>
        ) : (
          <NamesBoard
            work={work}
            names={names}
            onNamesChange={(updater) => setNames(updater)}
            reload={loadNames}
            providers={providers}
            providerId={providerId}
            onProviderChange={setProviderId}
            onApplied={() => void loadBatches()}
          />
        )}
      </SectionCard>

      {reskinVariants.length > 0 && skinVariant ? (
        <SectionCard
          className="overflow-visible"
          title={t("translate.skinMapTitle")}
          description={t("translate.skinMapHint")}
          actions={
            reskinVariants.length > 1 ? (
              <select
                aria-label={t("translate.variants")}
                className="h-9 rounded-lg border border-input bg-card px-2.5 text-sm"
                value={skinVariant.id}
                onChange={(e) => onSkinVariantChange(Number(e.target.value))}
              >
                {reskinVariants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {variantLabel(v.id)}
                  </option>
                ))}
              </select>
            ) : (
              <span className="inline-flex h-6 items-center rounded-full bg-info-soft px-2.5 text-xs font-semibold text-info">
                {variantLabel(skinVariant.id)}
              </span>
            )
          }
        >
          <SkinMapEditor
            key={skinVariant.id}
            workId={work.id}
            variant={skinVariant}
            providers={providers}
            providerId={providerId}
            onProviderChange={setProviderId}
            onApplied={() => void loadBatches()}
          />
        </SectionCard>
      ) : null}

      <SectionCard title={t("translate.renameHistory")} description={t("translate.renameHistoryHint")}>
        <RenameHistory
          workId={work.id}
          batches={batches}
          variantLabel={variantLabel}
          onUndone={() => {
            void loadBatches()
            void loadNames()
          }}
        />
      </SectionCard>
    </div>
  )
}
