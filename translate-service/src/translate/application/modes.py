"""Adaptation modes + style profiles (P3)."""
from __future__ import annotations

import json
from typing import Any

MODES = ("full", "pov", "audio_cut", "style_clone", "reskin")

# reskin ("giữ cốt, đổi vỏ") — bối cảnh mới cho truyện, giữ nguyên cốt truyện.
RESKIN_SETTINGS: dict[str, str] = {
    "modern_urban": "modern-day urban setting (contemporary city life, phones, offices, cars)",
    "vn_historical": "Vietnamese historical setting (feudal Đại Việt era, Vietnamese names and customs)",
    "xianxia": "xianxia / cultivation world (sects, cultivation realms, immortals, spirit beasts)",
    "western_fantasy": "Western high-fantasy setting (kingdoms, knights, mages, European-style names)",
    "scifi": "science-fiction setting (spaceships, colonies, advanced technology, corporations)",
    "school": "school setting (students, teachers, classes, clubs, exams)",
}
RESKIN_INTENSITIES = ("light", "medium", "heavy")
_RESKIN_KEEP_NAMES_MAX = 100
_RESKIN_CUSTOM_MAX = 500
_RESKIN_NOTES_MAX = 1000
# Khoá nội bộ — run_job gắn bảng đổi vỏ vào mode_params lúc chạy (không lưu DB).
SKIN_MAP_PARAM = "_skin_map"

STYLE_PROFILES: dict[str, dict[str, str]] = {
    "web_novel_vn_shorts": {
        "label": "Web novel VN ngắn",
        "instruction": (
            "Viết lại bản dịch theo phong cách web novel tiếng Việt ngắn: câu gọn, "
            "nhịp nhanh, ưu tiên đối thoại, tránh tả cảnh dài."
        ),
    },
    "audiobook_narration": {
        "label": "Kể audiobook",
        "instruction": (
            "Viết lại để đọc thành tiếng: câu rõ, tránh ngoặc chú thích, "
            "giữ mạch kể liền mạch, phù hợp narration."
        ),
    },
    "neutral_literary": {
        "label": "Văn học trung tính",
        "instruction": (
            "Giữ giọng văn học trung tính, trung thành nội dung, không rút gọn quá đà."
        ),
    },
}


def validate_mode(mode: str) -> str:
    m = (mode or "full").strip().lower()
    if m not in MODES:
        raise ValueError(f"mode không hợp lệ: {mode} (full|pov|audio_cut|style_clone|reskin)")
    return m


def normalize_mode_params(mode: str, params: dict[str, Any] | None) -> dict[str, Any]:
    mode = validate_mode(mode)
    raw = dict(params or {})
    # track_story_state: cờ chung, áp dụng cho MỌI mode (kể cả full) — không
    # thuộc riêng adaptation mode nào nên xử lý tách khỏi if/else theo mode.
    track_story_state = bool(raw.get("track_story_state"))
    polish = bool(raw.get("polish"))

    if mode == "full":
        out: dict[str, Any] = {}
    elif mode == "pov":
        pov = str(raw.get("target_pov") or "first_person").strip()
        if pov not in ("first_person", "third_person", "second_person"):
            raise ValueError("target_pov phải là first_person|third_person|second_person")
        out = {"target_pov": pov}
        char = str(raw.get("viewpoint_character") or "").strip()
        if char:
            out["viewpoint_character"] = char
    elif mode == "audio_cut":
        minutes = float(raw.get("target_minutes") or 10)
        max_chars = int(raw.get("max_chars") or 12000)
        ratio = float(raw.get("keep_dialogue_ratio") or 0.7)
        out = {
            "target_minutes": max(1.0, min(minutes, 60.0)),
            "max_chars": max(500, min(max_chars, 100_000)),
            "keep_dialogue_ratio": max(0.0, min(ratio, 1.0)),
        }
    elif mode == "reskin":
        out = _normalize_reskin_params(raw)
    else:
        # style_clone
        profile = str(raw.get("style_profile_id") or "web_novel_vn_shorts").strip()
        if profile not in STYLE_PROFILES:
            raise ValueError(f"style_profile_id không hợp lệ: {profile}")
        out = {"style_profile_id": profile}

    if track_story_state:
        out["track_story_state"] = True
    if polish:
        out["polish"] = True
    return out


def _normalize_reskin_params(raw: dict[str, Any]) -> dict[str, Any]:
    setting = str(raw.get("setting") or "modern_urban").strip()
    if setting not in RESKIN_SETTINGS and setting != "custom":
        raise ValueError(
            f"setting không hợp lệ: {setting} ({'|'.join([*RESKIN_SETTINGS, 'custom'])})"
        )
    intensity = str(raw.get("intensity") or "medium").strip()
    if intensity not in RESKIN_INTENSITIES:
        raise ValueError("intensity phải là light|medium|heavy")
    out: dict[str, Any] = {"setting": setting, "intensity": intensity}
    custom = str(raw.get("custom_setting") or "").strip()
    if len(custom) > _RESKIN_CUSTOM_MAX:
        raise ValueError(f"custom_setting tối đa {_RESKIN_CUSTOM_MAX} ký tự")
    if setting == "custom":
        if not custom:
            raise ValueError("setting=custom cần custom_setting (mô tả bối cảnh mới)")
        out["custom_setting"] = custom
    names_raw = raw.get("keep_names") or []
    if isinstance(names_raw, str):
        names_raw = [x for x in names_raw.split(",")]
    if not isinstance(names_raw, list):
        raise ValueError("keep_names phải là danh sách tên")
    keep_names: list[str] = []
    for n in names_raw:
        name = str(n or "").strip()
        if name and name not in keep_names:
            keep_names.append(name)
    if len(keep_names) > _RESKIN_KEEP_NAMES_MAX:
        raise ValueError(f"keep_names tối đa {_RESKIN_KEEP_NAMES_MAX} tên")
    if keep_names:
        out["keep_names"] = keep_names
    notes = str(raw.get("notes") or "").strip()
    if len(notes) > _RESKIN_NOTES_MAX:
        raise ValueError(f"notes tối đa {_RESKIN_NOTES_MAX} ký tự")
    if notes:
        out["notes"] = notes
    return out


def reskin_setting_label(params: dict[str, Any] | None) -> str:
    p = params or {}
    setting = str(p.get("setting") or "modern_urban")
    if setting == "custom":
        return str(p.get("custom_setting") or "").strip() or "custom setting"
    return RESKIN_SETTINGS.get(setting, setting)


_RESKIN_INTENSITY_RULES = {
    "light": (
        "LIGHT: change ONLY names of people, places, items and setting-specific terms. "
        "Everything else (wording, details, professions, forms of address) stays as is."
    ),
    "medium": (
        "MEDIUM: change names, places, items/terms, plus setting details, professions, "
        "forms of address and cultural references so they fit the new setting. Keep the "
        "wording of narration and dialogue otherwise close to the original."
    ),
    "heavy": (
        "HEAVY: everything in MEDIUM, plus you may rephrase dialogue and change minor "
        "incidental details so the new setting feels native — but NEVER change, drop, add "
        "or reorder a plot beat."
    ),
}


def build_reskin_instructions(params: dict[str, Any] | None, *, already_translated: bool) -> str:
    p = params or {}
    intensity = str(p.get("intensity") or "medium")
    verb = "Rewrite the text" if already_translated else "Translate then rewrite the text"
    keep = [str(x) for x in (p.get("keep_names") or []) if str(x).strip()]
    keep_line = f" Keep these names unchanged: {', '.join(keep)}." if keep else ""
    notes = str(p.get("notes") or "").strip()
    notes_line = f" Author notes for the reskin: {notes}" if notes else ""
    return (
        f"{verb} as a RESKIN — keep the story's bones, change its shell — transplanted into a "
        f"{reskin_setting_label(p)}. MUST preserve: every plot beat in the same order, character "
        "relationships and arcs, chapter structure, point of view, emotional beats, and the intent "
        f"of every dialogue line. {_RESKIN_INTENSITY_RULES.get(intensity, _RESKIN_INTENSITY_RULES['medium'])} "
        "Every item listed under MUST-KEEP BEATS below must still appear, in the same order. "
        "Use the SKIN MAP below VERBATIM for every mapped term — never output an original "
        f"mapped name; keep names/terms consistent across chapters.{keep_line}{notes_line}"
    )


def build_skin_map_block(entries: list[tuple[str, str]] | None) -> str:
    """Bảng đổi vỏ cho đoạn đang xử lý — gốc (bản full) → tên mới."""
    if not entries:
        return ""
    lines = [f"- {orig} → {repl}" for orig, repl in entries if orig and repl]
    if not lines:
        return ""
    return (
        "SKIN MAP (original name/term in the text → replacement to use verbatim, every time; "
        "never output the original):\n" + "\n".join(lines) + "\n\n"
    )


def build_skin_map_generate_prompt(params: dict[str, Any] | None, lang_tgt: str) -> str:
    p = params or {}
    intensity = str(p.get("intensity") or "medium")
    keep = [str(x) for x in (p.get("keep_names") or []) if str(x).strip()]
    keep_line = (
        f" These names must be KEPT (replacement equals original): {', '.join(keep)}." if keep else ""
    )
    notes = str(p.get("notes") or "").strip()
    return (
        f"You design a RESKIN of a novel already translated into {lang_tgt}: same plot, new shell. "
        f"New setting: {reskin_setting_label(p)}. Intensity: {intensity} "
        f"({_RESKIN_INTENSITY_RULES.get(intensity, '')}). The user lists the story's names and terms "
        "(as they appear in the current translation, with their kind) and may include an excerpt. "
        f"For each, propose a replacement in {lang_tgt} that fits the new setting, consistent with "
        "gender, family ties and culture (relatives share surnames, etc.). Also add any other obvious "
        "recurring names/terms from the excerpt that must change. "
        f"{keep_line}{(' Notes: ' + notes) if notes else ''} "
        'Output STRICT JSON only: an array of objects {"original": <exactly as given>, '
        '"replacement": <new name/term>, "kind": "character"|"place"|"term"|"other"}. '
        "At most 80 items. No commentary, no markdown fences, JSON array only."
    )


def mode_params_hash(params: dict[str, Any] | None) -> str:
    blob = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    import hashlib

    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_mode_instructions(
    mode: str, params: dict[str, Any] | None, *, already_translated: bool = False
) -> str:
    """`already_translated=True` — text đầu vào đã là bản dịch (fork từ variant
    full), pass này chỉ adapt, không dịch — đổi động từ trong hướng dẫn cho khớp."""
    mode = validate_mode(mode)
    p = params or {}
    if mode == "full":
        return "Translate faithfully without adapting POV, length, or style."
    if mode == "pov":
        pov = p.get("target_pov", "first_person")
        char = p.get("viewpoint_character") or ""
        label = {
            "first_person": "first person (I/me)",
            "third_person": "third person",
            "second_person": "second person (you)",
        }.get(str(pov), str(pov))
        extra = f" Viewpoint character: {char}." if char else ""
        verb = "Rewrite the text" if already_translated else "After translating, rewrite"
        return (
            f"{verb} so the narration is consistently in {label}.{extra} "
            "Keep plot and dialogue meaning; keep dialogue lines themselves as close to "
            "the original wording as possible — only narration voice changes."
        )
    if mode == "audio_cut":
        minutes = p.get("target_minutes", 10)
        max_chars = p.get("max_chars", 12000)
        ratio = p.get("keep_dialogue_ratio", 0.7)
        verb = "Condense the text" if already_translated else "Translate then condense"
        return (
            f"{verb} for ~{minutes} minutes of audio narration (hard cap ~{max_chars} characters). "
            f"Prefer dialogue (keep roughly {ratio:.0%} dialogue) over description. "
            "Rewrite transitions so the result still reads smoothly (do not just delete sentences). "
            "Every item listed under MUST-KEEP BEATS below must still appear, in the same order, "
            "with character identities and relationships kept clear — never sacrifice a beat just "
            "to hit the length target."
        )
    if mode == "reskin":
        return build_reskin_instructions(p, already_translated=already_translated)
    profile_id = str(p.get("style_profile_id") or "web_novel_vn_shorts")
    inst = STYLE_PROFILES.get(profile_id, {}).get("instruction") or ""
    verb = "Adapt the text's style" if already_translated else "Translate then adapt style"
    return f"{verb}: {inst}"


def build_prior_context_block(prior_context: str) -> str:
    """Đuôi chương ngay trước (đã dịch/adapt xong) — giữ mạch truyện (POV, tình
    tiết) khi pov/audio_cut dịch từng chương độc lập, kể cả nếu chương trước do
    AI khác xử lý (fallback/pool). Best-effort: gọi rỗng nếu chưa có."""
    text = (prior_context or "").strip()
    if not text:
        return ""
    return (
        "STORY CONTEXT — tail end of the immediately preceding chapter (already "
        "adapted), for continuity only. Do NOT repeat or re-narrate it, just stay "
        "consistent with the established POV, characters and unresolved threads:\n"
        f"{text}\n\n"
    )


def build_story_state_block(story_state: str) -> str:
    """Tóm tắt trạng thái truyện LŨY KẾ (khác `build_prior_context_block` chỉ
    có đuôi chương ngay trước) — trí nhớ DÀI HẠN xuyên suốt cả sách, không phụ
    thuộc slot/model nào đã dịch các chương trước đó."""
    text = (story_state or "").strip()
    if not text:
        return ""
    return (
        "STORY STATE SO FAR — cumulative summary of the book up to (not including) "
        "this chapter, for long-range consistency (character relationships, established "
        "facts, unresolved plot threads). Use it only as context; do not repeat it "
        "verbatim in your output:\n"
        f"{text}\n\n"
    )


def build_story_state_update_prompt() -> str:
    """Prompt cho lệnh gọi PHỤ sau mỗi chương (chỉ chạy khi bật
    `track_story_state`) — cập nhật lại bản tóm tắt lũy kế cho chương kế."""
    return (
        "You maintain a running STORY STATE summary for a novel translation pipeline, "
        "used to keep later chapters consistent with earlier ones. Given the PREVIOUS "
        "state (may be empty if this is the first chapter) and the chapter that was "
        "just translated/adapted, output an UPDATED, compact running summary: key "
        "character relationships/traits established so far, important facts, and "
        "unresolved plot threads. Merge in anything new from this chapter; drop details "
        "that are no longer relevant so the summary stays short. Output at most 8 short "
        "bullet points (leading dash), no commentary, no preamble, no markdown fences."
    )


def build_glossary_seed_prompt(lang_tgt: str) -> str:
    """Trích glossary TRƯỚC khi dịch (chỉ cần vài chương nguồn, chưa có bản dịch
    mẫu nào) — sửa đúng lỗ hổng: job full ĐẦU TIÊN của 1 Work chạy suốt mà
    glossary rỗng (glossary cũ chỉ trích SAU khi xong job), nên tên nhân vật bị
    2 model/2 chương đặt khác nhau ngay từ những chương đầu."""
    return (
        f"You are preparing a translation glossary BEFORE translating a novel into "
        f"{lang_tgt}. Read the untranslated source chapters below and extract recurring "
        "character names, place names, and unique terms a translator must render "
        f"CONSISTENTLY across the whole book. For each, propose the canonical {lang_tgt} "
        "rendering to use every time it recurs (a fixed transliteration or an established "
        'translation choice). Output STRICT JSON only: an array of objects, each '
        '{"source_term": <name exactly as it appears in the SOURCE text>, '
        f'"target_term": <the {lang_tgt} rendering to use consistently>}}. '
        "Only include names/terms that recur or matter for consistency — skip generic "
        "common words. At most 20 items. No commentary, no markdown fences, JSON array only."
    )


def build_glossary_extraction_prompt() -> str:
    """Tự trích glossary từ (nguồn, bản dịch) — không bắt user gõ tay. Bám đúng
    schema glossary hiện có (source_term, target_term) bằng cách cho AI xem cả
    2 vế thay vì chỉ đoán từ bản dịch."""
    return (
        "You are compiling a translation glossary from paired (source chapter, its "
        "translation) excerpts below. Extract recurring character names, place names, "
        "and unique terms a translator must render CONSISTENTLY across the whole book. "
        "Output STRICT JSON only: an array of objects, each "
        '{"source_term": <name exactly as it appears in the SOURCE text>, '
        '"target_term": <the canonical translation to reuse for it>}. '
        "Only include names/terms that recur or matter for consistency — skip generic "
        "common words. At most 20 items. No commentary, no markdown fences, JSON array only."
    )


def build_beats_extraction_prompt() -> str:
    """Pass riêng trước audio_cut (spec 4.3: bắt buộc must_keep_beats trước khi
    cắt) — outline ngắn để pass rút gọn không nuốt twist/mất context nhân vật."""
    return (
        "You are a meticulous story editor. Read the chapter below and extract the MUST-KEEP "
        "BEATS an adapted version (abridged audio cut or reskin) must not lose: key plot turns, twists or reveals, "
        "character-defining moments, and any detail later chapters depend on. "
        "Output 4-10 short bullet points, in story order, no commentary, no preamble, no numbering "
        "beyond a leading dash."
    )


def build_names_extract_prompt(lang_src: str, lang_tgt: str) -> str:
    """Bảng duyệt tên — trích tên/thuật ngữ từ chương nguồn rải đều cả sách."""
    return (
        f"You are building a NAME REVIEW BOARD for translating a novel from {lang_src} into "
        f"{lang_tgt}. Read the untranslated source excerpts below (sampled across the whole book) "
        "and extract recurring character names, place names, and unique terms (techniques, "
        "items, organisations, titles) that must be rendered CONSISTENTLY. For each, propose the "
        f"canonical {lang_tgt} rendering and classify it. Output STRICT JSON only: an array of "
        '{"source_term": <exactly as in the SOURCE>, "target_term": <the ' + lang_tgt + ' rendering>, '
        '"kind": "character"|"place"|"term"|"other"}. Skip generic common words. At most 40 items. '
        "No commentary, no markdown fences, JSON array only."
    )
