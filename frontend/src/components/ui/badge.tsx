import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const badgeVariants = cva(
  "group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1.5 overflow-hidden rounded-full border border-transparent px-2.5 text-xs font-semibold whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 aria-invalid:border-destructive [&>svg]:pointer-events-none [&>svg]:size-3.5!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        destructive: "bg-danger-soft text-danger",
        outline: "border-border text-foreground",
        ghost: "hover:bg-muted hover:text-muted-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        success: "bg-success-soft text-success",
        warning: "bg-warning-soft text-warning",
        danger: "bg-danger-soft text-danger",
        info: "bg-info-soft text-info",
        neutral: "bg-muted text-muted-foreground",
        collect: "bg-stage-collect-soft text-stage-collect",
        translate: "bg-stage-translate-soft text-success",
        listen: "bg-stage-listen-soft text-warning",
        write: "bg-stage-write-soft text-danger",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

const DOT_TONE: Record<string, string> = {
  success: "bg-success",
  warning: "bg-warning-dot",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-muted-foreground",
  destructive: "bg-danger",
}

function Badge({
  className,
  variant = "default",
  live = false,
  dot = false,
  render,
  children,
  ...props
}: useRender.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & {
    /** Chấm nhịp thở trước nhãn (việc đang chạy). */
    live?: boolean
    /** Chấm tĩnh trước nhãn. */
    dot?: boolean
  }) {
  const showDot = live || dot
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
        children: (
          <>
            {showDot ? (
              <span
                aria-hidden
                className={cn(
                  "size-1.5 shrink-0 rounded-full",
                  DOT_TONE[variant ?? ""] ?? "bg-current",
                  live && "dot-live",
                )}
              />
            ) : null}
            {children}
          </>
        ),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
