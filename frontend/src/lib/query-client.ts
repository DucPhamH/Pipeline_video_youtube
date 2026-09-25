import { QueryClient } from "@tanstack/react-query"

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
})

export const queryKeys = {
  sites: (params: { search?: string; accessKind?: string; region?: string; offset?: number; limit?: number } = {}) =>
    ["sites", params] as const,
  genres: (params: {
    sourceKey?: string
    search?: string
    enabled?: boolean
    lastRunStatus?: string
    offset?: number
    limit?: number
  } = {}) => ["genres", params] as const,
  novels: (params: {
    sourceKey?: string
    status?: string
    search?: string
    isManual?: boolean
    genreId?: number
    offset?: number
    limit?: number
  }) => ["novels", params] as const,
  novel: (id: number) => ["novel", id] as const,
  chapters: (
    novelId: number,
    params: {
      status?: string
      search?: string
      reviewed?: boolean
      has_cleaned?: boolean
      offset?: number
      limit?: number
    } = {},
  ) => ["chapters", novelId, params] as const,
  settings: ["settings"] as const,
  genreProgress: (id: number) => ["genre-progress", id] as const,
}
