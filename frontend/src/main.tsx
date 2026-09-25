import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter } from "react-router-dom"
import "./index.css"
import App from "./App.tsx"
import { I18nProvider } from "./i18n"
import { queryClient } from "./lib/query-client"
import { AppThemeProvider } from "./theme/AppThemeProvider"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </I18nProvider>
    </AppThemeProvider>
  </StrictMode>,
)
