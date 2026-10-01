import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
    <form
      className="space-y-3 rounded-2xl border bg-card p-5 shadow-[0_1px_2px_rgb(16_22_20/0.04)]"
      onSubmit={(e) => {
        e.preventDefault()
        if (!sourceKey || !url.trim()) return
        mutation.mutate()
      }}
    >
      <Label htmlFor="add-novel-url" className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
        {t("addNovel.label")}
      </Label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative min-w-0 flex-1">
          <Link2 className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="add-novel-url"
            type="text"
            required
            inputMode="url"
            placeholder={t("addNovel.placeholder")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-11 pl-9 font-mono text-sm"
          />
        </div>
        <Button type="submit" disabled={mutation.isPending} className="h-11">
          {mutation.isPending ? t("addNovel.submitting") : t("addNovel.submit")}
        </Button>
      </div>
    </form>
  )
}
