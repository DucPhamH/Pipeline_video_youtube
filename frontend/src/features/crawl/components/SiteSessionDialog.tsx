import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Eye, EyeOff, MoreHorizontal } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ActionMenu, ActionMenuItem } from "@/components/ActionMenu"
import { StatusPill } from "@/components/StatusPill"
import { useConfirm } from "@/components/useConfirm"
import { ListSkeleton } from "@/components/Skeleton"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"
import { getSessionGuide } from "../sessionGuides"
import { GenericSessionInstructions, SessionGuidePanel } from "./SessionGuidePanel"
import { useSiteSession } from "./useSiteSession"

/** Pill trạng thái phiên đăng nhập: đã lưu / cần / không cần. */
export function SessionStatusPill({ sourceKey }: { sourceKey: string }) {
  const t = useT()
  const { data: session } = useSiteSession(sourceKey)
  const guide = getSessionGuide(sourceKey)
  if (!session) return null
  if (session.configured) {
    return <StatusPill status="ready" tone="success" label={t("site.sessionHas")} />
  }
  if ((session.missing_required_cookies?.length ?? 0) > 0 || guide) {
    return <StatusPill status="needs_session" tone="warning" label={t("site.sessionNeed")} />
  }
  return null
}

function maskCookie(header: string): string {
  return header
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const eq = part.indexOf("=")
      return eq < 0 ? "••••" : `${part.slice(0, eq)}=••••••`
    })
    .join("; ")
}

export function SiteSessionDialog({
  sourceKey,
  open,
  onOpenChange,
}: {
  sourceKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const t = useT()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)
  const [reveal, setReveal] = useState(false)
  const [confirm, confirmDialog] = useConfirm()

  const { data: session, isFetching } = useSiteSession(sourceKey)

  const cookieValue = draft ?? session?.cookie_header ?? ""
  const guide = getSessionGuide(sourceKey)
  // Có cookie đã lưu và chưa sửa → che giá trị; bấm "Hiện" hoặc bắt đầu gõ mới thấy.
  const masked = !reveal && draft === null && Boolean(session?.cookie_header)

  const saveMutation = useMutation({
    mutationFn: (cookieHeader: string) => crawlApi.saveSiteSession(sourceKey, cookieHeader),
    onSuccess: () => {
      setDraft(null)
      setReveal(false)
      void queryClient.invalidateQueries({ queryKey: ["site-session", sourceKey] })
      toast.success(t("site.sessionSaved"))
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  const probeMutation = useMutation({
    mutationFn: async () => {
      if (draft !== null && draft !== (session?.cookie_header ?? "")) {
        await crawlApi.saveSiteSession(sourceKey, draft)
        setDraft(null)
      }
      return crawlApi.probeSiteSession(sourceKey)
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["site-session", sourceKey] })
      if (result.ok) toast.success(result.message)
      else toast.error(result.message)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  async function clearSession() {
    const confirmed = await confirm({
      title: t("site.clearSessionTitle"),
      description: t("site.clearSessionConfirm"),
      confirmLabel: t("site.clearSession"),
    })
    if (!confirmed) return
    setDraft("")
    saveMutation.mutate("")
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) {
          setDraft(null)
          setReveal(false)
        }
      }}
    >
      <DialogContent className="max-h-[88vh] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("site.sessionDialogTitle")}</DialogTitle>
          <DialogDescription>{t("site.sessionDialogDesc")}</DialogDescription>
        </DialogHeader>

        {isFetching && !session ? (
          <ListSkeleton />
        ) : (
          <div className="space-y-2.5 rounded-xl border bg-muted/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor={`${sourceKey}-session-cookie`} className="font-semibold">
                {t("site.cookieHeader")}
              </Label>
              <div className="flex items-center gap-2">
                <SessionStatusPill sourceKey={sourceKey} />
                {session?.cookie_header ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setReveal((v) => !v)}
                    aria-pressed={!masked}
                  >
                    {masked ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
                    {masked ? t("site.cookieReveal") : t("site.cookieHide")}
                  </Button>
                ) : null}
              </div>
            </div>
            {masked ? (
              <button
                type="button"
                id={`${sourceKey}-session-cookie`}
                onClick={() => setReveal(true)}
                className="block max-h-40 w-full overflow-y-auto rounded-lg border bg-card px-3 py-2.5 text-left font-mono text-xs break-all text-muted-foreground"
              >
                {maskCookie(session?.cookie_header ?? "")}
              </button>
            ) : (
              <Textarea
                id={`${sourceKey}-session-cookie`}
                rows={7}
                value={cookieValue}
                placeholder={t("site.cookiePlaceholder")}
                onChange={(e) => setDraft(e.target.value)}
                spellCheck={false}
                autoComplete="off"
                wrap="soft"
                className="max-h-48 overflow-x-hidden overflow-y-auto bg-card font-mono text-xs break-all whitespace-pre-wrap"
              />
            )}
            {session?.configured && (
              <p className="text-[13px] text-muted-foreground">
                {t("site.cookieSaving", {
                  count: session.cookie_names.length,
                  names:
                    session.cookie_names.slice(0, 8).join(", ") + (session.cookie_names.length > 8 ? "…" : ""),
                })}
              </p>
            )}
            {session && (session.missing_required_cookies?.length ?? 0) > 0 && (
              <p className="text-[13px] font-medium text-warning">
                {t("site.cookieMissingRequired", {
                  names: session.missing_required_cookies.join(", "),
                })}
              </p>
            )}
          </div>
        )}

        <details className="group rounded-xl border px-4 py-3">
          <summary className="cursor-pointer text-sm font-semibold">{t("site.sessionHowTo")}</summary>
          <div className="mt-3">{guide ? <SessionGuidePanel guide={guide} /> : <GenericSessionInstructions />}</div>
        </details>

        {!session?.configured && guide ? (
          <Alert className="border-warning/25 bg-warning-soft">
            <AlertTitle>{t("site.sessionAlert")}</AlertTitle>
            <AlertDescription>{guide.summary}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter className="gap-2 sm:justify-between">
          <ActionMenu
            label={<><MoreHorizontal className="size-4" aria-hidden /><span className="sr-only">{t("novel.moreActions")}</span></>}
            variant="ghost"
            size="default"
            align="start"
            showChevron={false}
            disabled={saveMutation.isPending || !session?.cookie_header}
          >
            <ActionMenuItem destructive onSelect={() => void clearSession()}>
              {t("site.clearSession")}
            </ActionMenuItem>
          </ActionMenu>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => probeMutation.mutate()}
              disabled={probeMutation.isPending || saveMutation.isPending}
            >
              {probeMutation.isPending ? t("site.probing") : t("site.probeSession")}
            </Button>
            <Button
              type="button"
              onClick={() => saveMutation.mutate(cookieValue)}
              disabled={saveMutation.isPending || draft === null}
            >
              {saveMutation.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </DialogFooter>
        {/* Lồng trong popup phiên để base-ui coi là dialog con (không đóng dialog cha). */}
        {confirmDialog}
      </DialogContent>
    </Dialog>
  )
}
