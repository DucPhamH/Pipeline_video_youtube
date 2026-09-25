"""Xuất Excel truyện — openpyxl + pathvalidate."""
from __future__ import annotations

import io
from dataclasses import dataclass
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Font
from pathvalidate import sanitize_filename as pv_sanitize_filename


@dataclass
class ChapterExportRow:
    title: str
    content: str


def sanitize_filename(name: str, *, max_len: int = 80) -> str:
    cleaned = pv_sanitize_filename(name.strip(), replacement_text="_") or "novel"
    cleaned = cleaned.replace(" ", "_")
    return cleaned[:max_len].strip("._") or "novel"


def content_disposition(filename: str, *, fallback: str = "export.xlsx") -> str:
    """Header Content-Disposition — filename ASCII + filename* UTF-8 (RFC 5987).

    Cùng pattern Starlette FileResponse dùng (quote + filename*).
    """
    ascii_name = fallback
    try:
        filename.encode("latin-1")
        ascii_name = filename
    except UnicodeEncodeError:
        if filename.lower().endswith(".xlsx"):
            ascii_name = fallback if fallback.endswith(".xlsx") else f"{fallback}.xlsx"
    starred = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{starred}"


def build_novel_workbook(rows: list[ChapterExportRow]) -> bytes:
    """1 sheet: cột Tiêu đề + Nội dung (tên chương cũng đứng đầu nội dung)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "chapters"
    ws.append(["Tiêu đề", "Nội dung"])
    for row in rows:
        title = (row.title or "").strip() or "(không tiêu đề)"
        content = (row.content or "").strip()
        # Nhiều người chỉ nhìn/cột Nội dung — luôn đưa tên chap lên đầu body.
        if content:
            head = content.splitlines()[0].strip() if content else ""
            body = content if head == title else f"{title}\n\n{content}"
        else:
            body = title
        ws.append([title, body])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 100
    header_font = Font(bold=True)
    for cell in ws[1]:
        cell.font = header_font
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
