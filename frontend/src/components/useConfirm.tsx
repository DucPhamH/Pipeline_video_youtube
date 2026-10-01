import { useCallback, useEffect, useRef, useState } from "react"
import { ConfirmDialog } from "@/components/ConfirmDialog"

export type ConfirmOptions = {
  title: string
  description: string
  confirmLabel?: string
  destructive?: boolean
}

/**
 * Xác nhận kiểu promise dùng ConfirmDialog — thay window.confirm:
 *   const [confirm, confirmDialog] = useConfirm()
 *   if (!(await confirm({ title, description }))) return
 *   ...render {confirmDialog} ở đâu đó trong cây.
 */
export function useConfirm() {
  const [open, setOpen] = useState(false)
  // Giữ options sau khi đóng để animation đóng không nháy text rỗng.
  const [opts, setOpts] = useState<ConfirmOptions>({ title: "", description: "" })
  const resolverRef = useRef<((ok: boolean) => void) | null>(null)

  // Unmount khi hộp đang mở → trả false để await phía gọi không treo mãi.
  useEffect(
    () => () => {
      resolverRef.current?.(false)
      resolverRef.current = null
    },
    [],
  )

  const settle = useCallback((ok: boolean) => {
    resolverRef.current?.(ok)
    resolverRef.current = null
    setOpen(false)
  }, [])

  const confirm = useCallback((next: ConfirmOptions) => {
    // Hộp cũ chưa trả lời → coi như huỷ.
    resolverRef.current?.(false)
    setOpts(next)
    setOpen(true)
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve
    })
  }, [])

  const dialog = (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) settle(false)
      }}
      title={opts.title}
      description={opts.description}
      confirmLabel={opts.confirmLabel}
      destructive={opts.destructive ?? true}
      onConfirm={() => settle(true)}
    />
  )

  return [confirm, dialog] as const
}
