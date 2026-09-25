"""OpenAI-compatible chat completions + mock translator."""
from __future__ import annotations

import re
import time
from typing import Any, Protocol

import httpx

from translate.application.modes import (
    build_beats_extraction_prompt,
    build_mode_instructions,
    build_prior_context_block,
    build_story_state_block,
    build_story_state_update_prompt,
)

GlossaryPairs = list[tuple[str, str, bool]]  # source, target, protected


class Translator(Protocol):
    def translate(
        self,
        *,
        text: str,
        lang_src: str,
        lang_tgt: str,
        title: str = "",
        glossary: GlossaryPairs | None = None,
        mode: str = "full",
        mode_params: dict[str, Any] | None = None,
        already_translated: bool = False,
        prior_context: str = "",
        story_state: str = "",
    ) -> str: ...

    def summarize_state(self, *, previous_state: str, new_chapter_text: str) -> str: ...


_MAX_SPLIT_DEPTH = 4  # tối đa chia thành 2^4 = 16 mảnh — chặn đệ quy vô hạn
_MIN_SPLITTABLE_CHARS = 500  # mảnh dưới ngưỡng này thì thôi, raise lỗi gốc luôn
_CONTEXT_TAIL_CHARS_LOCAL = 700  # đuôi nửa trước dùng làm ngữ cảnh cho nửa sau

_TOO_LARGE_MARKERS = (
    "request too large",
    "reduce your message size",
    "reduce max_tokens",
    "context_length_exceeded",
    "maximum context length",
)


def _is_too_large_text(text: str) -> bool:
    msg = text.lower()
    return any(marker in msg for marker in _TOO_LARGE_MARKERS)


def _looks_too_large(exc: Exception) -> bool:
    """Lỗi "request quá to so với hạn mức" (TPM/OTPM per-request, hoặc vượt
    context window model) — khác 429/5xx TẠM THỜI đã tự retry trong `_chat`,
    lỗi này KHÔNG BAO GIỜ tự hết nếu gửi lại y hệt, chỉ hết khi payload nhỏ
    lại — nên mới đáng để tự chia đôi thử tiếp, chứ không phải mọi lỗi."""
    return _is_too_large_text(str(exc))


def _split_in_half(text: str) -> tuple[str, str]:
    """Cắt gần giữa văn bản theo ranh giới đoạn (ưu tiên `\\n\\n`, sa xuống
    `\\n` nếu chỉ có 1 đoạn) — không bao giờ cắt giữa câu/dòng nếu tránh được.
    Trả `("", "")`-kiểu (right rỗng) nếu không cắt được (text quá ngắn/liền mạch)."""
    for sep in ("\n\n", "\n"):
        parts = text.split(sep)
        if len(parts) < 2:
            continue
        total = len(text)
        running = 0
        split_at = None
        for i, p in enumerate(parts):
            running += len(p) + len(sep)
            if running >= total / 2:
                split_at = i + 1
                break
        if split_at is None or split_at <= 0 or split_at >= len(parts):
            split_at = max(1, len(parts) // 2)
        left = sep.join(parts[:split_at])
        right = sep.join(parts[split_at:])
        if left.strip() and right.strip():
            return left, right
    return text, ""


def _glossary_block(glossary: GlossaryPairs | None) -> str:
    if not glossary:
        return ""
    lines = []
    for src, tgt, protected in glossary:
        lock = " [PROTECTED — keep exact]" if protected else ""
        lines.append(f"- {src} → {tgt}{lock}")
    return (
        "Glossary (apply consistently; protected terms must appear exactly as target):\n"
        + "\n".join(lines)
        + "\n\n"
    )


class MockTranslator:
    """MVP test/dev — marker [lang][+mode]; protected glossary; audio_cut truncate."""

    def translate(
        self,
        *,
        text: str,
        lang_src: str,
        lang_tgt: str,
        title: str = "",
        glossary: GlossaryPairs | None = None,
        mode: str = "full",
        mode_params: dict[str, Any] | None = None,
        already_translated: bool = False,
        prior_context: str = "",
        story_state: str = "",
    ) -> str:
        out = text or ""
        if glossary:
            for src, tgt, protected in sorted(glossary, key=lambda x: -len(x[0])):
                if protected and src and tgt and src in out:
                    out = out.replace(src, tgt)
        params = mode_params or {}
        if mode == "audio_cut":
            max_chars = int(params.get("max_chars") or 12000)
            if len(out) > max_chars:
                out = out[:max_chars].rstrip() + "…"
        if mode == "pov":
            pov = params.get("target_pov") or "first_person"
            out = f"(pov:{pov}) {out}"
        if mode == "style_clone":
            pid = params.get("style_profile_id") or "web_novel_vn_shorts"
            out = f"(style:{pid}) {out}"
        mode_tag = "" if mode == "full" else f"+{mode}"
        prefix = f"[fork{mode_tag}]" if already_translated else f"[{lang_tgt}{mode_tag}]"
        return f"{prefix} " + out

    def summarize_state(self, *, previous_state: str, new_chapter_text: str) -> str:
        """Mock — không gọi mạng thật, chỉ nối+cắt để bài test có thể xác nhận
        story_state có được truyền đúng qua các lệnh gọi hay không."""
        combined = f"{previous_state} {new_chapter_text[:80]}".strip()
        return combined[-500:]


class OpenAICompatTranslator:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        max_retries: int = 8,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "deepseek-chat"
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport  # test hook — None = httpx client mặc định

    def _chat(self, *, system: str, user: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        # AI local (Ollama/LM Studio…) thường không cần key — gửi "Bearer " rỗng
        # bị httpx/h11 từ chối (Illegal header value, trailing whitespace).
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        last_detail = ""
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            for attempt in range(self.max_retries):
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_detail = (resp.text or "")[:500]
                    # "Request quá to" báo qua 429 (vd Groq OTPM) KHÔNG BAO GIỜ
                    # tự hết khi gửi lại y hệt payload — retry-with-backoff ở
                    # đây chỉ hợp lý cho throttle TẠM THỜI. Raise ngay để
                    # `_translate_chunk` kịp chia nhỏ, thay vì đốt hết cả
                    # `max_retries` lần backoff (có thể tới vài phút) vô ích.
                    if _is_too_large_text(last_detail):
                        raise httpx.HTTPStatusError(
                            f"{resp.status_code} from {url}: {last_detail}",
                            request=resp.request,
                            response=resp,
                        )
                    # Hết lần thử (hoặc max_retries=1 cho key-failover) → raise
                    # ngay kèm status để tầng trên nhìn ra 429 và xoay key.
                    if attempt + 1 >= self.max_retries:
                        raise httpx.HTTPStatusError(
                            f"{resp.status_code} from {url}: {last_detail}",
                            request=resp.request,
                            response=resp,
                        )
                    wait = min(2 ** attempt, 60)
                    ra = resp.headers.get("retry-after")
                    if ra:
                        try:
                            wait = max(wait, int(float(ra)))
                        except ValueError:
                            pass
                    m = re.search(
                        r"try again in\s+(?:(\d+)m)?\s*([0-9.]+)s",
                        last_detail,
                        re.I,
                    )
                    if m:
                        mins = int(m.group(1) or 0)
                        secs = float(m.group(2) or 0)
                        wait = max(wait, int(mins * 60 + secs) + 1)
                    wait = min(max(wait, 1), 120)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    detail = (resp.text or "")[:400]
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code} from {url}: {detail}",
                        request=resp.request,
                        response=resp,
                    )
                data = resp.json()
                content = (data["choices"][0]["message"]["content"] or "").strip()
                if not content:
                    # Vài model (nhất là "reasoning" model như deepseek-r1-distill,
                    # qwen3...) đôi khi trả content rỗng — thường do cắt cụt giữa
                    # chừng lúc "suy nghĩ" (hết max_tokens trước khi ra câu trả lời
                    # thật). Coi như lỗi tạm thời, thử lại — TUYỆT ĐỐI không trả
                    # rỗng để khỏi bị đánh dấu DONE mà không có bản dịch thật.
                    last_detail = "model trả về content rỗng"
                    wait = min(2**attempt, 60)
                    time.sleep(wait)
                    continue
                return content
        raise RuntimeError(f"Model liên tục trả về rỗng/lỗi sau {self.max_retries} lần thử: {last_detail}")

    def translate(
        self,
        *,
        text: str,
        lang_src: str,
        lang_tgt: str,
        title: str = "",
        glossary: GlossaryPairs | None = None,
        mode: str = "full",
        mode_params: dict[str, Any] | None = None,
        already_translated: bool = False,
        prior_context: str = "",
        story_state: str = "",
    ) -> str:
        return self._translate_chunk(
            text=text,
            lang_src=lang_src,
            lang_tgt=lang_tgt,
            title=title,
            glossary=glossary,
            mode=mode,
            mode_params=mode_params,
            already_translated=already_translated,
            prior_context=prior_context,
            story_state=story_state,
            depth=0,
        )

    def _translate_chunk(
        self,
        *,
        text: str,
        lang_src: str,
        lang_tgt: str,
        title: str,
        glossary: GlossaryPairs | None,
        mode: str,
        mode_params: dict[str, Any] | None,
        already_translated: bool,
        prior_context: str,
        story_state: str,
        depth: int,
    ) -> str:
        """Gửi nguyên `text` trước (giống AiNiee: thử cả cụm, KHÔNG tự chia sẵn
        theo ngưỡng cố định). Chỉ khi provider báo lỗi "request quá to" (giới
        hạn cứng theo request — retry y hệt payload không bao giờ qua được,
        khác 429/5xx thoáng qua đã tự retry trong `_chat`) mới tự cắt đôi theo
        đoạn văn và thử lại từng nửa — đúng kiểu "auto-shrink on failure" của
        AiNiee, không phải bổ 1 ngưỡng tĩnh áp cho mọi chương. Không bao giờ
        gộp/cắt qua ranh giới CHƯƠNG KHÁC — chunking chỉ diễn ra bên trong 1
        lần gọi translate() của đúng 1 chương, vô hình với segment/cache/export
        phía trên (chúng vẫn thấy 1 kết quả dịch duy nhất cho chương đó)."""
        try:
            return self._translate_once(
                text=text,
                lang_src=lang_src,
                lang_tgt=lang_tgt,
                title=title,
                glossary=glossary,
                mode=mode,
                mode_params=mode_params,
                already_translated=already_translated,
                prior_context=prior_context,
                story_state=story_state,
            )
        except Exception as exc:  # noqa: BLE001
            if depth >= _MAX_SPLIT_DEPTH or len(text) < _MIN_SPLITTABLE_CHARS or not _looks_too_large(exc):
                raise
            left, right = _split_in_half(text)
            if not right:
                raise
            left_out = self._translate_chunk(
                text=left,
                lang_src=lang_src,
                lang_tgt=lang_tgt,
                title=title,
                glossary=glossary,
                mode=mode,
                mode_params=mode_params,
                already_translated=already_translated,
                prior_context=prior_context,
                story_state=story_state,
                depth=depth + 1,
            )
            # Nửa sau lấy đuôi nửa TRƯỚC (cùng chương) làm ngữ cảnh cục bộ, thay
            # cho prior_context bên ngoài (đó là ngữ cảnh của CHƯƠNG trước) —
            # giữ mạch ngay tại điểm cắt trong chính chương này.
            right_out = self._translate_chunk(
                text=right,
                lang_src=lang_src,
                lang_tgt=lang_tgt,
                title=title,
                glossary=glossary,
                mode=mode,
                mode_params=mode_params,
                already_translated=already_translated,
                prior_context=left_out.strip()[-_CONTEXT_TAIL_CHARS_LOCAL:],
                story_state=story_state,
                depth=depth + 1,
            )
            return left_out.rstrip() + "\n\n" + right_out.lstrip()

    def _translate_once(
        self,
        *,
        text: str,
        lang_src: str,
        lang_tgt: str,
        title: str = "",
        glossary: GlossaryPairs | None = None,
        mode: str = "full",
        mode_params: dict[str, Any] | None = None,
        already_translated: bool = False,
        prior_context: str = "",
        story_state: str = "",
    ) -> str:
        # QUAN TRỌNG: không nhét "Title: {title}" vào USER message — từng làm
        # 1 số model (vd Groq qwen) hiểu nhầm đây cũng là nội dung cần dịch rồi
        # in lại y "Tiêu đề: ..." vào đầu output (leak), gây lệch format so với
        # model khác. Tiêu đề chỉ đưa vào system prompt làm NGỮ CẢNH, không bao
        # giờ đưa vào user message.
        user = text
        title_block = (
            f"Chapter title (context only — do NOT output this line or any "
            f"translation of it, do not invent your own title/heading either): "
            f"\"{title}\"\n\n"
            if title
            else ""
        )
        # Chuẩn hoá format ra — khác model (Groq llama vs mixtral vs qwen…) hay
        # tự thêm heading/markdown khác nhau, gây lệch format giữa các chương
        # khi pool/fallback chia cho nhiều model dịch cùng 1 sách.
        format_rule = (
            "Output ONLY the chapter body text itself — no title/heading line, "
            "no markdown formatting (no **bold**, ##, > blockquote, numbered "
            "preamble) wrapping the output unless that exact formatting already "
            "appears in the source text.\n\n"
        )

        # audio_cut (spec 4.3): pass riêng trích must_keep_beats trước khi cắt,
        # tránh LLM nuốt twist/mất context nhân vật khi rút ngắn cho audio.
        beats_block = ""
        if mode == "audio_cut":
            beats = self._chat(system=title_block + build_beats_extraction_prompt(), user=user)
            beats_block = f"\n\nMUST-KEEP BEATS (preserve all, in order):\n{beats}\n"

        mode_inst = build_mode_instructions(mode, mode_params, already_translated=already_translated)
        if already_translated:
            role = (
                f"You are a professional literary editor. The user's text is already in "
                f"{lang_tgt} — do NOT translate it further, only apply the adaptation "
                f"instruction below. Preserve paragraph breaks. Output only the adapted "
                f"text, no preamble.\n\n"
            )
        else:
            role = (
                f"You are a professional literary translator. "
                f"Translate the user's chapter from {lang_src} to {lang_tgt}. "
                f"Preserve paragraph breaks. Output only the translation, no preamble.\n\n"
            )
        context_block = build_prior_context_block(prior_context)
        state_block = build_story_state_block(story_state)
        system = (
            f"{role}"
            f"{title_block}"
            f"{format_rule}"
            f"Adaptation mode `{mode}`: {mode_inst}{beats_block}\n\n"
            f"{context_block}"
            f"{state_block}"
            f"{_glossary_block(glossary)}"
        )
        return self._chat(system=system, user=user)

    def summarize_state(self, *, previous_state: str, new_chapter_text: str) -> str:
        """Lệnh gọi PHỤ sau mỗi chương (chỉ khi bật `track_story_state`) — cập
        nhật tóm tắt lũy kế để chương kế (dù slot/model nào dịch) đọc được."""
        user = (
            (f"PREVIOUS STATE:\n{previous_state}\n\n" if previous_state.strip() else "")
            + f"NEW CHAPTER (just translated/adapted):\n{new_chapter_text[:3000]}"
        )
        return self._chat(system=build_story_state_update_prompt(), user=user)


def build_translator(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    requires_api_key: bool = True,
) -> Translator:
    """provider=mock → MockTranslator. Thiếu api_key → MockTranslator, trừ khi
    requires_api_key=False (AI local như Ollama/LM Studio không cần key)."""
    prov = (provider or "mock").strip().lower()
    if prov == "mock" or (requires_api_key and not (api_key or "").strip()):
        return MockTranslator()
    return OpenAICompatTranslator(base_url=base_url, api_key=api_key, model=model)
