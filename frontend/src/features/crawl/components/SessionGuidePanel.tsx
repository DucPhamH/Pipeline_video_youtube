import { Alert, AlertDescription } from "@/components/ui/alert"
import { StatusPill } from "@/components/StatusPill"
import { useT } from "@/i18n"
import { type SessionGuide, COMMON_COPY_METHODS } from "../sessionGuides"

function NeedBadge({ level }: { level: SessionGuide["needsSession"][0]["level"] }) {
  const t = useT()
  const label =
    level === "required"
      ? t("guide.needRequired")
      : level === "optional"
        ? t("guide.needOptional")
        : t("guide.needNone")
  return (
    <StatusPill
      status={level}
      label={label}
      tone={level === "required" ? "warning" : level === "optional" ? "neutral" : "success"}
      live={false}
    />
  )
}

function LoginLine({ loginUrl }: { loginUrl: string }) {
  const t = useT()
  const [before, after] = t("guide.openLogin", { url: "\u0001" }).split("\u0001")
  return (
    <p className="text-muted-foreground">
      {before}
      <a
        href={loginUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent-foreground font-semibold underline-offset-2 hover:underline"
      >
        {loginUrl}
      </a>
      {after}
    </p>
  )
}

export function SessionGuidePanel({ guide }: { guide: SessionGuide }) {
  const t = useT()
  const methods = guide.copyMethods.length > 0 ? guide.copyMethods : COMMON_COPY_METHODS

  return (
    <div className="space-y-4 text-sm">
      <Alert>
        <AlertDescription>{guide.summary}</AlertDescription>
      </Alert>

      <div className="space-y-1.5">
        <p className="font-medium">{t("guide.loginOnBrowser")}</p>
        <LoginLine loginUrl={guide.loginUrl} />
        {guide.domainNote && (
          <p className="text-[13px] font-medium text-warning">{guide.domainNote}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <p className="font-medium">{t("guide.crawlWithoutSession")}</p>
        <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
          {guide.worksWithoutSession.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="space-y-1.5">
        <p className="font-medium">{t("guide.whenNeedCookie")}</p>
        <ul className="space-y-2">
          {guide.needsSession.map((row) => (
            <li key={row.task} className="rounded-lg border px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{row.task}</span>
                <NeedBadge level={row.level} />
              </div>
              <p className="mt-0.5 text-[13px] text-muted-foreground">{row.detail}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-1.5">
        <p className="font-medium">{t("guide.cookiesShouldHave")}</p>
        <ul className="space-y-1 rounded-lg border px-3 py-2 font-mono text-xs">
          {guide.keyCookies.map((c) => (
            <li key={c.name}>
              <span className="text-foreground">{c.name}</span>
              <span className="text-muted-foreground"> — {c.note}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-2">
        <p className="font-medium">{t("guide.howToCopy")}</p>
        {methods.map((method) => (
          <details
            key={method.title}
            className="rounded-lg border px-3 py-2"
            open={method.recommended}
          >
            <summary className="cursor-pointer font-medium">
              {method.title}
              {method.recommended && (
                <span className="ml-2 text-xs font-semibold text-accent-foreground">{t("guide.recommended")}</span>
              )}
            </summary>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-[13px] text-muted-foreground">
              {method.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </details>
        ))}
      </div>

      {guide.vipNote && <p className="text-xs text-muted-foreground">{guide.vipNote}</p>}

      {guide.extraNotes && guide.extraNotes.length > 0 && (
        <div className="space-y-1">
          <p className="font-medium">{t("guide.extraNotes")}</p>
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
            {guide.extraNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function GenericSessionInstructions() {
  const t = useT()
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">{t("guide.genericP1")}</p>
      <p className="text-muted-foreground">{t("guide.genericP2")}</p>
      <div className="space-y-2">
        <p className="font-medium">{t("guide.howToCopy")}</p>
        {COMMON_COPY_METHODS.map((method) => (
          <details
            key={method.title}
            className="rounded-lg border px-3 py-2"
            open={method.recommended}
          >
            <summary className="cursor-pointer font-medium">
              {method.title}
              {method.recommended && (
                <span className="ml-2 text-xs font-semibold text-accent-foreground">{t("guide.recommended")}</span>
              )}
            </summary>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-[13px] text-muted-foreground">
              {method.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </details>
        ))}
      </div>
    </div>
  )
}
