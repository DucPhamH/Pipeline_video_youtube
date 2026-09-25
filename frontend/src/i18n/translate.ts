import type { MessageTree } from "./types"

export function lookup(tree: MessageTree, key: string): string | undefined {
  const parts = key.split(".")
  let cur: string | MessageTree | undefined = tree
  for (const part of parts) {
    if (cur == null || typeof cur === "string") return undefined
    cur = cur[part]
  }
  return typeof cur === "string" ? cur : undefined
}

export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, name: string) =>
    vars[name] !== undefined ? String(vars[name]) : `{${name}}`,
  )
}

export function createTranslator(tree: MessageTree, fallback?: MessageTree) {
  return (key: string, vars?: Record<string, string | number>): string => {
    const raw = lookup(tree, key) ?? (fallback ? lookup(fallback, key) : undefined) ?? key
    return interpolate(raw, vars)
  }
}
