import { useQuery } from "@tanstack/react-query"
import { crawlApi } from "../api"

/** Trạng thái phiên đăng nhập của 1 site (dùng chung key với thẻ site). */
export function useSiteSession(sourceKey: string) {
  return useQuery({
    queryKey: ["site-session", sourceKey],
    queryFn: () => crawlApi.getSiteSession(sourceKey),
  })
}
