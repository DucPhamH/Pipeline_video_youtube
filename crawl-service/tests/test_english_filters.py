"""Lọc truyện tiếng Anh (Royal Road): từ khoá hoàn thành + ngôi kể cho locale "en"."""
from bs4 import BeautifulSoup

from crawl.domain.services import (
    evaluate_candidate,
    is_completed,
    matches_narration_filter,
)
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.royalroad_com_source import RoyalroadComSource

_FIRST = (
    "I woke up in a cold room. My head hurt and I could not remember my name. "
    "I looked at my hands; they were shaking. I told myself to stay calm."
)
_THIRD = (
    "He woke up in a cold room. His head hurt and he could not remember his name. "
    "She watched him from the door; her hands were shaking. He told himself to stay calm."
)


def _chapters(last_title: str, n: int = 3) -> list[ChapterRef]:
    return [
        ChapterRef(index=i, title=last_title if i == n else f"Chapter {i}", url=f"u{i}")
        for i in range(1, n + 1)
    ]


def test_en_completion_markers_not_chinese():
    assert is_completed("Chapter 80 - Epilogue", locale="en")
    assert is_completed("The End", locale="en")
    assert not is_completed("Chapter 12 - Into the Woods", locale="en")
    assert not is_completed("第十章 完结", locale="en")


def test_en_book_complete_in_chapter_title_is_not_story_complete():
    assert not is_completed("[Book 1 Complete] Chapter 40", locale="en")


def test_listing_hint_marks_completed():
    assert is_completed("Chapter 12", locale="en", listing_hint="COMPLETED")
    assert not is_completed("Chapter 12", locale="en", listing_hint="ONGOING")


def test_evaluate_candidate_uses_listing_hint():
    chapters = _chapters("Chapter 3")
    ok, _ = evaluate_candidate(chapters, 50, "completed_only", locale="en", listing_hint="COMPLETED")
    assert ok
    ok, reason = evaluate_candidate(chapters, 50, "completed_only", locale="en", listing_hint="ONGOING")
    assert not ok and "hoàn thành" in reason


def test_en_first_person_narration():
    assert matches_narration_filter(_FIRST, "first_person", locale="en")
    assert not matches_narration_filter(_THIRD, "first_person", locale="en")
    assert matches_narration_filter(_THIRD, "third_person", locale="en")


def test_en_pronouns_count_whole_words_only():
    text = "This is his kingdom, and the king rides in shining armor. He smiles."
    assert not matches_narration_filter(text, "first_person", locale="en")


def test_royalroad_listing_sets_status_hint(monkeypatch):
    html = """
    <div class="fiction-list-item row"><div class="col-sm-10">
      <h2 class="fiction-title"><a href="/fiction/21220/mother-of-learning">Mother of Learning</a></h2>
      <div class="margin-bottom-10">
        <span class="label label-default">Original</span>
        <span class="label label-default">
            COMPLETED
        </span>
        <span class="tags"><a class="label fiction-tag" href="#">Time Loop</a></span>
      </div></div></div>
    <div class="fiction-list-item row"><div class="col-sm-10">
      <h2 class="fiction-title"><a href="/fiction/1/x">Ongoing Story</a></h2>
      <div class="margin-bottom-10">
        <span class="label label-default">Original</span>
        <span class="label label-default">ONGOING</span>
      </div></div></div>
    """
    src = RoyalroadComSource()
    monkeypatch.setattr(src, "_get_soup", lambda url, **kw: BeautifulSoup(html, "lxml"))
    refs = src.list_genre_novels_page("https://www.royalroad.com/fictions/best-rated", 1)
    assert [(r.title, r.latest_chapter_title) for r in refs] == [
        ("Mother of Learning", "COMPLETED"),
        ("Ongoing Story", "ONGOING"),
    ]


def test_royalroad_complete_page_without_labels_defaults_completed(monkeypatch):
    html = """
    <div class="fiction-list-item row"><div class="col-sm-10">
      <h2 class="fiction-title"><a href="/fiction/21220/mother-of-learning">Mother of Learning</a></h2>
      <div class="margin-bottom-10"><span class="label label-default">Original</span></div>
    </div></div>
    """
    src = RoyalroadComSource()
    monkeypatch.setattr(src, "_get_soup", lambda url, **kw: BeautifulSoup(html, "lxml"))
    refs = src.list_genre_novels_page("https://www.royalroad.com/fictions/complete", 1)
    assert refs[0].latest_chapter_title == "COMPLETED"
    refs = src.list_genre_novels_page("https://www.royalroad.com/fictions/best-rated", 1)
    assert refs[0].latest_chapter_title == ""
