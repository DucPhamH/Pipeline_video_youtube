"""Test domain logic thuần — không DB, không HTTP, chạy cực nhanh.
Đúng tinh thần tách domain/ ra riêng: test được logic nghiệp vụ mà không
cần mock hạ tầng."""
from crawl.domain.services import (
    chapter_failure_counts_toward_block,
    evaluate_candidate,
    first_person_ratio,
    is_completed,
    is_first_person_narrated,
    validate_chapter_content,
)
from crawl.domain.value_objects import ChapterRef


def _chapters(*titles: str) -> list[ChapterRef]:
    """Helper dựng nhanh 1 danh sách ChapterRef chỉ cần title (test không
    quan tâm url) — evaluate_candidate() chỉ đọc index cuối + title cuối."""
    return [ChapterRef(index=i, title=t, url=f"u{i}") for i, t in enumerate(titles, start=1)]


def test_chapter_failure_classification():
    assert chapter_failure_counts_toward_block("Nội dung quá ngắn") is True
    assert chapter_failure_counts_toward_block("Chương VIP — cần cookie") is False
    assert chapter_failure_counts_toward_block("HTTP 503 cloudflare") is True
    assert chapter_failure_counts_toward_block("[qidian] VIP chưa mua — cookie") is False
    assert chapter_failure_counts_toward_block("OCR không đọc được chữ từ ảnh") is False
    assert chapter_failure_counts_toward_block("Chương khoá VIP/cần cookie (marker='付费章节')") is False


def test_validate_rejects_too_short():
    ok, reason = validate_chapter_content("ngắn")
    assert not ok
    assert reason


def test_validate_rejects_block_marker():
    text = "请稍后" + "测试内容" * 30
    ok, reason = validate_chapter_content(text)
    assert not ok


def test_validate_bare_yan_zheng_in_story_is_ok():
    # "验证" đơn lẻ thường gặp trong truyện — không được coi là challenge.
    text = "他想验证自己的想法是否正确，于是继续往前走。" * 8
    ok, reason = validate_chapter_content(text)
    assert ok, reason
    assert "验证" in text


def test_validate_rejects_captcha_phrase():
    text = "请完成验证后继续访问" + "测试内容" * 30
    ok, reason = validate_chapter_content(text)
    assert not ok
    assert "验证" in (reason or "")


def test_validate_rejects_low_chinese_ratio():
    text = "abcdefgh " * 20  # đủ dài nhưng không phải tiếng Trung
    ok, reason = validate_chapter_content(text)
    assert not ok


def test_validate_accepts_real_chinese_text():
    text = "今天天气很好，少年走在山间小道上，心情格外愉快。" * 5
    ok, reason = validate_chapter_content(text)
    assert ok
    assert reason is None


def test_is_completed_detects_markers():
    assert is_completed("第一百章 大结局")
    assert is_completed("尾声")
    assert not is_completed("第五十章 危机四伏")


def test_evaluate_candidate_accepts_short_and_complete():
    chapters = _chapters(*[f"第{i}章" for i in range(1, 10)], "第十章 大结局")
    ok, reason = evaluate_candidate(chapters, max_chapters_per_story=50)
    assert ok


def test_evaluate_candidate_rejects_too_long():
    chapters = _chapters(*[f"第{i}章" for i in range(1, 90)], "第九十章 大结局")
    ok, reason = evaluate_candidate(chapters, max_chapters_per_story=50)
    assert not ok
    assert "dài hơn ngưỡng" in reason


def test_evaluate_candidate_rejects_not_completed():
    # Mặc định completion_filter="completed_only" (giữ hành vi cũ) — chưa
    # hoàn thành thì bị loại.
    chapters = _chapters(*[f"第{i}章" for i in range(1, 11)])
    ok, reason = evaluate_candidate(chapters, max_chapters_per_story=50)
    assert not ok
    assert "hoàn thành" in reason


def test_evaluate_candidate_accepts_single_chapter_short_as_completed():
    # Syosetu 短編: 1 chương, tiêu đề không có 完結 — vẫn coi đã xong (ja).
    chapters = _chapters("ヒロインをいじめ尽くす正妻に転生したことを思い出したのでスローライフ")
    ok, reason = evaluate_candidate(
        chapters, max_chapters_per_story=50, completion_filter="completed_only", locale="ja"
    )
    assert ok, reason
    assert is_completed(chapters[0].title, locale="ja", total_chapters=1)


def test_evaluate_candidate_zh_single_chapter_not_auto_completed():
    chapters = _chapters("第一章 开端")
    ok, reason = evaluate_candidate(
        chapters, max_chapters_per_story=50, completion_filter="completed_only", locale="zh"
    )
    assert not ok
    assert "hoàn thành" in reason


def test_is_completed_ja_markers_without_bare_kan():
    assert is_completed("最終話 完結", locale="ja")
    assert is_completed("連載終了", locale="ja")
    assert not is_completed("完全に終わった話", locale="ja")  # không match "完" lẻ


def test_evaluate_candidate_completion_filter_any_accepts_ongoing():
    chapters = _chapters(*[f"第{i}章" for i in range(1, 11)])
    ok, _ = evaluate_candidate(chapters, max_chapters_per_story=50, completion_filter="any")
    assert ok


def test_evaluate_candidate_completion_filter_ongoing_only_rejects_completed():
    chapters = _chapters(*[f"第{i}章" for i in range(1, 4)], "第4章 大结局")
    ok, reason = evaluate_candidate(chapters, max_chapters_per_story=50, completion_filter="ongoing_only")
    assert not ok
    assert "đang ra" in reason


def test_evaluate_candidate_rejects_empty_chapter_list():
    ok, reason = evaluate_candidate([], max_chapters_per_story=50)
    assert not ok
    assert "rỗng" in reason


def test_evaluate_candidate_rejects_empty_even_with_filter_any():
    ok, reason = evaluate_candidate([], max_chapters_per_story=50, completion_filter="any")
    assert not ok
    assert "rỗng" in reason


def test_first_person_ratio_all_first_person():
    text = "我走在路上，我看见前方有一道光，我心里很害怕，我不知道该怎么办。"
    assert first_person_ratio(text) == 1.0
    assert is_first_person_narrated(text)


def test_first_person_ratio_all_third_person():
    text = "他走在路上，她看见前方有一道光，他们心里很害怕，她们不知道该怎么办。"
    assert first_person_ratio(text) == 0.0
    assert not is_first_person_narrated(text)


def test_first_person_ratio_mixed_below_threshold():
    text = "我看着他和她说话，他们转身离开，我却站在原地，我不知所措。"
    # Đếm tay: 我=3; 他=2 (1 lần đứng riêng + 1 lần là tiền tố của "他们");
    # 她=1 -> first=3, third=3 -> ratio=0.5, dưới ngưỡng mặc định 0.6.
    assert first_person_ratio(text) == 0.5
    assert not is_first_person_narrated(text, threshold=0.6)


def test_first_person_ratio_no_pronouns_defaults_to_not_first_person():
    text = "今天天气很好，山间小路上很安静，没有人经过。"
    assert first_person_ratio(text) == 0.0
    assert not is_first_person_narrated(text)


def test_matches_narration_no_pronouns_rejects_third_person():
    from crawl.domain.services import matches_narration_filter

    text = "今天天气很好，山间小路上很安静，没有人经过。"
    assert matches_narration_filter(text, "third_person", locale="zh") is False
    assert matches_narration_filter(text, "first_person", locale="zh") is False


def test_ja_first_person_pronouns():
    from crawl.domain.services import matches_narration_filter

    text = "私は山道を歩いていた。僕の心はとても不安だった。" * 5
    assert matches_narration_filter(text, "first_person", locale="ja") is True
