"""Terminal UI tiến độ crawl — Rich Live panel khi stderr là TTY.

Bật/tắt:
  CRAWL_TERMINAL_UI=1  ép bật
  CRAWL_TERMINAL_UI=0  ép tắt
  (mặc định) bật nếu stderr.isatty()

Nhiều task song song (Quét ngay + job lịch) dùng chung 1 panel thread-safe.
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import replace

from crawl.application.progress import CrawlProgress

_lock = threading.RLock()
_tasks: dict[str, CrawlProgress] = {}
_live = None
_started = False


def terminal_ui_enabled() -> bool:
    flag = os.environ.get("CRAWL_TERMINAL_UI", "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if flag in {"1", "true", "on", "yes"}:
        return True
    return sys.stderr.isatty()


def _short(text: str, limit: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _render():
    from rich.console import Group
    from rich.markup import escape
    from rich.text import Text

    if not _tasks:
        return Text.from_markup("[dim]crawl idle[/dim]")
    lines: list[Text] = [Text.from_markup("[bold]Crawl tasks[/bold]")]
    for p in list(_tasks.values()):
        if p.kind == "genre":
            goal = f"{p.discovered}/{p.scan_window}" if p.scan_window else str(p.discovered)
            pages = f"p{p.page}/{p.max_pages}" if p.max_pages else f"p{p.page}"
            head = Text()
            head.append("  ")
            head.append(escape(p.label), style="cyan")
            head.append(
                f"  {p.phase}  {pages}  ✓{p.discovered} ✗{p.rejected} ⚠{p.errors}  "
                f"sync={p.synced}  goal={goal}"
            )
            lines.append(head)
            if p.novel_title:
                ch = f"  {p.chapter_index}/{p.chapter_total} ch" if p.chapter_total else ""
                sub = Text("    → ")
                sub.append(escape(_short(p.novel_title, 42)), style="yellow")
                sub.append(ch)
                lines.append(sub)
            if p.message:
                lines.append(Text(f"    {_short(p.message, 80)}", style="dim"))
        else:
            title = _short(p.novel_title or p.label, 48)
            ch = f"{p.chapter_index}/{p.chapter_total}" if p.chapter_total else str(p.chapter_index)
            head = Text("  ")
            head.append(escape(title), style="magenta")
            head.append(f"  {p.phase}  ch {ch}  ⚠{p.errors}")
            lines.append(head)
            if p.message:
                lines.append(Text(f"    {_short(p.message, 80)}", style="dim"))
    return Group(*lines)


def _ensure_live() -> None:
    global _live, _started
    if _started or not terminal_ui_enabled():
        return
    try:
        from rich.console import Console
        from rich.live import Live
    except ImportError:
        return
    console = Console(file=sys.stderr, highlight=False)
    _live = Live(_render(), console=console, refresh_per_second=8, transient=False)
    _live.start()
    _started = True


def _refresh() -> None:
    if _live is None:
        return
    try:
        _live.update(_render())
    except Exception:
        pass


def report_progress(progress: CrawlProgress) -> None:
    """Callback gắn vào CrawlGenreUseCase / CrawlNovelUseCase — store + terminal."""
    from platform_.run_progress import publish

    publish(progress)
    if not terminal_ui_enabled():
        return
    with _lock:
        _ensure_live()
        _tasks[progress.task_id] = replace(progress)
        _refresh()


def clear_task(task_id: str) -> None:
    with _lock:
        _tasks.pop(task_id, None)
        _refresh()
