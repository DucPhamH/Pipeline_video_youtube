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
    """Ưu tiên heading `# Title`; không có thì tách theo `\n\n`."""
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
        return chapters

    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    if not blocks:
        return [ParsedChapter(index=1, title="Chapter 1", text=raw)]

    chapters = []
    for i, block in enumerate(blocks):
        lines = block.splitlines()
        title = lines[0].strip() if lines else f"Chapter {i + 1}"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else block
        # Nếu block ngắn 1 dòng: dùng cả block làm text, title generic
        if len(lines) == 1:
            title = f"Chapter {i + 1}"
            body = block
        chapters.append(ParsedChapter(index=i + 1, title=title, text=body))
    return chapters
