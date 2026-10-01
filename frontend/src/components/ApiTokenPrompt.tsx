import { useEffect, useRef, useState, useSyncExternalStore } from "react"
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
import { Label } from "@/components/ui/label"
import { SectionCard } from "@/components/PageChrome"
import { useT } from "@/i18n"
import {
  clearApiToken,
  getApiToken,
  registerTokenPrompt,
  setApiToken,
  subscribeApiToken,
} from "@/api/authToken"

function useApiToken(): string {
  return useSyncExternalStore(subscribeApiToken, getApiToken, getApiToken)
}

/** Hộp nhập token khi API trả 401 — mount 1 lần ở App. */
export function ApiTokenPromptDialog() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState("")
  const resolverRef = useRef<((ok: boolean) => void) | null>(null)

  useEffect(() => {
    registerTokenPrompt(
      () =>
        new Promise<boolean>((resolve) => {
          resolverRef.current?.(false)
          resolverRef.current = resolve
          setValue(getApiToken())
          setOpen(true)
        }),
    )
    return () => {
      registerTokenPrompt(null)
      resolverRef.current?.(false)
      resolverRef.current = null
    }
  }, [])

  function settle(ok: boolean) {
    if (ok) setApiToken(value)
    resolverRef.current?.(ok)
    resolverRef.current = null
    setOpen(false)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) settle(false)
      }}
    >
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (value.trim()) settle(true)
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("auth.promptTitle")}</DialogTitle>
            <DialogDescription>{t("auth.promptHint")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="folio-token-prompt">{t("auth.tokenLabel")}</Label>
            <Input
              id="folio-token-prompt"
              type="password"
              autoComplete="off"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-10 font-mono text-sm"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => settle(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!value.trim()}>
              {t("auth.saveRetry")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Ô đổi/xoá token trong trang Settings (không gọi API — luôn hiện kể cả khi 401). */
export function ApiTokenSettingsCard() {
  const t = useT()
  const saved = useApiToken()
  // null = đang hiện token đã lưu; chỉ giữ bản nháp khi user gõ.
  const [edited, setEdited] = useState<string | null>(null)
  const draft = edited ?? saved

  return (
    <SectionCard title={t("auth.settingsTitle")} description={t("auth.settingsHint")}>
      <div className="flex max-w-xl flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1 space-y-1.5">
          <Label htmlFor="folio-token">{t("auth.tokenLabel")}</Label>
          <Input
            id="folio-token"
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(e) => setEdited(e.target.value)}
            placeholder={saved ? "" : t("auth.notSet")}
            className="h-10 w-full font-mono text-sm"
          />
        </div>
        <Button
          type="button"
          disabled={draft.trim() === saved}
          onClick={() => {
            setApiToken(draft)
            setEdited(null)
            toast.success(t("auth.saved"))
          }}
        >
          {t("common.save")}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={!saved}
          onClick={() => {
            clearApiToken()
            setEdited(null)
            toast.success(t("auth.cleared"))
          }}
        >
          {t("auth.clear")}
        </Button>
      </div>
    </SectionCard>
  )
}
