"""Rule smooth — kỹ thuật port từ novel-processor."""
from crawl.domain.rule_smooth import filter_lines, smooth_chapter_text


def test_strip_ads_and_artifacts():
    raw = (
        "他走在路上。\n"
        "请收藏本站！\n"
        "点击下一章继续阅读\n"
        "Added Url\n"
        "前方有一道光。\n"
        "========\n"
        "分卷阅读1\n"
        "心里很害怕。"
    )
    result = smooth_chapter_text(raw)
    assert "请收藏" not in result.text
    assert "点击下一章" not in result.text
    assert "Added Url" not in result.text
    assert "他走在路上" in result.text
    assert "心里很害怕" in result.text
    assert result.removed_lines >= 2


def test_half_width_and_normalize():
    raw = "第１章　开始\r\n他走了。"
    result = smooth_chapter_text(raw)
    assert "第1章" in result.text or "第１章" not in result.text.replace("第1章", "")
    assert "\r" not in result.text


def test_filter_lines_keeps_long_when_max_len():
    text = "短广告请收藏\n" + ("正文很长" * 30)
    out, removed = filter_lines(text, ["请收藏"], max_len=20)
    assert removed == 1
    assert "正文很长" in out


def test_locale_ja_filters_nav():
    raw = (
        "第一話　出会い\n"
        "彼は走った。\n"
        "次の話へ\n"
        "ブックマークに追加\n"
        "彼女は笑った。"
    )
    result = smooth_chapter_text(raw, locale="ja")
    assert "次の話へ" not in result.text
    assert "ブックマーク" not in result.text
    assert "彼は走った" in result.text
    assert "彼女は笑った" in result.text


def test_locale_ko_filters():
    raw = "그는 걸었다.\n다음화 보기\n광고 클릭\n그녀는 웃었다."
    result = smooth_chapter_text(raw, locale="ko")
    assert "다음화" not in result.text
    assert "광고" not in result.text
    assert "그는 걸었다" in result.text


def test_locale_vi_filters():
    raw = "Anh ấy bước đi.\nChương sau\nQuảng cáo\nCô ấy cười."
    result = smooth_chapter_text(raw, locale="vi")
    assert "Chương sau" not in result.text
    assert "Quảng cáo" not in result.text
    assert "Anh ấy bước đi" in result.text


def test_ja_chapter_title_recognized():
    from crawl.domain.rule_smooth import CHAPTER_TITLE_RE

    assert CHAPTER_TITLE_RE.match("第一話　出会い")
    assert CHAPTER_TITLE_RE.match("제 3 화")
    assert CHAPTER_TITLE_RE.match("Chương 12")
