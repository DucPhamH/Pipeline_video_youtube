"""Rule-based làm mượt text chương — kỹ thuật port từ
rockbenben/novel-processor (MIT License, Copyright (c) 2026 rockbenben).

Chỉ rule/regex — không gọi AI. Dùng trước bước review người rồi mới dịch.

Dùng thư viện `regex` (PyPI) thay `re` để hỗ trợ Unicode property
(`\\p{L}`, `\\p{N}`) — nhiều người dùng, drop-in với stdlib `re`.
"""
from __future__ import annotations

from dataclasses import dataclass

import regex as re

# --- Patterns adapted from novel-processor textUtils / regex / novelUtils ---

_SENTENCE_PUNCT_ONLY = re.compile(r"^[？！。…，、；：?!.,;:]+$", re.UNICODE)
_SEPARATOR_BAR = re.compile(r"^[^\p{L}\p{N}\s]+$", re.UNICODE)
_EMOJI_PRESENTATION = re.compile(r"[\U0001F300-\U0001FAFF\uFE0F]")

CHAPTER_TITLE_RE = re.compile(
    r"^(?:"
    # ZH
    r"(?:序章|序言|引子|前言|卷首语|扉页|楔子|正文卷?|终章|后记|附录|尾声|番外篇?)"
    r"(?=$|[\s：:，,、．.·\-—（(【\[「《0-9零一二三四五六七八九十第])|"
    r"番外之|[上中下][部册](?=$|[\s：:])|"
    r"第?\s{0,4}[\d〇零一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+?\s{0,4}"
    r"(?:章|节(?!课)|卷|集(?![合和])|幕(?![前后布])|回(?![合访忆顾应答音到头来去了过])|"
    r"部(?![分赛游])|篇(?!张)|話)|"
    # JA section headers / 話
    r"(?:プロローグ|エピローグ|あとがき|前書き|序|終章|特別編|書き下ろし)"
    r"(?=$|[\s：:　．.·\-—（(【\[「『0-9])|"
    r"第\s{0,4}[\d〇零一二三四五六七八九十百千万]+?\s{0,4}話|"
    # KO
    r"(?:프롤로그|에필로그|작가의\s*말|후기|특별편)"
    r"(?=$|[\s：:．.·\-—（(\[0-9])|"
    r"제\s{0,4}\d{1,5}\s{0,4}화|"
    # VI
    r"(?:Mở đầu|Kết thúc|Lời mở đầu|Lời kết|Phụ lục|Ngoại truyện)"
    r"(?=$|[\s：:．.\-—0-9])|"
    r"Chương\s+\d{1,5}"
    r").*",
    re.IGNORECASE | re.UNICODE,
)

NUMBER_TITLE_RE = re.compile(
    r"^[ \t\u3000]{0,4}\d{1,5}([：:,.， 、_—\-]|【.{1,30}】).{0,30}$"
)
PURE_NUMBER_RE = re.compile(r"^\d+$")
NOVEL_SECTION_HEADER_RE = re.compile(
    r"^(?:作者|作家|(?:内容|作品)?简介|創作|创作|标签|タグ|소개|작가|Tác giả|Giới thiệu)[:：]?",
    re.UNICODE | re.IGNORECASE,
)
PUNCTUATION_END_RE = re.compile(
    r"(?:[。？！…”\"」』\]】)）※.!?]|\.{3,}|-{3,}|—{3,}|={3,}|＝{3,})$"
)
SPECIAL_LINE_START_RE = re.compile(
    r"^(?:[【「『\[“\"◆※].*|-{3,}|—{3,}|={3,}|＝{3,}|第.*[章节卷話]|제\s*\d+|Chương\s+\d+).*$",
    re.IGNORECASE,
)
NUMBER_START_RE = re.compile(r"^\d+")
NUMBER_END_RE = re.compile(r"\d$")

CHAPTER_MARKERS = "章节卷集幕回部篇話"
_CHAPTER_MARKER_SPACE_RE = re.compile(rf"([{CHAPTER_MARKERS}])[、：:]")
_MULTI_SPACE_CN_RE = re.compile(r"([\u4e00-\u9fa5]) {2,}([\u4e00-\u9fa5])")

# URL / downloader — mọi locale
_COMMON_FILTERS: tuple[str, ...] = (
    "Added Url",
    "http://",
    "https://",
    "www.",
)

_FILTERS_BY_LOCALE: dict[str, tuple[str, ...]] = {
    "zh": (
        "请收藏",
        "收藏本站",
        "加入书架",
        "本章完",
        "未完待续",
        "点击下一章",
        "手机阅读",
        "天才一秒记住",
        "记住网址",
        "百度搜索",
        "分卷阅读",
        "本书由【",
        "下载后",
        "请在下载后",
        "最新章节",
        "文字版下载",
    ),
    "ja": (
        "ブックマーク",
        "お気に入り",
        "広告",
        "広告掲載",
        "続きを読む",
        "小説を読む",
        "次の話へ",
        "前の話へ",
        "目次へ",
        "小説家になろう",
        "カクヨム",
        "ポイントを贈る",
        "応援する",
        "評価する",
        "作品を報告",
        "ログイン",
        "会員登録",
        "R18",
        "閲覧注意",
    ),
    "ko": (
        "작가의 말",
        "이 작품은",
        "다음화",
        "이전화",
        "목록으로",
        "관심작품",
        "좋아요",
        "추천하기",
        "소설피아",
        "무료충전",
        "코인",
        "로그인",
        "회원가입",
        "광고",
        "후원하기",
    ),
    "vi": (
        "Chương sau",
        "Chương trước",
        "Mục lục",
        "Theo dõi",
        "Đăng nhập",
        "Đăng ký",
        "Quảng cáo",
        "Truyện Full",
        "truyenfull",
        "Đánh giá",
        "Bình luận",
        "Chia sẻ",
        "Ủng hộ",
        "Nạp xu",
    ),
}


def filters_for_locale(locale: str) -> list[str]:
    key = (locale or "zh").lower().split("-")[0]
    # TW vẫn zh; fallback zh nếu lạ
    specific = _FILTERS_BY_LOCALE.get(key, _FILTERS_BY_LOCALE["zh"])
    return list(_COMMON_FILTERS) + list(specific)


# Giữ alias cũ cho test/code gọi trực tiếp
DEFAULT_FILTER_KEYWORDS: tuple[str, ...] = tuple(filters_for_locale("zh"))

_ARTIFACT_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\uE000-\uF8FF\uFFFD]"), " "),
    (re.compile(r"&nbsp;?"), " "),
    (re.compile(r"Added Url"), ""),
    (re.compile(r"【待续】"), ""),
    (re.compile(r"本文是使用怠惰小说下载器（DownloadAllContent）下载的"), ""),
    (
        re.compile(
            r"本书由【[^】]*】整理[\s\S]{0,500}?请在下载后\d+小时内删除"
            r"[\s\S]{0,500}?本群免费提取全网平台[\s\S]{0,50}?私聊群主。"
        ),
        "",
    ),
    (
        re.compile(
            r"={10,}\n?[\s\S]{0,500}?刺猬猫，飞卢，点娘，少年梦等全网小说资源每日更新"
            r"[\s\S]{0,500}?如不慎该资源侵犯了您的权益，请麻烦通知我们及时删除。\n?={10,}"
        ),
        "",
    ),
    (
        re.compile(
            r"刺猬猫，飞卢，点娘，少年梦等全网小说资源每日更新"
            r"[\s\S]{0,500}?如不慎该资源侵犯了您的权益，请麻烦通知我们及时删除。"
        ),
        "",
    ),
)


@dataclass(frozen=True)
class SmoothResult:
    text: str
    removed_lines: int
    chars_before: int
    chars_after: int


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n") if "\r" in text else text


def split_lines(text: str) -> list[str]:
    return normalize_newlines(text).split("\n") if text else []


def to_half_width(text: str) -> str:
    def _one(ch: str) -> str:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
            return chr(code - 0xFEE0)
        return ch

    return "".join(_one(c) for c in text)


def strip_novel_artifacts(text: str) -> str:
    out = text
    for pattern, repl in _ARTIFACT_REPLACEMENTS:
        out = pattern.sub(repl, out)
    return out


def is_separator_bar(line: str) -> bool:
    t = line.strip()
    if len(t) < 3:
        return False
    if _SENTENCE_PUNCT_ONLY.match(t):
        return False
    if _EMOJI_PRESENTATION.search(t):
        return False
    return bool(_SEPARATOR_BAR.match(t))


def filter_lines(
    text: str,
    filters: list[str] | tuple[str, ...],
    *,
    max_len: int = 0,
) -> tuple[str, int]:
    """Drop lines containing any filter substring. Long lines (>\n max_len) kept
    if max_len > 0 (same idea as novel-processor)."""
    removed = 0
    kept: list[str] = []
    for line in split_lines(text):
        trimmed = line.strip()
        if max_len > 0 and len(trimmed) > max_len:
            kept.append(line)
            continue
        if any(f and f in line for f in filters):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


def dedupe_adjacent_lines(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    out: list[str] = []
    for i, line in enumerate(lines):
        if i == 0 or line.strip() != lines[i - 1].strip():
            out.append(line)
    return out


def compress_newlines(text: str, max_consecutive: int = 2) -> str:
    if max_consecutive < 1:
        return re.sub(r"\n+", "\n", text)
    return re.sub(rf"\n{{{max_consecutive + 1},}}", "\n" * max_consecutive, text)


def _is_title_line(line: str) -> bool:
    return bool(CHAPTER_TITLE_RE.match(line) or NUMBER_TITLE_RE.match(line))


def smart_reflow(lines: list[str], *, enable_indent: bool = False) -> str:
    """Port rút gọn vòng smartLineBreak của novel-processor — tách đoạn theo
    tiêu đề chương / dấu câu / thanh phân cách; bỏ nav ngắn (分卷阅读 / 次の話へ…)."""
    result: list[str] = []
    indent = "\n\n\u3000\u3000" if enable_indent else "\n\n"
    nav_noise = (
        "分卷阅读",
        "次の話へ",
        "前の話へ",
        "目次へ",
        "다음화",
        "이전화",
        "Chương sau",
        "Chương trước",
    )

    for i, current in enumerate(lines):
        if any(current.startswith(p) for p in nav_noise) and len(current) <= 16:
            result.append("\n\n")
            continue
        if is_separator_bar(current):
            result.append("\n\n")
            continue

        previous = lines[i - 1].strip() if i > 0 else ""
        is_chapter = (
            _is_title_line(current)
            or bool(PURE_NUMBER_RE.match(current))
        )
        is_special_start = bool(NOVEL_SECTION_HEADER_RE.match(current))
        starts_special = bool(
            SPECIAL_LINE_START_RE.match(current) or NUMBER_START_RE.match(current)
        )
        prev_ends_punct = bool(
            PUNCTUATION_END_RE.search(previous)
            or NUMBER_END_RE.search(previous)
            or is_separator_bar(previous)
        )

        if is_chapter:
            result.append("\n\n" + current + indent)
        elif is_special_start:
            result.append("\n\n" + current)
        elif starts_special or prev_ends_punct:
            result.append(indent + current)
        else:
            result.append(current)

    text = "".join(result)
    text = re.sub(r"\n{2,}\u3000\u3000\n{2,}\u3000\u3000", "\n\n\u3000\u3000", text)
    text = re.sub(r"\n{2,}\u3000\u3000\n{2,}", "\n\n", text)
    return compress_newlines(text, 2).strip()


def smooth_chapter_text(
    text: str,
    *,
    locale: str = "zh",
    extra_filters: list[str] | None = None,
    max_filter_line_length: int = 80,
    smart_line_break: bool = True,
    enable_indent: bool = False,
    remove_duplicate_lines: bool = True,
) -> SmoothResult:
    """Pipeline: normalize → strip artifacts → half-width → filter ads (theo
    locale) → dedupe → smart reflow. Không đụng OpenCC / AI."""
    before = len(text or "")
    processed = normalize_newlines(text or "")
    processed = strip_novel_artifacts(processed)
    processed = to_half_width(processed)
    processed = _CHAPTER_MARKER_SPACE_RE.sub(r"\1 ", processed)
    processed = _MULTI_SPACE_CN_RE.sub(
        lambda m: m.group(0) if m.group(1) in CHAPTER_MARKERS else f"{m.group(1)} {m.group(2)}",
        processed,
    )

    filters = filters_for_locale(locale)
    if extra_filters:
        filters.extend(extra_filters)
    processed, removed = filter_lines(
        processed, filters, max_len=max_filter_line_length
    )

    lines = [ln.strip() for ln in split_lines(processed) if ln.strip()]
    if remove_duplicate_lines:
        lines = dedupe_adjacent_lines(lines)

    if smart_line_break:
        out = smart_reflow(lines, enable_indent=enable_indent)
    else:
        kept = [ln for ln in lines if not is_separator_bar(ln)]
        out = compress_newlines("\n".join(kept), 1).strip()

    return SmoothResult(
        text=out,
        removed_lines=removed,
        chars_before=before,
        chars_after=len(out),
    )
