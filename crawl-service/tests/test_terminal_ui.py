"""Terminal progress reporter — không đụng Rich Live khi UI tắt."""
from crawl.application.progress import CrawlProgress
from platform_.terminal_ui import report_progress, terminal_ui_enabled


def test_report_progress_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("CRAWL_TERMINAL_UI", "0")
    assert terminal_ui_enabled() is False
    report_progress(
        CrawlProgress(
            task_id="genre:1",
            kind="genre",
            label="demo/fantasy",
            phase="listing",
            page=1,
            max_pages=3,
            scan_window=5,
        )
    )


def test_crawl_progress_fields():
    p = CrawlProgress(
        task_id="novel:9",
        kind="novel",
        label="novel#9",
        phase="crawling",
        novel_title="短編",
        chapter_index=2,
        chapter_total=7,
    )
    assert p.chapter_index == 2
    assert p.kind == "novel"
