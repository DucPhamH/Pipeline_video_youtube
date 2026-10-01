import { useState } from "react"
import { cn } from "@/lib/utils"
import { coverColors } from "./coverColors"

/**
 * Bìa sách: ảnh thật nếu có và tải được, không thì bìa chữ (gáy tối, vòng tròn
 * trang trí, tên bằng Fraunces). Co giãn theo bề rộng khung chứa.
 */
export function BookCover({
  title,
  subtitle,
  url,
  className,
  lift = true,
}: {
  title: string
  subtitle?: string
  url?: string | null
  className?: string
  /** Nhấc lên khi hover (mặc định bật). */
  lift?: boolean
}) {
  const [broken, setBroken] = useState(false)
  const { bg, orb } = coverColors(title)
  const showImage = Boolean(url) && !broken

  return (
    <div
      className={cn(
        "@container relative aspect-[2/3] w-full overflow-hidden rounded-[6px_12px_12px_6px] shadow-(--shadow-cover)",
        lift && "lift",
        className,
      )}
      style={showImage ? undefined : { backgroundColor: bg }}
    >
      {showImage ? (
        <img
          src={url!}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          className="size-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute -top-[20%] -right-[20%] aspect-square w-[80%] rounded-full opacity-55"
            style={{ backgroundColor: orb }}
          />
          <div className="absolute inset-x-[13%] bottom-[9%] flex flex-col gap-[0.4em] text-white">
            <div aria-hidden className="h-0.5 w-[26%] bg-white/70" />
            <p
              className="font-display line-clamp-4 leading-[1.15] font-semibold break-words"
              style={{ fontSize: "clamp(10px, 13cqw, 22px)" }}
            >
              {title || "?"}
            </p>
            {subtitle !== "" ? (
              <p className="truncate text-white/75" style={{ fontSize: "clamp(9px, 7.5cqw, 12px)" }}>
                {subtitle ?? "Folio"}
              </p>
            ) : null}
          </div>
        </>
      )}
      {/* Gáy sách */}
      <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-[6%] bg-black/18" />
    </div>
  )
}
