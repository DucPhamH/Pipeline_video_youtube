import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SectionCard, Toolbar } from "@/components/PageChrome"
import { useT } from "@/i18n"
import { ApiError } from "../../../api/client"
import { crawlApi } from "../api"

export function AddNovelForm({ sourceKey }: { sourceKey: string }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [url, setUrl] = useState("")

  const mutation = useMutation({
    mutationFn: () => crawlApi.addNovel(sourceKey, url.trim()),
    onSuccess: (result) => {
      if (!result.success) {
        toast.error(result.error ?? t("addNovel.fail"))
        return
      }
      toast.message(t("addNovel.success"))
      setUrl("")
      void queryClient.invalidateQueries({ queryKey: ["novels"] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("app.unknownError")),
  })

  return (
    <SectionCard>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!sourceKey || !url.trim()) return
          mutation.mutate()
        }}
      >
        <Toolbar>
          <Input
            type="text"
            required
            placeholder={t("addNovel.placeholder")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-10 min-w-64 flex-1"
          />
          <Button type="submit" disabled={mutation.isPending} className="h-10">
            {mutation.isPending ? t("addNovel.submitting") : t("addNovel.submit")}
          </Button>
        </Toolbar>
      </form>
    </SectionCard>
  )
}
