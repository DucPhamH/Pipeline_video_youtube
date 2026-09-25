import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useT } from "@/i18n"

/**
 * Popup xác nhận trong app — thay window.confirm của trình duyệt.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirming,
  destructive = true,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  confirming?: boolean
  destructive?: boolean
  onConfirm: () => void
}) {
  const t = useT()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={confirming}
            onClick={() => onOpenChange(false)}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            disabled={confirming}
            onClick={onConfirm}
          >
            {confirming ? t("common.deleting") : (confirmLabel ?? t("common.confirmDelete"))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
