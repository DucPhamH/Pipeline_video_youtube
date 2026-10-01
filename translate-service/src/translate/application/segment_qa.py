"""Kiểm tra nhanh output 1 segment bằng luật rẻ (không gọi LLM).

Flag:
- `refusal`: model từ chối / trả lời kiểu trợ lý thay vì bản dịch → coi là
  lỗi (segment FAILED, không cache).
- `untranslated`: còn nhiều chữ hệ nguồn (CJK) trong bản dịch sang ngôn ngữ
  chữ Latin.
- `length_ratio`: độ dài output/nguồn lệch bất thường.
- `repetition`: lặp dòng (model kẹt vòng lặp).
- `polish_failed`: lượt polish lỗi, đang giữ bản chưa polish.
- `leftover_original_name`: (reskin) output còn tên GỐC của mục bảng đổi vỏ
  (mục có replacement khác original).
Các flag ngoài `refusal` chỉ cảnh báo — segment vẫn DONE.
"""
from __future__ import annotations

import re
from collections import Counter

QA_FLAGS = (
    "refusal",
    "untranslated",
    "length_ratio",
    "repetition",
    "polish_failed",
    "leftover_original_name",
)
BLOCKING_FLAGS = frozenset({"refusal"})

_CJK_LANGS = {"zh", "ja", "ko"}
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
_LETTER_RE = re.compile(r"[^\W\d_]")

UNTRANSLATED_RATIO = 0.15
MIN_CHARS_FOR_LENGTH_CHECK = 200
_LENGTH_CHECK_MODES = ("full", "pov", "style_clone", "reskin")

# Cụm "trợ lý từ chối" rõ ràng — gặp ở đầu output là đủ kết luận.
_STRONG_REFUSAL = tuple(
    p.casefold()
    for p in (
        "as an ai",
        "as a language model",
        "i'm an ai",
        "i am an ai",
        "i can't help with",
        "i cannot help with",
        "i can't assist",
        "i cannot assist",
        "i'm sorry, but i can",
        "i am sorry, but i can",
        "i'm unable to translate",
        "i cannot translate",
        "i can't translate",
        "作为ai",
        "作为一个ai",
        "作为人工智能",
        "我无法",
        "抱歉，我不能",
        "là một ai",
        "là mô hình ngôn ngữ",
        "tôi không thể giúp",
        "tôi không thể dịch",
        "xin lỗi, nhưng tôi không thể",
        "xin lỗi, tôi không thể",
    )
)
# Cụm yếu hơn (cũng có thể là lời thoại thật) — chỉ tính khi output ngắn bất thường.
_WEAK_REFUSAL = tuple(p.casefold() for p in ("i can't", "i cannot", "tôi không thể"))
_REFUSAL_HEAD_CHARS = 200


def _lang(code: str) -> str:
    return (code or "").strip().lower().split("-")[0].split("_")[0]


def _length_bounds(lang_src: str, lang_tgt: str) -> tuple[float, float]:
    src_cjk = _lang(lang_src) in _CJK_LANGS
    tgt_cjk = _lang(lang_tgt) in _CJK_LANGS
    if src_cjk and not tgt_cjk:
        return 0.8, 12.0  # 1 chữ Hán ≈ 3-5 ký tự Latin
    if tgt_cjk and not src_cjk:
        return 0.08, 1.5
    return 0.3, 3.0


def _is_refusal(source: str, output: str) -> bool:
    head = output.strip()[:_REFUSAL_HEAD_CHARS].casefold()
    if any(p in head for p in _STRONG_REFUSAL):
        return True
    src_len = len(source.strip())
    short = src_len >= MIN_CHARS_FOR_LENGTH_CHECK and len(output.strip()) < 0.5 * src_len
    return short and any(head.startswith(p) for p in _WEAK_REFUSAL)


def _is_untranslated(output: str, lang_src: str, lang_tgt: str) -> bool:
    if _lang(lang_src) not in _CJK_LANGS or _lang(lang_tgt) in _CJK_LANGS:
        return False
    letters = len(_LETTER_RE.findall(output))
    if letters < 20:
        return False
    return len(_CJK_RE.findall(output)) / letters > UNTRANSLATED_RATIO


def _is_repetitive(output: str) -> bool:
    lines = [ln.strip() for ln in output.splitlines() if len(ln.strip()) >= 8]
    if len(lines) < 4:
        return False
    run = 1
    for prev, cur in zip(lines, lines[1:]):
        run = run + 1 if cur == prev else 1
        if run >= 4:
            return True
    _, top = Counter(lines).most_common(1)[0]
    return top >= 5 and top / len(lines) >= 0.2


def leftover_originals(output: str, skin_map: list[tuple[str, str]] | None) -> list[str]:
    """Tên gốc (đã đổi trong bảng) còn sót nguyên văn trong output — so đúng
    hoa/thường, theo ranh giới từ Unicode (khớp tên tiếng Việt có dấu)."""
    found: list[str] = []
    for item in skin_map or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        orig, repl = str(item[0] or "").strip(), str(item[1] or "").strip()
        if not orig or not repl or orig == repl:
            continue
        # Tên mới chứa tên gốc (vd "Lan" → "Lan Anh") — bỏ phần đã thay rồi mới dò.
        hay = output.replace(repl, "\0") if orig in repl else output
        if re.search(rf"(?<![\w]){re.escape(orig)}(?![\w])", hay):
            found.append(orig)
    return found


def check_output(
    *,
    source: str,
    output: str,
    lang_src: str,
    lang_tgt: str,
    mode: str = "full",
    skin_map: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Flag theo thứ tự QA_FLAGS (trừ `polish_failed` — tầng job tự gắn)."""
    source = source or ""
    output = output or ""
    flags: list[str] = []
    if _is_refusal(source, output):
        flags.append("refusal")
    if _is_untranslated(output, lang_src, lang_tgt):
        flags.append("untranslated")
    src_len = len(source.strip())
    if mode in _LENGTH_CHECK_MODES and src_len >= MIN_CHARS_FOR_LENGTH_CHECK:
        low, high = _length_bounds(lang_src, lang_tgt)
        ratio = len(output.strip()) / src_len
        if ratio < low or ratio > high:
            flags.append("length_ratio")
    if _is_repetitive(output):
        flags.append("repetition")
    if mode == "reskin" and leftover_originals(output, skin_map):
        flags.append("leftover_original_name")
    return flags


def blocking(flags: list[str]) -> list[str]:
    return [f for f in flags if f in BLOCKING_FLAGS]


class QualityRejected(RuntimeError):
    """Output bị QA chặn (vd model từ chối) — segment FAILED, không cache."""

    error_code = "refusal"

    def __init__(self, flags: list[str], output: str = ""):
        self.flags = flags
        preview = re.sub(r"\s+", " ", (output or "").strip())[:120]
        super().__init__(f"QA chặn output ({', '.join(flags)}): {preview}")
