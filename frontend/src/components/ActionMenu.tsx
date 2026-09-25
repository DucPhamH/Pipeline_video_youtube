import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** Menu nút đơn giản — không thêm dependency dropdown. */
export function ActionMenu({
  label,
  variant = "outline",
  size = "sm",
  disabled,
  align = "end",
  showChevron = true,
  children,
}: {
  label: ReactNode
  variant?: "outline" | "secondary" | "default" | "ghost"
  size?: "sm" | "default"
  disabled?: boolean
  align?: "start" | "end"
  showChevron?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDoc)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={rootRef}>
      <Button
        type="button"
        size={size}
        variant={variant}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
        {showChevron ? <ChevronDown className="size-3.5 opacity-70" aria-hidden /> : null}
      </Button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          className={cn(
            "absolute z-50 mt-1 min-w-[11rem] rounded-lg border bg-popover p-1 text-popover-foreground shadow-md",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          <div
            className="flex flex-col"
            onClick={() => setOpen(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setOpen(false)
            }}
          >
            {children}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function ActionMenuItem({
  children,
  onSelect,
  disabled,
  destructive,
}: {
  children: ReactNode
  onSelect: () => void
  disabled?: boolean
  destructive?: boolean
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      className={cn(
        "flex w-full rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
        destructive
          ? "text-destructive hover:bg-destructive/10"
          : "hover:bg-accent hover:text-accent-foreground",
        disabled && "pointer-events-none opacity-50",
      )}
      onClick={onSelect}
    >
      {children}
    </button>
  )
}
