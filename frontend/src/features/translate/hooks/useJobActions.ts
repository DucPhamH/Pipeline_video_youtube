/** Hành động job dùng chung: Work overview (hàng biến thể) + Job Detail. */
import { toast } from "sonner"
import { ApiError } from "@/api/client"
import { useT } from "@/i18n"
import { translateApi } from "../api"
import type { Job, ProviderConfig } from "../types"

export const jobIsActive = (job: Job | null | undefined) =>
  job != null && ["queued", "running"].includes(job.status)

export const jobCanResume = (job: Job | null | undefined) =>
  job != null &&
  !jobIsActive(job) &&
  (job.failed_segments > 0 || job.done_segments < job.total_segments)

export const jobCanDelete = (job: Job | null | undefined) =>
  job != null && ["completed", "failed", "cancelled"].includes(job.status)

export function useJobActions() {
  const t = useT()

  function reportError(err: unknown) {
    toast.error(err instanceof ApiError ? err.message : t("app.unknownError"))
  }

  async function pause(jobId: number): Promise<Job | null> {
    try {
      const j = await translateApi.pauseJob(jobId)
      toast.message(t("translate.jobPaused"))
      return j
    } catch (err) {
      reportError(err)
      return null
    }
  }

  async function resume(jobId: number, cfg?: ProviderConfig): Promise<Job | null> {
    try {
      const j = await translateApi.resumeJob(jobId, cfg)
      toast.success(t("translate.jobResumed"))
      return j
    } catch (err) {
      reportError(err)
      return null
    }
  }

  async function remove(jobId: number, confirmMessage?: string): Promise<boolean> {
    if (confirmMessage && !window.confirm(confirmMessage)) return false
    try {
      await translateApi.deleteJob(jobId)
      toast.success(t("translate.jobDeleted"))
      return true
    } catch (err) {
      reportError(err)
      return false
    }
  }

  async function applyProvider(jobId: number, cfg: ProviderConfig): Promise<Job | null> {
    try {
      const j = await translateApi.patchJobProvider(jobId, cfg)
      toast.success(t("translate.modelApplied"))
      return j
    } catch (err) {
      reportError(err)
      return null
    }
  }

  /** "Dịch lại": còn segment failed/pending → resume; job đã completed sạch →
   * xóa rồi tạo job mới (không bao giờ start thẳng lên 1 variant đã có job). */
  async function retranslate(
    job: Job,
    variantId: number,
    cfg?: ProviderConfig,
  ): Promise<Job | null> {
    if (jobCanResume(job)) {
      return resume(job.id, cfg)
    }
    const ok = await remove(job.id)
    if (!ok) return null
    try {
      const j = await translateApi.startJob(variantId, cfg)
      toast.success(t("translate.jobStarted"))
      return j
    } catch (err) {
      reportError(err)
      return null
    }
  }

  return { pause, resume, remove, applyProvider, retranslate }
}
