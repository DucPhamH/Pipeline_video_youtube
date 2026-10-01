"""Tách người kể / lời thoại, rồi cắt đoạn ngắn cho engine."""
from __future__ import annotations

import re

MAX_CHUNK = 500

_QUOTED = re.compile(r"「[^」]*」|『[^』]*』|“[^”]*”|\"[^\"\n]*\"")
_SENTENCE = re.compile(r"(?<=[。！？.!?])\s+")
# Thoại kiểu gạch đầu dòng (hay gặp trong truyện tiếng Việt): "- Đi thôi!", "-Đi thôi!" hoặc
# "— Đi thôi — hắn nói — nhanh lên." Không có khoảng trắng sau gạch thì phải là chữ ngay sau
# (tránh "-5 độ", "---").
_DASH_LINE = re.compile(r"^[ \t]*[-–—](?:[ \t]+([^\s\-–—].*)|([^\W\d_].*))$")
_DASH_SEP = re.compile(r"(\s[-–—]\s)")
# Đoạn sau gạch giữa câu là lời dẫn khi có động từ nói (viết thường) trong vài chữ đầu:
# "Lan hỏi.", "hắn nói", "cô thì thầm". "- Không - không được!" thì không có → vẫn là thoại.
_SPEECH_TAG = re.compile(
    r"^(?:\S+\s+){0,3}(?:nói|hỏi|đáp|cười|hét|quát|gắt|thét|la|kêu|gọi|bảo|thì thầm|lẩm bẩm|"
    r"trả lời|lên tiếng|cất tiếng|thở dài|ngắt lời|xen vào|giải thích|nhắc|rít|gầm|lầm bầm|"
    r"khẽ nói|nghĩ|tiếp lời|đáp lại|reo|than|mắng|hừ|gằn giọng)(?![^\W\d_])"
)
_SENTENCE_MARK = re.compile(r"[.!?…:;,。！？\"“”「」]")
# Dòng gạch ngắn, không dấu câu, đứng thành cụm → danh sách ("- Kiếm\n- Khiên"), không phải thoại.
_LIST_MAX_WORDS = 6


def normalize(text: str) -> str:
    text = (text or "").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_roles(text: str, *, dialogue: bool) -> list[tuple[str, str]]:
    """Câu trong ngoặc kép hoặc dòng mở bằng gạch ngang là lời thoại. Không đoán tên nhân vật."""
    raw = normalize(text)
    if not raw:
        return []
    if not dialogue:
        return [("narrator", raw)]
    lines = raw.split("\n")
    bodies = [_dash_body(line) for line in lines]
    listed = _list_lines(bodies)
    parts: list[tuple[str, str]] = []
    buf: list[str] = []
    for i, line in enumerate(lines):
        body = bodies[i]
        if body is None or i in listed:
            buf.append(line)
            continue
        if buf:
            parts.extend(_split_quoted("\n".join(buf)))
            buf = []
        for role, piece in _dash_pieces(body):
            if role == "dialogue":
                parts.extend(_split_quoted(piece, inside="dialogue"))
            else:
                parts.extend(_split_quoted(piece))
    if buf:
        parts.extend(_split_quoted("\n".join(buf)))
    return parts or [("narrator", raw)]


def _dash_body(line: str) -> str | None:
    match = _DASH_LINE.match(line)
    if match is None:
        return None
    return (match.group(1) or match.group(2) or "").strip() or None


def _list_lines(bodies: list[str | None]) -> set[int]:
    """Cụm ≥2 dòng gạch liền nhau, dòng nào cũng ngắn và không dấu câu → danh sách."""
    out: set[int] = set()
    run: list[int] = []
    for i, body in enumerate([*bodies, None]):
        looks_item = (
            body is not None
            and len(body.split()) <= _LIST_MAX_WORDS
            and not _SENTENCE_MARK.search(body)
        )
        if looks_item:
            run.append(i)
            continue
        if len(run) >= 2:
            out.update(run)
        run = []
    return out


def _dash_pieces(body: str) -> list[tuple[str, str]]:
    """Tách "A — hắn nói — B." thành thoại A, dẫn "hắn nói", thoại B.

    Gạch giữa câu chỉ mở lời dẫn khi đoạn sau là lời dẫn (_SPEECH_TAG); không thì gộp lại vào thoại.
    """
    tokens = _DASH_SEP.split(body)
    out: list[list[str]] = [["dialogue", tokens[0]]]
    for k in range(1, len(tokens), 2):
        sep, seg = tokens[k], tokens[k + 1]
        role, text = out[-1]
        if role == "narrator":
            out.append(["dialogue", seg])
        elif _is_speech_tag(seg):
            out.append(["narrator", seg])
        else:
            out[-1][1] = text + sep + seg
    return [(role, text.strip()) for role, text in out if text.strip()]


def _is_speech_tag(seg: str) -> bool:
    seg = seg.strip()
    if not seg or seg[-1] in "!?":
        return False
    return bool(_SPEECH_TAG.match(seg))


def _split_quoted(raw: str, *, inside: str = "narrator") -> list[tuple[str, str]]:
    raw = raw.strip()
    if not raw:
        return []
    parts: list[tuple[str, str]] = []
    pos = 0
    for match in _QUOTED.finditer(raw):
        before = raw[pos : match.start()].strip()
        if before:
            parts.append((inside, before))
        inner = match.group(0)[1:-1].strip()
        if inner:
            parts.append(("dialogue", inner))
        pos = match.end()
    tail = raw[pos:].strip()
    if tail:
        parts.append((inside, tail))
    return parts


def chunk_text(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    if len(raw) <= MAX_CHUNK:
        return [raw]
    out: list[str] = []
    buf = ""
    for sent in _SENTENCE.split(raw):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) > MAX_CHUNK:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_hard_cut(sent))
            continue
        if buf and len(buf) + 1 + len(sent) > MAX_CHUNK:
            out.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip() if buf else sent
    if buf:
        out.append(buf)
    return out


def _hard_cut(text: str) -> list[str]:
    out: list[str] = []
    rest = text.strip()
    while len(rest) > MAX_CHUNK:
        cut = rest.rfind(" ", 0, MAX_CHUNK)
        if cut < MAX_CHUNK // 2:
            cut = MAX_CHUNK
        piece = rest[:cut].strip()
        if piece:
            out.append(piece)
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def pieces_for(text: str, dialogue_voice: str) -> list[tuple[str, str]]:
    roles = split_roles(text, dialogue=bool((dialogue_voice or "").strip()))
    out: list[tuple[str, str]] = []
    for role, body in roles:
        for chunk in chunk_text(body):
            out.append((role, chunk))
    return out
