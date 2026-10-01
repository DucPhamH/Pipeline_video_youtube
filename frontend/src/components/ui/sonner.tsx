import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "12px",
          "--success-bg": "var(--success-soft)",
          "--success-text": "var(--success)",
          "--success-border": "color-mix(in srgb, var(--success) 25%, transparent)",
          "--error-bg": "var(--danger-soft)",
          "--error-text": "var(--danger)",
          "--error-border": "color-mix(in srgb, var(--danger) 25%, transparent)",
          "--warning-bg": "var(--warning-soft)",
          "--warning-text": "var(--warning)",
          "--warning-border": "color-mix(in srgb, var(--warning) 25%, transparent)",
          "--info-bg": "var(--info-soft)",
          "--info-text": "var(--info)",
          "--info-border": "color-mix(in srgb, var(--info) 25%, transparent)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
