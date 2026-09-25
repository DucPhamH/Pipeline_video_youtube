import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { BookOpen, Languages, Menu, Settings, Wrench, Globe2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { LanguageSwitcher } from "@/i18n/LanguageSwitcher"
import { useT } from "@/i18n"
import { ThemeToggle } from "@/theme/ThemeToggle"

export function AppLayout() {
  const t = useT()
  const [mobileOpen, setMobileOpen] = useState(false)

  const navItems = [
    { to: "/sites", label: t("nav.sites"), icon: Globe2 },
    { to: "/translate", label: t("nav.translate"), icon: Languages },
    { to: "/settings", label: t("nav.settings"), icon: Settings },
    ...(import.meta.env.DEV
      ? [{ to: "/dev-tools", label: t("nav.devTools"), icon: Wrench }]
      : []),
  ]

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-card/95 backdrop-blur-sm">
        <div className="flex h-14 items-center gap-3 px-4 sm:px-5">
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="md:hidden"
            aria-label={t("nav.openMenu")}
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="size-4" />
          </Button>
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BookOpen className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 leading-tight">
              <span className="font-heading block truncate text-base tracking-tight sm:text-lg">
                {t("app.title")}
              </span>
              <p className="hidden truncate text-xs text-muted-foreground sm:block">
                {t("app.tagline")}
              </p>
            </div>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <ThemeToggle />
            <LanguageSwitcher />
          </div>
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {/* Desktop sidebar — sát content */}
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-48 shrink-0 border-r border-border bg-card md:block lg:w-52">
          <nav className="flex flex-col gap-0.5 p-2" aria-label={t("nav.main")}>
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/sites"}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {item.label}
                </NavLink>
              )
            })}
          </nav>
        </aside>

        {/* Mobile drawer */}
        {mobileOpen ? (
          <div className="fixed inset-0 z-50 md:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/40"
              aria-label={t("nav.closeMenu")}
              onClick={() => setMobileOpen(false)}
            />
            <aside className="absolute inset-y-0 left-0 flex w-56 flex-col bg-card shadow-xl">
              <div className="flex items-center justify-between border-b border-border px-3 py-3">
                <span className="font-heading text-base">{t("app.title")}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("common.close")}
                  onClick={() => setMobileOpen(false)}
                >
                  <X className="size-4" />
                </Button>
              </div>
              <nav className="flex flex-col gap-0.5 p-2" aria-label={t("nav.main")}>
                {navItems.map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/sites"}
                      onClick={() => setMobileOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-primary text-primary-foreground"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        )
                      }
                    >
                      <Icon className="size-4 shrink-0" aria-hidden />
                      {item.label}
                    </NavLink>
                  )
                })}
              </nav>
            </aside>
          </div>
        ) : null}

        {/* Content bám sát sidebar, không căn giữa tạo khoảng trống */}
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
