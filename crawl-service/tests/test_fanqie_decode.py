from crawl.infrastructure.sources.fanqie_com_source import _PUA_CHARSET, decode_pua


def test_charset_covers_full_pua_range():
    # U+E3E8..U+E55B
    assert len(_PUA_CHARSET) == 372


def test_decode_pua_maps_known_glyphs():
    assert decode_pua("\ue3e9\ue4f3\ue40a") == "在的直"
    assert decode_pua("\ue500\ue551") == "已四"


def test_decode_pua_keeps_unmapped_and_plain_text():
    # U+E3F6 không có glyph trong font
    assert decode_pua("第1章\ue3f6abc") == "第1章\ue3f6abc"
