import { Suspense, lazy } from "react"
import { Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { ApiTokenPromptDialog } from "@/components/ApiTokenPrompt"
import { AppLayout } from "./layout/AppLayout"
import { PageSkeleton } from "@/components/Skeleton"
import { PlayerProvider } from "@/features/player/PlayerProvider"

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
const WriteStoriesPage = lazy(() =>
  import("./features/write/pages/WriteStoriesPage").then((m) => ({ default: m.WriteStoriesPage })),
)
const WriteStoryPage = lazy(() =>
  import("./features/write/pages/WriteStoryPage").then((m) => ({ default: m.WriteStoryPage })),
)
const HomePage = lazy(() =>
  import("./features/home/HomePage").then((m) => ({ default: m.HomePage })),
)
const ReaderPage = lazy(() =>
  import("./features/reader/ReaderPage").then((m) => ({ default: m.ReaderPage })),
)
const TtsWorksPage = lazy(() =>
  import("./features/tts/pages/TtsWorksPage").then((m) => ({ default: m.TtsWorksPage })),
)
const TtsWorkPage = lazy(() =>
  import("./features/tts/pages/TtsWorkPage").then((m) => ({ default: m.TtsWorkPage })),
)

function PageFallback() {
  return <PageSkeleton />
}

export default function App() {
  return (
    <PlayerProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route
            index
            element={
              <Suspense fallback={<PageFallback />}>
                <HomePage />
              </Suspense>
            }
          />
          <Route
            path="read/translate/:workId/:jobId"
            element={
              <Suspense fallback={<PageFallback />}>
                <ReaderPage />
              </Suspense>
            }
          />
          <Route
            path="read/write/:storyId"
            element={
              <Suspense fallback={<PageFallback />}>
                <ReaderPage />
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
          <Route
            path="write"
            element={
              <Suspense fallback={<PageFallback />}>
                <WriteStoriesPage />
              </Suspense>
            }
          />
          <Route
            path="write/:storyId"
            element={
              <Suspense fallback={<PageFallback />}>
                <WriteStoryPage />
              </Suspense>
            }
          />
          <Route
            path="tts"
            element={
              <Suspense fallback={<PageFallback />}>
                <TtsWorksPage />
              </Suspense>
            }
          />
          <Route
            path="tts/:workId"
            element={
              <Suspense fallback={<PageFallback />}>
                <TtsWorkPage />
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
      <ApiTokenPromptDialog />
      <Toaster position="top-right" richColors />
    </PlayerProvider>
  )
}
