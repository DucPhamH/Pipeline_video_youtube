import { UserPlus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useT } from "@/i18n"
import type { StoryCharacter } from "./api"

/** Danh sách nhân vật (tên + vai trò), dùng chung cho trang tạo và trang soạn. */
export function CharacterFields({
  characters,
  onChange,
  disabled,
}: {
  characters: StoryCharacter[]
  onChange: (update: (prev: StoryCharacter[]) => StoryCharacter[]) => void
  disabled?: boolean
}) {
  const t = useT()
  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium">{t("write.characters")}</legend>
      {characters.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={row.name}
            aria-label={t("write.characterName")}
            placeholder={t("write.characterName")}
            className="min-w-0 flex-1"
            onChange={(e) => onChange((prev) => prev.map((c, j) => (j === i ? { ...c, name: e.target.value } : c)))}
          />
          <Input
            value={row.role}
            aria-label={t("write.characterRole")}
            placeholder={t("write.characterRole")}
            className="min-w-0 flex-1"
            onChange={(e) => onChange((prev) => prev.map((c, j) => (j === i ? { ...c, role: e.target.value } : c)))}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("write.removeCharacter")}
            title={t("write.removeCharacter")}
            onClick={() => onChange((prev) => prev.filter((_, j) => j !== i))}
          >
            <X className="size-4" />
          </Button>
        </div>
      ))}
      {characters.length < 8 ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-accent-foreground dark:text-primary"
          onClick={() => onChange((prev) => [...prev, { name: "", role: "" }])}
        >
          <UserPlus className="size-4" aria-hidden />
          {t("write.addCharacter")}
        </Button>
      ) : null}
    </fieldset>
  )
}
