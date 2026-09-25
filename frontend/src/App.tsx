import { Suspense, lazy } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { useT } from "./i18n"
import { AppLayout } from "./layout/AppLayout"

const SitesPage = lazy(() =>
  import("./features/crawl/pages/SitesPage").then((m) => ({ default: m.SitesPage })),
)
const SiteDetailPage = lazy(() =>
  import("./features/crawl/pages/SiteDetailPage").then((m) => ({ default: m.SiteDetailPage })),
)
const NovelDetailPage = lazy(() =>
  import("./features/crawl/pages/NovelDetailPage").then((m) => ({ default: m.NovelDetailPage })),
)
const SettingsPage = lazy(() =>
  import("./features/crawl/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
)
const DevToolsPage = lazy(() =>
  import("./features/crawl/pages/DevToolsPage").then((m) => ({ default: m.DevToolsPage })),
)
const TranslateWorksPage = lazy(() =>
  import("./features/translate/pages/TranslateWorksPage").then((m) => ({
    default: m.TranslateWorksPage,
  })),
)
const TranslateWorkPage = lazy(() =>
  import("./features/translate/pages/TranslateWorkPage").then((m) => ({
    default: m.TranslateWorkPage,
  })),
)
const TranslateSettingsPage = lazy(() =>
  import("./features/translate/pages/TranslateSettingsPage").then((m) => ({
    default: m.TranslateSettingsPage,
  })),
)
const TranslateJobPage = lazy(() =>
  import("./features/translate/pages/TranslateJobPage").then((m) => ({
    default: m.TranslateJobPage,
  })),
)

function PageFallback() {
  const t = useT()
  return <p className="text-sm text-muted-foreground">{t("app.loadingPage")}</p>
}

export default function App() {
  return (
    <>
      <Routes>
        <Route element={<AppLayout />}>
          <Route
            index
            element={
              <Suspense fallback={<PageFallback />}>
                <Navigate to="/sites" replace />
              </Suspense>
            }
          />
          <Route
            path="sites"
            element={
              <Suspense fallback={<PageFallback />}>
                <SitesPage />
              </Suspense>
            }
          />
          <Route
            path="sites/:sourceKey"
            element={
              <Suspense fallback={<PageFallback />}>
                <SiteDetailPage />
              </Suspense>
            }
          />
          <Route
            path="novels/:id"
            element={
              <Suspense fallback={<PageFallback />}>
                <NovelDetailPage />
              </Suspense>
            }
          />
          <Route
            path="settings"
            element={
              <Suspense fallback={<PageFallback />}>
                <SettingsPage />
              </Suspense>
            }
          />
          <Route
            path="translate"
            element={
              <Suspense fallback={<PageFallback />}>
                <TranslateWorksPage />
              </Suspense>
            }
          />
          <Route
            path="translate/settings"
            element={
              <Suspense fallback={<PageFallback />}>
                <TranslateSettingsPage />
              </Suspense>
            }
          />
          <Route
            path="translate/:workId"
            element={
              <Suspense fallback={<PageFallback />}>
                <TranslateWorkPage />
              </Suspense>
            }
          />
          <Route
            path="translate/:workId/jobs/:jobId"
            element={
              <Suspense fallback={<PageFallback />}>
                <TranslateJobPage />
              </Suspense>
            }
          />
          {/* Sửa 17/9/2026: route tự nó phải gate theo DEV giống link nav
              (AppLayout.tsx) — trước đây chỉ ẩn link, route vẫn truy cập
              được ở bản build production nếu biết/đoán URL. */}
          {import.meta.env.DEV && (
            <Route
              path="dev-tools"
              element={
                <Suspense fallback={<PageFallback />}>
                  <DevToolsPage />
                </Suspense>
              }
            />
          )}
        </Route>
      </Routes>
      <Toaster position="top-right" richColors />
    </>
  )
}
