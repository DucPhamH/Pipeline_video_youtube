"""Parse TXT thành danh sách chương."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedChapter:
    index: int
    title: str
    text: str


_HEADING_RE = re.compile(r"(?m)^#\s+(.+)$")


def split_txt_chapters(text: str) -> list[ParsedChapter]:
    """Ưu tiên heading `# Title`; không có thì tách theo đoạn trống."""
    raw = (text or "").strip()
    if not raw:
        return []

    headings = list(_HEADING_RE.finditer(raw))
    if headings:
        chapters: list[ParsedChapter] = []
        for i, match in enumerate(headings):
            title = match.group(1).strip()
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(raw)
            body = raw[start:end].strip()
            chapters.append(ParsedChapter(index=i + 1, title=title or f"Chapter {i + 1}", text=body))
        return [c for c in chapters if c.text]

    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    if len(blocks) <= 1:
        return [ParsedChapter(index=1, title="Chapter 1", text=raw)]

    chapters = []
    for i, block in enumerate(blocks):
        lines = block.splitlines()
        if len(lines) == 1:
            chapters.append(ParsedChapter(index=i + 1, title=f"Chapter {i + 1}", text=block))
            continue
        title = lines[0].strip() or f"Chapter {i + 1}"
        body = "\n".join(lines[1:]).strip() or block
        chapters.append(ParsedChapter(index=i + 1, title=title, text=body))
    return chapters
