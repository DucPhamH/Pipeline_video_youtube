"""Enqueue + chạy Job dịch theo segment (background thread)."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time

from sqlalchemy.orm import Session

from platform_.db import SessionLocal
from platform_.settings_store import get_setting
from translate.application.callback import notify_crawl
from translate.application.estimate import (
    estimate_beats_pass_tokens,
    estimate_tokens,
    estimate_usd,
)
from translate.application.fingerprint import cache_key as make_cache_key
from translate.application.fingerprint import glossary_hash as make_glossary_hash
from translate.application.key_rotator import KeyRotator, looks_rate_limited
from translate.application.modes import build_glossary_extraction_prompt, build_glossary_seed_prompt
from translate.application.modes import mode_params_hash as make_mode_params_hash
from translate.domain.entities import (
    PROMPT_VERSION,
    ChapterSource,
    GlossaryTerm,
    Job,
    JobProviderSlot,
    JobStatus,
    Segment,
    SegmentStatus,
    Variant,
    VariantStatus,
    Work,
)
from translate.infrastructure.persistence.repositories import (
    AiProviderRepository,
    ChapterSourceRepository,
    GlossaryRepository,
    JobProviderSlotRepository,
    JobRepository,
    SegmentRepository,
    TranslationCacheRepository,
    VariantRepository,
    WorkRepository,
)
from translate.infrastructure.providers.openai_compat import (
    GlossaryPairs,
    OpenAICompatTranslator,
    build_translator,
)


def start_job_thread(job_id: int) -> None:
    """Chạy run_job() nền — dùng ở router (start/resume) và auto-chain fork."""
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()

# Gợi ý model phổ biến — user vẫn gõ tự do.
SUGGESTED_MODELS = [
    "qwen/qwen3.8-27b",
    "deepseek-chat",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

SUGGESTED_BASE_URLS = [
    {"label": "OpenAI (GPT)", "url": "https://api.openai.com/v1"},
    {"label": "Anthropic (Claude)", "url": "https://api.anthropic.com/v1"},
    {"label": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"label": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"label": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"label": "Mistral", "url": "https://api.mistral.ai/v1"},
    {"label": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"label": "xAI (Grok)", "url": "https://api.x.ai/v1"},
    {"label": "Qwen (DashScope)", "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"},
]


def _api_key_hint(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 4:
        return "****"
    return f"…{k[-4:]}"


def resolve_provider_config(
    db: Session,
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    requires_api_key: bool | None = None,
    ai_provider_id: int | None = None,
    fallback_provider: str = "",
    fallback_model: str = "",
    fallback_base_url: str = "",
    fallback_api_key: str = "",
    fallback_requires_api_key: bool = True,
) -> dict[str, str | bool]:
    """Request override > ai_provider_id (đã lưu) > job fallback > settings.

    `ai_provider_id`, khi truyền, là nguồn "authoritative" — field field nào nó có
    (kể cả api_key rỗng cho AI local) đứng chặn, không rơi tiếp xuống job
    fallback/settings (khác với fallback_* thường, vốn chỉ là gợi ý khi field
    đó rỗng/không set).

    Trả provider/model/base_url/api_key/requires_api_key đã resolve.
    """
    saved = AiProviderRepository(db).get(ai_provider_id) if ai_provider_id is not None else None
    if ai_provider_id is not None and saved is None:
        raise ValueError(f"AI provider {ai_provider_id} không tồn tại")

    settings_provider = str(get_setting(db, "translate.provider") or "mock")
    settings_model = str(get_setting(db, "translate.openai_model") or "deepseek-chat")
    settings_base = str(get_setting(db, "translate.openai_base_url") or "")
    settings_key = str(get_setting(db, "translate.openai_api_key") or "")

    chosen_provider = (
        (provider if provider is not None else "")
        or (saved.provider if saved else "")
        or fallback_provider
        or settings_provider
        or "mock"
    ).strip().lower()
    chosen_model = (
        (model if model is not None else "")
        or (saved.model if saved else "")
        or fallback_model
        or settings_model
        or "deepseek-chat"
    ).strip()
    chosen_base = (
        (base_url if base_url is not None else "")
        or (saved.base_url if saved else "")
        or fallback_base_url
        or settings_base
        or ""
    ).strip()
    # api_key: empty string in request means "clear"; None means inherit. Với
    # ai_provider_id, key của saved là quyết định cuối — không rơi xuống settings.
    if api_key is not None:
        chosen_key = api_key.strip()
    elif saved is not None:
        chosen_key = (saved.api_key or "").strip()
    else:
        chosen_key = (fallback_api_key or settings_key or "").strip()

    chosen_requires_key = (
        requires_api_key
        if requires_api_key is not None
        else (saved.requires_api_key if saved is not None else fallback_requires_api_key)
    )

    if not chosen_model:
        chosen_model = "deepseek-chat"
    if chosen_provider == "mock":
        effective = "mock"
    elif not chosen_key and chosen_requires_key:
        if (provider or "").strip().lower() == "openai":
            raise ValueError("provider=openai cần api_key — điền key trên desk trước khi dịch")
        effective = "mock"
    else:
        effective = "openai"

    return {
        "provider": effective,
        "model": chosen_model,
        "base_url": chosen_base,
        "api_key": chosen_key,
        "requires_api_key": chosen_requires_key,
    }


_CONTEXT_CARRY_MODES = ("pov", "audio_cut")
_CONTEXT_TAIL_CHARS = 700


def _story_state_tail(seg_repo: SegmentRepository, *, job_id: int, chapter_index: int) -> str:
    """Tóm tắt trạng thái truyện LŨY KẾ của chương ngay trước — trí nhớ DÀI HẠN
    (khác `_prior_context_tail`, chỉ có đuôi văn bản chương trước). Đọc theo
    chapter_index nên không phụ thuộc slot/model nào đã dịch chương đó."""
    prev = seg_repo.get_by_job_and_chapter(job_id, chapter_index - 1)
    if prev is None:
        return ""
    return (prev.story_state or "").strip()


def _prior_context_tail(seg_repo: SegmentRepository, *, job_id: int, chapter_index: int) -> str:
    """Đuôi output chương ngay trước (đã DONE/SKIPPED_CACHE) trong CÙNG job —
    best-effort: chương trước có thể do AI khác xử lý (fallback) hoặc chưa xong
    (pool chạy song song không đảm bảo thứ tự) -> rỗng thì bỏ qua, không chặn."""
    prev = seg_repo.get_by_job_and_chapter(job_id, chapter_index - 1)
    if prev is None or prev.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
        return ""
    text = (prev.output_text or "").strip()
    return text[-_CONTEXT_TAIL_CHARS:]


def _load_glossary_pairs(db: Session, work_id: int) -> tuple[GlossaryPairs, str]:
    terms = GlossaryRepository(db).list_by_work(work_id)
    pairs: GlossaryPairs = [
        (t.source_term, t.target_term, t.protected) for t in terms if t.source_term.strip()
    ]
    ghash = make_glossary_hash([(a, b, c) for a, b, c in pairs])
    return pairs, ghash


def resolve_provider_model(
    db: Session,
    *,
    model: str | None = None,
    provider: str | None = None,
    fallback_model: str = "",
) -> tuple[str, str]:
    """Backward-compat thin wrapper — dùng resolve_provider_config."""
    cfg = resolve_provider_config(
        db, model=model, provider=provider, fallback_model=fallback_model
    )
    return cfg["provider"], cfg["model"]


def _effective_lang_src(variant: Variant, work: Work) -> str:
    """lang_src 'hiệu lực' cho cache-key/prompt: variant fork từ full dùng
    lang_tgt (input đã là bản dịch); variant full dùng lang_src thật của Work."""
    return variant.lang_tgt if variant.source_variant_id is not None else work.lang_src


def _segment_cache_key(
    *,
    source_text: str,
    variant: Variant,
    lang_src: str,
    model: str,
    ghash: str,
    mphash: str,
) -> str:
    return make_cache_key(
        source_text=source_text,
        mode=variant.mode,
        lang_src=lang_src,
        lang_tgt=variant.lang_tgt,
        model=model,
        prompt_version=PROMPT_VERSION,
        glossary_hash_value=ghash,
        mode_params_hash_value=mphash,
    )


def _estimate_for_work(db: Session, *, work: Work, mode: str = "full") -> dict:
    """Ước chi phí dịch dựa trên toàn bộ ChapterSource của Work. `mode` chỉ ảnh
    hưởng số pass LLM (audio_cut chạy thêm 1 pass must_keep_beats — spec 4.3),
    không đổi lượng văn bản nguồn."""
    chapters = ChapterSourceRepository(db).list_by_work(work.id)  # type: ignore[arg-type]
    blob = "\n".join(ch.text or "" for ch in chapters)
    tokens = estimate_tokens(blob, lang_src=work.lang_src)
    if mode == "audio_cut":
        tokens += estimate_beats_pass_tokens(blob, lang_src=work.lang_src)
    usd_per_1k = float(get_setting(db, "translate.usd_per_1k_tokens") or 0.0)
    budget = float(get_setting(db, "translate.budget_usd_per_job") or 0.0)
    usd = estimate_usd(tokens, usd_per_1k=usd_per_1k)
    return {
        "chapter_count": len(chapters),
        "char_count": len(blob),
        "estimated_tokens": tokens,
        "usd_per_1k_tokens": usd_per_1k,
        "estimated_usd": usd,
        "budget_usd": budget,
        "over_budget": budget > 0 and usd > budget,
    }


def estimate_variant(db: Session, *, variant_id: int) -> dict:
    variant = VariantRepository(db).get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")
    work = WorkRepository(db).get(variant.work_id)
    if work is None:
        raise LookupError(f"Work {variant.work_id} không tồn tại")
    return {"variant_id": variant_id, **_estimate_for_work(db, work=work, mode=variant.mode)}


def estimate_work(db: Session, *, work_id: int, mode: str = "full") -> dict:
    work = WorkRepository(db).get(work_id)
    if work is None:
        raise LookupError(f"Work {work_id} không tồn tại")
    return {"work_id": work_id, **_estimate_for_work(db, work=work, mode=mode)}


def _prepare_segment_sources(
    db: Session, *, variant: Variant, work: Work, chapters: list[ChapterSource]
) -> tuple[dict[int, str], str]:
    """Trả (source_text theo chapter_index, lang_src hiệu lực) cho job sắp chạy.

    mode=full: dịch thẳng từ ChapterSource (lang_src = work.lang_src).
    mode khác (pov/audio_cut/style_clone): BẮT BUỘC fork từ variant `full` cùng
    Work đã dịch xong sạch (0 segment lỗi) — input là bản dịch, không dịch lại
    từ nguồn (spec mục 4.3 — quy tắc chi phí). Nếu full chưa xong: tự khởi động
    job full (nếu chưa chạy) rồi raise để user biết đang chờ; auto-chain trong
    run_job() sẽ tự start variant này tiếp khi full xong.
    """
    if variant.mode == "full" or variant.source_variant_id is None:
        return {ch.index: ch.text for ch in chapters}, work.lang_src

    variant_repo = VariantRepository(db)
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)

    source_variant = variant_repo.get(variant.source_variant_id)
    if source_variant is None:
        raise ValueError("Variant nguồn (full) không tồn tại — tạo lại variant này")

    source_job = job_repo.latest_for_variant(variant.source_variant_id)
    source_ready = source_job is not None and source_job.status == JobStatus.COMPLETED
    if source_ready:
        source_ready = not any(
            s.status == SegmentStatus.FAILED for s in seg_repo.list_by_job(source_job.id)  # type: ignore[arg-type]
        )

    if not source_ready:
        if source_job is None or source_job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
            try:
                new_job = enqueue_job(db, variant_id=variant.source_variant_id)
                start_job_thread(new_job.id)
            except ValueError:
                pass  # full đã queued/running do race khác, hoặc lỗi tạm — user thử lại sau
        raise ValueError(
            f"Đang dịch bản Đầy đủ trước (variant #{variant.source_variant_id}) — "
            f"'{variant.mode}' sẽ tự chạy tiếp ngay khi bản Đầy đủ xong."
        )

    assert source_job is not None
    output_by_index = {
        s.chapter_index: (s.output_text or "")
        for s in seg_repo.list_by_job(source_job.id)  # type: ignore[arg-type]
        if s.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE)
    }
    missing = [ch.index for ch in chapters if ch.index not in output_by_index]
    if missing:
        raise ValueError(
            f"Bản Đầy đủ thiếu bản dịch cho {len(missing)} chương "
            f"(vd #{missing[0]}) — Resume/chạy lại bản Đầy đủ trước"
        )
    return output_by_index, variant.lang_tgt


def _start_pending_forks(db: Session, *, source_variant_id: int) -> None:
    """Sau khi variant full dịch xong sạch — tự start mọi variant con (PENDING,
    source_variant_id trỏ vào đây) đang chờ fork, không cần user bấm lại."""
    variant_repo = VariantRepository(db)
    source = variant_repo.get(source_variant_id)
    if source is None:
        return
    children = [
        v
        for v in variant_repo.list_by_work(source.work_id)
        if v.source_variant_id == source_variant_id and v.status == VariantStatus.PENDING
    ]
    for child in children:
        try:
            job = enqueue_job(db, variant_id=child.id)  # type: ignore[arg-type]
        except (LookupError, ValueError):
            continue
        start_job_thread(job.id)  # type: ignore[arg-type]


_GLOSSARY_SAMPLE_MAX_CHAPTERS = 3
_GLOSSARY_SAMPLE_MAX_CHARS = 6000
# Đã có đủ thuật ngữ thì khỏi đốt thêm 1 lệnh LLM seed/extract.
_GLOSSARY_AUTO_SKIP_IF_AT_LEAST = 8


def _dedupe_keys(*groups: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            k = (raw or "").strip()
            if k and k not in seen:
                out.append(k)
                seen.add(k)
    return out


def _keys_from_ai_provider(p) -> list[str]:
    if p is None:
        return []
    return _dedupe_keys(getattr(p, "api_keys", None), [getattr(p, "api_key", "") or ""])


def _auto_seed_glossary_pre_translate(
    db: Session, *, work: Work, variant: Variant, chapters: list[ChapterSource], job: Job
) -> None:
    """Trích glossary TRƯỚC khi dịch chương nào — chạy 1 lần, ngay khi job full
    ĐẦU TIÊN của Work bắt đầu (trước khi spawn pool/fallback/single), nếu Work
    chưa có glossary nào. Khác `_auto_extract_glossary_if_empty` (chạy SAU khi
    job xong, cần cặp nguồn+bản dịch mẫu) — hàm này chỉ cần chương nguồn, nên
    kịp áp dụng cho MỌI chương của chính job đang chạy, không chỉ job sau."""
    if variant.mode != "full":
        return
    glossary_repo = GlossaryRepository(db)
    # Trộn vào, không đè: glossary tay của user (nếu có) vẫn giữ nguyên, chỉ
    # bổ sung thêm tên CHƯA có — trước đây hễ có >=1 mục (kể cả tự tay thêm)
    # là bỏ qua trích hoàn toàn, làm phí công nếu user chỉ thêm 1-2 tên riêng.
    existing_lower = {t.source_term.strip().lower() for t in glossary_repo.list_by_work(work.id)}  # type: ignore[arg-type]
    if len(existing_lower) >= _GLOSSARY_AUTO_SKIP_IF_AT_LEAST:
        return
    if (job.provider or "").strip().lower() != "openai":
        return

    ordered = sorted(chapters, key=lambda c: c.index)[:_GLOSSARY_SAMPLE_MAX_CHAPTERS]
    sample = "\n\n---\n\n".join(
        f"CHAPTER {ch.index}:\n{(ch.text or '')[:2500]}" for ch in ordered if (ch.text or "").strip()
    )[:_GLOSSARY_SAMPLE_MAX_CHARS]
    if not sample.strip():
        return

    try:
        translator = OpenAICompatTranslator(
            base_url=job.base_url, api_key=job.api_key or "", model=job.model, max_retries=2
        )
        raw = translator._chat(  # noqa: SLF001 — dùng nội bộ cho 1 lệnh gọi phụ, không qua translate()
            system=build_glossary_seed_prompt(variant.lang_tgt), user=sample
        )
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[1] if "\n" in text else text
        items = json.loads(text)
    except Exception:  # noqa: BLE001 — best-effort, không chặn job dịch
        return

    if not isinstance(items, list):
        return
    added = 0
    for item in items:
        if added >= 20:
            break
        if not isinstance(item, dict):
            continue
        src_term = str(item.get("source_term") or "").strip()
        tgt_term = str(item.get("target_term") or "").strip()
        if not src_term or not tgt_term or src_term.lower() in existing_lower:
            continue
        glossary_repo.add(
            GlossaryTerm(
                id=None,
                work_id=work.id,  # type: ignore[arg-type]
                source_term=src_term,
                target_term=tgt_term,
                protected=False,
                notes="Tự động trích xuất (trước khi dịch)",
            )
        )
        existing_lower.add(src_term.lower())
        added += 1
    if added:
        db.commit()


def _auto_extract_glossary_if_empty(db: Session, *, work: Work, variant: Variant, job: Job) -> None:
    """Tự trích glossary (tên nhân vật/địa danh) từ vài chương đầu bản Đầy đủ
    vừa dịch xong — user không phải tự gõ tay. Chỉ chạy khi Work CHƯA có glossary
    nào (không ghi đè lựa chọn tay của user) và job dùng AI thật (mock không
    trích được gì đáng tin). Best-effort tuyệt đối: lỗi/parse hỏng gì cũng bỏ
    qua lặng lẽ, không làm fail job — glossary rỗng vẫn dịch bình thường được,
    chỉ là kém nhất quán tên riêng hơn."""
    if variant.mode != "full":
        return
    glossary_repo = GlossaryRepository(db)
    existing_lower = {t.source_term.strip().lower() for t in glossary_repo.list_by_work(work.id)}  # type: ignore[arg-type]
    if len(existing_lower) >= _GLOSSARY_AUTO_SKIP_IF_AT_LEAST:
        return
    if (job.provider or "").strip().lower() != "openai":
        return

    chapters_by_index = {
        ch.index: ch for ch in ChapterSourceRepository(db).list_by_work(work.id)  # type: ignore[arg-type]
    }
    segments = sorted(
        (
            s
            for s in SegmentRepository(db).list_by_job(job.id)  # type: ignore[arg-type]
            if s.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE)
        ),
        key=lambda s: s.chapter_index,
    )

    blocks: list[str] = []
    total = 0
    for seg in segments:
        if len(blocks) >= _GLOSSARY_SAMPLE_MAX_CHAPTERS or total >= _GLOSSARY_SAMPLE_MAX_CHARS:
            break
        ch = chapters_by_index.get(seg.chapter_index)
        if ch is None or not seg.output_text:
            continue
        block = (
            f"CHAPTER {seg.chapter_index} (source):\n{(ch.text or '')[:2500]}\n\n"
            f"CHAPTER {seg.chapter_index} (translation):\n{(seg.output_text or '')[:2500]}"
        )
        blocks.append(block)
        total += len(block)
    if not blocks:
        return

    try:
        translator = OpenAICompatTranslator(
            base_url=job.base_url, api_key=job.api_key or "", model=job.model, max_retries=2
        )
        raw = translator._chat(  # noqa: SLF001 — dùng nội bộ cho 1 lệnh gọi phụ, không qua translate()
            system=build_glossary_extraction_prompt(), user="\n\n---\n\n".join(blocks)
        )
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[1] if "\n" in text else text
        items = json.loads(text)
    except Exception:  # noqa: BLE001 — best-effort, không làm fail job
        return

    if not isinstance(items, list):
        return
    added = 0
    for item in items:
        if added >= 20:
            break
        if not isinstance(item, dict):
            continue
        src_term = str(item.get("source_term") or "").strip()
        tgt_term = str(item.get("target_term") or "").strip()
        if not src_term or not tgt_term or src_term.lower() in existing_lower:
            continue
        glossary_repo.add(
            GlossaryTerm(
                id=None,
                work_id=work.id,  # type: ignore[arg-type]
                source_term=src_term,
                target_term=tgt_term,
                protected=False,
                notes="Tự động trích xuất",
            )
        )
        existing_lower.add(src_term.lower())
        added += 1
    if added:
        db.commit()


def _resolve_slot_specs(
    db: Session,
    *,
    ai_provider_ids: list[int] | None = None,
    ai_selections: list[dict] | None = None,
) -> list[dict]:
    """Danh sách slot phẳng (provider/model/base_url/api_key/label|ai_provider_id).

    - `ai_provider_ids`: 1 slot/AI, dùng model mặc định của registry.
    - `ai_selections`: mỗi AI có thể override `model` cho job này + `use_all_keys`
      (nhiều key CÙNG model đó → nhiều slot, kiểu AiNiee/Glossarion).
    """
    ai_repo = AiProviderRepository(db)
    specs: list[dict] = []
    if ai_selections:
        for sel in ai_selections:
            pid = sel.get("ai_provider_id")
            p = ai_repo.get(pid)
            if p is None:
                raise ValueError(f"AI provider {pid} không tồn tại")
            chosen_model = (str(sel.get("model") or "").strip() or p.model or "").strip()
            if not chosen_model:
                raise ValueError(f"AI «{p.label}» chưa có model — chọn model lúc bắt đầu dịch")
            explicit_keys = [str(k).strip() for k in (sel.get("api_keys") or []) if str(k).strip()]
            if sel.get("use_all_keys") and p.api_keys:
                keys = p.api_keys
            else:
                keys = explicit_keys or [p.api_key]
            multi = len(keys) > 1
            for k in keys:
                suffix = f"key…{k[-4:]}" if k else "key trống"
                label = p.label
                if chosen_model != (p.model or ""):
                    label = f"{p.label} · {chosen_model}"
                if multi:
                    label = f"{label} · {suffix}"
                specs.append(
                    {
                        "provider": p.provider,
                        "model": chosen_model,
                        "base_url": p.base_url,
                        "api_key": k,
                        "requires_api_key": p.requires_api_key,
                        "label": label,
                        "ai_provider_id": p.id,
                    }
                )
    else:
        for pid in ai_provider_ids or []:
            p = ai_repo.get(pid)
            if p is None:
                raise ValueError(f"AI provider {pid} không tồn tại")
            specs.append(
                {
                    "provider": p.provider,
                    "model": p.model,
                    "base_url": p.base_url,
                    "api_key": p.api_key,
                    "requires_api_key": p.requires_api_key,
                    "label": p.label,
                    "ai_provider_id": p.id,
                }
            )
    return specs


def _enqueue_multi_ai_job(
    db: Session,
    *,
    variant: Variant,
    work: Work,
    chapters: list[ChapterSource],
    source_by_index: dict[int, str],
    effective_lang_src: str,
    slot_specs: list[dict],
    ai_mode: str,
) -> Job:
    """Nhiều AI (hoặc nhiều key của cùng 1 AI) cho 1 job — snapshot từng slot
    vào job_provider_slots (không FK registry, giống Job), theo 1 trong 2 kiểu:
    - `pool`: chia round-robin theo thứ tự chương, chạy song song (nhanh hơn).
    - `fallback`: tất cả segment bắt đầu ở slot 0 (ưu tiên cao nhất) — chạy
      TUẦN TỰ, tự chuyển sang slot kế khi slot hiện tại lỗi liên tục (xem
      `_run_fallback_chain_segments`), không chạy song song.
    """
    if ai_mode not in ("pool", "fallback"):
        raise ValueError(f"ai_mode không hợp lệ: {ai_mode} (pool|fallback)")

    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    slot_repo = JobProviderSlotRepository(db)

    primary = slot_specs[0]
    primary_ai = primary.get("ai_provider_id")
    snap_keys = _dedupe_keys(
        [s.get("api_key") or "" for s in slot_specs if s.get("ai_provider_id") == primary_ai],
        [primary.get("api_key") or ""],
    )
    job = job_repo.add(
        Job(
            id=None,
            variant_id=variant.id,  # type: ignore[arg-type]
            status=JobStatus.QUEUED,
            provider=primary["provider"],
            model=primary["model"],
            base_url=primary["base_url"],
            api_key=primary["api_key"],
            requires_api_key=primary["requires_api_key"],
            ai_provider_id=primary_ai,
            api_keys=snap_keys,
            ai_mode=ai_mode,
            prompt_version=PROMPT_VERSION,
        )
    )
    slot_repo.add_many(
        [
            JobProviderSlot(
                id=None,
                job_id=job.id,  # type: ignore[arg-type]
                slot_index=i,
                provider=s["provider"],
                model=s["model"],
                base_url=s["base_url"],
                api_key=s["api_key"],
                requires_api_key=s["requires_api_key"],
                label=s["label"],
                ai_provider_id=s.get("ai_provider_id"),
            )
            for i, s in enumerate(slot_specs)
        ]
    )

    _, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
    mphash = make_mode_params_hash(variant.mode_params)
    n = len(slot_specs)
    segments = [
        Segment(
            id=None,
            job_id=job.id,  # type: ignore[arg-type]
            chapter_index=ch.index,
            status=SegmentStatus.PENDING,
            source_text=source_by_index[ch.index],
            slot_index=(i % n) if ai_mode == "pool" else 0,
            cache_key=_segment_cache_key(
                source_text=source_by_index[ch.index],
                variant=variant,
                lang_src=effective_lang_src,
                model=slot_specs[i % n]["model"] if ai_mode == "pool" else primary["model"],
                ghash=ghash,
                mphash=mphash,
            ),
        )
        for i, ch in enumerate(chapters)
    ]
    seg_repo.add_many(segments)
    VariantRepository(db).update_status(variant.id, VariantStatus.QUEUED)  # type: ignore[arg-type]
    db.commit()
    return job


def enqueue_job(
    db: Session,
    *,
    variant_id: int,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    ai_provider_id: int | None = None,
    ai_provider_ids: list[int] | None = None,
    ai_selections: list[dict] | None = None,
    ai_mode: str = "pool",
) -> Job:
    variant_repo = VariantRepository(db)
    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)

    variant = variant_repo.get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")

    work = work_repo.get(variant.work_id)
    if work is None:
        raise LookupError(f"Work {variant.work_id} không tồn tại")

    chapters = chapter_repo.list_by_work(work.id)  # type: ignore[arg-type]
    if not chapters:
        raise ValueError("Work không có chương nguồn")

    # Fork-from-full (spec 4.3): raise sớm nếu chưa fork được — trước khi tạo Job
    # row, để không để lại Job rỗng khi phải chờ variant full dịch xong.
    source_by_index, effective_lang_src = _prepare_segment_sources(
        db, variant=variant, work=work, chapters=chapters
    )

    est = estimate_variant(db, variant_id=variant_id)
    if est["over_budget"]:
        raise ValueError(
            f"Estimate ${est['estimated_usd']:.4f} vượt budget ${est['budget_usd']:.4f} "
            f"— tăng budget hoặc rút chương"
        )

    pool_ids = [pid for pid in (ai_provider_ids or []) if pid is not None]
    slot_specs = (
        _resolve_slot_specs(db, ai_selections=ai_selections)
        if ai_selections
        else (_resolve_slot_specs(db, ai_provider_ids=pool_ids) if len(pool_ids) >= 2 else [])
    )
    if len(slot_specs) >= 2:
        return _enqueue_multi_ai_job(
            db,
            variant=variant,
            work=work,
            chapters=chapters,
            source_by_index=source_by_index,
            effective_lang_src=effective_lang_src,
            slot_specs=slot_specs,
            ai_mode=ai_mode,
        )

    # 1 slot từ ai_selections (vd 1 AI + model override) — dùng thẳng, không
    # bỏ qua model đã chọn ở selection rồi rơi về default registry.
    if len(slot_specs) == 1:
        s = slot_specs[0]
        cfg = {
            "provider": s["provider"],
            "model": s["model"],
            "base_url": s["base_url"],
            "api_key": s["api_key"],
            "requires_api_key": s["requires_api_key"],
        }
        linked_ai_id = s.get("ai_provider_id")
    else:
        cfg = resolve_provider_config(
            db,
            model=model,
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            ai_provider_id=ai_provider_id,
        )
        linked_ai_id = ai_provider_id

    # Snapshot mọi key của AI (cùng model) — xoay vòng / failover 429 mà không
    # cần tick use_all_keys (pool). use_all_keys vẫn tạo nhiều slot song song.
    snap_keys: list[str] = []
    if linked_ai_id is not None:
        snap_keys = _keys_from_ai_provider(AiProviderRepository(db).get(linked_ai_id))
    snap_keys = _dedupe_keys(snap_keys, [str(cfg.get("api_key") or "")])

    _, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
    mphash = make_mode_params_hash(variant.mode_params)

    job = job_repo.add(
        Job(
            id=None,
            variant_id=variant_id,
            status=JobStatus.QUEUED,
            provider=cfg["provider"],
            model=cfg["model"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            requires_api_key=bool(cfg["requires_api_key"]),
            ai_provider_id=linked_ai_id,
            api_keys=snap_keys,
            prompt_version=PROMPT_VERSION,
        )
    )

    segments = [
        Segment(
            id=None,
            job_id=job.id,  # type: ignore[arg-type]
            chapter_index=ch.index,
            status=SegmentStatus.PENDING,
            source_text=source_by_index[ch.index],
            cache_key=_segment_cache_key(
                source_text=source_by_index[ch.index],
                variant=variant,
                lang_src=effective_lang_src,
                model=cfg["model"],
                ghash=ghash,
                mphash=mphash,
            ),
        )
        for ch in chapters
    ]
    seg_repo.add_many(segments)
    variant_repo.update_status(variant_id, VariantStatus.QUEUED)
    db.commit()
    return job


def resume_job(
    db: Session,
    *,
    job_id: int,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    ai_provider_id: int | None = None,
) -> Job:
    """Chạy lại segment failed/pending — có thể đổi toàn bộ provider config."""
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    variant_repo = VariantRepository(db)
    work_repo = WorkRepository(db)

    job = job_repo.get(job_id)
    if job is None:
        raise LookupError(f"Job {job_id} không tồn tại")
    if job.status == JobStatus.RUNNING:
        raise ValueError("Job đang chạy — dùng PATCH provider để đổi config đoạn còn lại")

    segs = seg_repo.list_by_job(job_id)
    retryable = [s for s in segs if s.status in (SegmentStatus.FAILED, SegmentStatus.PENDING)]
    if not retryable:
        raise ValueError("Không còn segment failed/pending để resume")

    is_pool = len(JobProviderSlotRepository(db).list_by_job(job_id)) >= 2
    has_override = any(
        x is not None for x in (model, provider, base_url, api_key, ai_provider_id)
    )
    if is_pool and has_override:
        raise ValueError(
            "Job nhiều AI (pool) — không đổi provider chung; xóa job và tạo lại nếu muốn đổi AI"
        )

    variant = variant_repo.get(job.variant_id)
    work = work_repo.get(variant.work_id) if variant else None  # type: ignore[union-attr]
    if variant is None or work is None:
        raise LookupError("Variant/Work missing")

    if is_pool:
        # Refresh key/URL từng slot từ registry (giữ model đã snapshot trên slot).
        _refresh_pool_slot_credentials(db, job_id=job_id)
        # Mỗi segment giữ nguyên slot/cache_key của nó — chỉ reset status để chạy lại.
        for seg in retryable:
            seg.status = SegmentStatus.PENDING
            seg.error = None
            seg_repo.update(seg)
    else:
        # Không truyền gì (resume trơn) nhưng job này vốn gắn với 1 AI đã lưu
        # (registry) -> re-resolve FRESH từ registry thay vì kẹt ở snapshot cũ
        # lúc tạo job (vd user vừa sửa lại key sai trong Settings).
        effective_ai_provider_id = ai_provider_id if ai_provider_id is not None else job.ai_provider_id
        # Chỉ provider/base_url/api_key tay mới tách khỏi registry. Đổi model
        # thôi (job-level override) VẪN giữ ai_provider_id để resume sau này
        # còn refresh được key từ Settings.
        detach_from_registry = any(x is not None for x in (provider, base_url, api_key))

        cfg = resolve_provider_config(
            db,
            model=model,
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            ai_provider_id=effective_ai_provider_id,
            fallback_provider=job.provider,
            fallback_model=job.model,
            fallback_base_url=job.base_url,
            fallback_api_key=job.api_key,
            fallback_requires_api_key=job.requires_api_key,
        )
        # Resume trơn (không gửi model): Settings chỉ refresh key/url — GIỮ
        # model đã snapshot trên job (vd job chọn Haiku trong khi Settings
        # default vẫn Fable). Chỉ khi request có model=... mới đổi.
        if model is None:
            cfg["model"] = job.model
        job.provider = cfg["provider"]
        job.model = cfg["model"]
        job.base_url = cfg["base_url"]
        job.api_key = cfg["api_key"]
        job.requires_api_key = bool(cfg["requires_api_key"])
        if ai_provider_id is not None:
            job.ai_provider_id = ai_provider_id  # user chỉ định AI khác -> theo AI mới từ đây
        elif detach_from_registry:
            job.ai_provider_id = None  # override tay -> không còn tự refresh theo registry nữa
        # Làm mới danh sách key xoay vòng từ registry (nếu còn gắn).
        if job.ai_provider_id is not None:
            fresh_keys = _keys_from_ai_provider(AiProviderRepository(db).get(job.ai_provider_id))
            if fresh_keys:
                job.api_keys = fresh_keys

        _, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
        mphash = make_mode_params_hash(variant.mode_params)
        for seg in retryable:
            seg.status = SegmentStatus.PENDING
            seg.error = None
            seg.cache_key = _segment_cache_key(
                source_text=seg.source_text,
                variant=variant,
                lang_src=_effective_lang_src(variant, work),
                model=cfg["model"],
                ghash=ghash,
                mphash=mphash,
            )
            seg_repo.update(seg)

    job.status = JobStatus.QUEUED
    job.error = None
    job_repo.update(job)
    variant_repo.update_status(job.variant_id, VariantStatus.QUEUED)
    db.commit()
    return job


def _stop_job(db: Session, *, job_id: int, reason: str) -> Job:
    """Dừng job queued/running — worker thoát giữa các segment.

    `reason` chỉ đổi thông điệp hiển thị (job.error); về mặt máy trạng thái,
    "cancelled" và "paused" giống hệt nhau — cả hai đều resumable qua
    resume_job (chỉ chặn khi job đang RUNNING).
    """
    from translate.infrastructure.persistence.models import JobModel

    message = "Đã tạm dừng bởi người dùng" if reason == "paused" else "Đã dừng bởi người dùng"

    job_repo = JobRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        raise LookupError(f"Job {job_id} không tồn tại")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise ValueError(f"Job đã {job.status.value} — không cần dừng")

    rows = (
        db.query(JobModel)
        .filter(
            JobModel.id == job_id,
            JobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
        .update(
            {
                JobModel.status: JobStatus.CANCELLED.value,
                JobModel.error: message,
            },
            synchronize_session=False,
        )
    )
    if rows == 0:
        job = job_repo.get(job_id)
        assert job is not None
        raise ValueError(f"Không dừng được — trạng thái hiện tại: {job.status.value}")

    variant_repo = VariantRepository(db)
    variant_repo.update_status(job.variant_id, VariantStatus.PENDING)
    db.commit()
    job = job_repo.get(job_id)
    assert job is not None
    return job


def cancel_job(db: Session, *, job_id: int) -> Job:
    return _stop_job(db, job_id=job_id, reason="cancelled")


def pause_job(db: Session, *, job_id: int) -> Job:
    return _stop_job(db, job_id=job_id, reason="paused")


def delete_job(db: Session, *, job_id: int) -> None:
    """Xóa job + segments. Phải dừng trước nếu đang chạy."""
    from translate.infrastructure.persistence.models import JobModel

    job_repo = JobRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        raise LookupError(f"Job {job_id} không tồn tại")
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise ValueError("Dừng job trước khi xóa")

    variant_id = job.variant_id
    m = db.get(JobModel, job_id)
    if m is not None:
        db.delete(m)
    db.commit()

    # Nếu variant không còn job nào — về pending
    latest = job_repo.latest_for_variant(variant_id)
    if latest is None:
        VariantRepository(db).update_status(variant_id, VariantStatus.PENDING)
        db.commit()


def set_job_provider(
    db: Session,
    *,
    job_id: int,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    ai_provider_id: int | None = None,
) -> Job:
    """Đổi provider config job — áp dụng cho segment chưa xong (kể cả đang running)."""
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    variant_repo = VariantRepository(db)
    work_repo = WorkRepository(db)

    job = job_repo.get(job_id)
    if job is None:
        raise LookupError(f"Job {job_id} không tồn tại")
    if job.status in (JobStatus.COMPLETED,):
        raise ValueError("Job đã completed — tạo job mới nếu muốn đổi provider")
    if len(JobProviderSlotRepository(db).list_by_job(job_id)) >= 2:
        raise ValueError(
            "Job nhiều AI (pool) — không đổi provider chung; xóa job và tạo lại nếu muốn đổi AI"
        )

    variant = variant_repo.get(job.variant_id)
    work = work_repo.get(variant.work_id) if variant else None  # type: ignore[union-attr]
    if variant is None or work is None:
        raise LookupError("Variant/Work missing")

    cfg = resolve_provider_config(
        db,
        model=model,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        ai_provider_id=ai_provider_id,
        fallback_provider=job.provider,
        fallback_model=job.model,
        fallback_base_url=job.base_url,
        fallback_api_key=job.api_key,
        fallback_requires_api_key=job.requires_api_key,
    )
    if not cfg["model"]:
        raise ValueError("model bắt buộc")
    # Giống resume: chỉ tách registry khi override credential/provider tay.
    # PATCH chỉ model (job-level) giữ ai_provider_id.
    if ai_provider_id is not None:
        job.ai_provider_id = ai_provider_id
    elif any(x is not None for x in (provider, base_url, api_key)):
        job.ai_provider_id = None

    _, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
    mphash = make_mode_params_hash(variant.mode_params)

    job.provider = cfg["provider"]
    job.model = cfg["model"]
    job.base_url = cfg["base_url"]
    job.api_key = cfg["api_key"]
    job.requires_api_key = bool(cfg["requires_api_key"])
    job_repo.update(job)

    for seg in seg_repo.list_by_job(job_id):
        if seg.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue
        seg.cache_key = _segment_cache_key(
            source_text=seg.source_text,
            variant=variant,
            lang_src=_effective_lang_src(variant, work),
            model=cfg["model"],
            ghash=ghash,
            mphash=mphash,
        )
        if seg.status == SegmentStatus.FAILED:
            seg.status = SegmentStatus.PENDING
            seg.error = None
        seg_repo.update(seg)

    db.commit()
    return job


def set_job_model(db: Session, *, job_id: int, model: str) -> Job:
    """Alias — chỉ đổi model."""
    return set_job_provider(db, job_id=job_id, model=model)

def _creds_from_job(j: Job) -> tuple[str, str, str, str]:
    provider = (j.provider or "mock").strip().lower()
    model = (j.model or "").strip() or "deepseek-chat"
    base_url = (j.base_url or "").strip()
    api_key = (j.api_key or "").strip()
    if provider != "mock" and not api_key and j.requires_api_key:
        provider = "mock"
    return provider, model, base_url, api_key


def _build_job_translator(
    prov: str, m: str, bu: str, key: str, requires_key: bool, *, max_retries: int | None = None
):
    t = build_translator(provider=prov, base_url=bu, api_key=key, model=m, requires_api_key=requires_key)
    if max_retries is not None and hasattr(t, "max_retries"):
        t.max_retries = max_retries
    return t


def _refresh_pool_slot_credentials(db: Session, *, job_id: int) -> None:
    """Resume job nhiều slot: refresh key/url từ registry theo ai_provider_id,
    GIỮ model đã snapshot trên từng slot (job-level override)."""
    slot_repo = JobProviderSlotRepository(db)
    ai_repo = AiProviderRepository(db)
    slots = slot_repo.list_by_job(job_id)
    by_ai: dict[int, list[JobProviderSlot]] = {}
    for s in slots:
        if s.ai_provider_id is not None:
            by_ai.setdefault(s.ai_provider_id, []).append(s)
    for pid, group in by_ai.items():
        p = ai_repo.get(pid)
        if p is None:
            continue
        fresh = _keys_from_ai_provider(p)
        if not fresh:
            continue
        group_sorted = sorted(group, key=lambda x: x.slot_index)
        used: set[str] = set()
        for i, s in enumerate(group_sorted):
            matched = None
            suffix = (s.api_key or "")[-4:]
            if suffix:
                for k in fresh:
                    if k.endswith(suffix) and k not in used:
                        matched = k
                        break
            if matched is None:
                matched = fresh[i % len(fresh)]
            used.add(matched)
            s.api_key = matched
            s.base_url = p.base_url or s.base_url
            s.provider = p.provider or s.provider
            s.requires_api_key = p.requires_api_key
            slot_repo.update(s)


def _sibling_keys_for_slot(slots: list[JobProviderSlot], slot: JobProviderSlot) -> list[str]:
    """Key failover: cùng AI / cùng (base_url, model) — ưu tiên key của slot hiện tại."""
    pool: list[str] = []
    for s in slots:
        same_ai = (
            slot.ai_provider_id is not None
            and s.ai_provider_id is not None
            and s.ai_provider_id == slot.ai_provider_id
        )
        same_endpoint = (s.base_url or "") == (slot.base_url or "") and (s.model or "") == (slot.model or "")
        if same_ai or same_endpoint:
            if s.api_key:
                pool.append(s.api_key)
    return _dedupe_keys([slot.api_key or ""], pool)


def _call_translate_rotating(
    *,
    provider: str,
    base_url: str,
    model: str,
    requires_api_key: bool,
    keys: list[str],
    rotator: KeyRotator,
    is_cancelled,
    translate_call,
):
    """Gọi translate với round-robin key; 429 → cooldown key đó, thử key khác
    ngay (cùng model). Trả (cancelled, output)."""
    key_list = _dedupe_keys(keys) or [""]
    last_exc: BaseException | None = None
    # Nhiều key: 1 lần thử/key rồi failover — tránh đốt phút backoff trên key chết.
    inner_retries = 1 if len(key_list) > 1 else None
    for attempt in range(max(len(key_list), 1)):
        if is_cancelled():
            return True, None
        key = rotator.next_key()
        translator = _build_job_translator(
            provider, model, base_url, key, requires_api_key, max_retries=inner_retries
        )
        try:
            cancelled, out = _call_with_shared_pacing(
                provider=provider,
                base_url=base_url,
                api_key=key,
                is_cancelled=is_cancelled,
                call=lambda t=translator: translate_call(t),
            )
            if cancelled:
                return True, None
            return False, out
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if looks_rate_limited(exc) and attempt + 1 < len(key_list):
                rotator.cooldown(key, 45.0)
                continue
            raise
    assert last_exc is not None
    raise last_exc


# --- Giãn cách dùng CHUNG theo (base_url, api_key) — nhiều job/thread trỏ tới
# cùng 1 AI thật (vd 2 job khác Work nhưng chọn chung 1 ai_provider_id) sẽ tự
# xếp hàng + cách nhau tối thiểu MIN_CALL_INTERVAL thay vì bắn song song không
# kiểm soát và cùng vượt rate-limit thật của nhà cung cấp. Không áp dụng cho
# mock (không gọi mạng thật, không có gì để bảo vệ).
MIN_CALL_INTERVAL = 3.0

# Giới hạn tổng số lệnh gọi LLM thật đang chạy CÙNG LÚC toàn hệ thống (khác
# identity vẫn bị chặn ở đây, không chỉ trùng key) — tránh user start rất nhiều
# job (nhiều AI khác nhau) rồi spawn không giới hạn request đồng thời. Không
# tính mock. Xem docs/translate-service.md mục 9 "Concurrency bounded".
MAX_CONCURRENT_TRANSLATE_CALLS = 8
_global_call_semaphore = threading.Semaphore(MAX_CONCURRENT_TRANSLATE_CALLS)

_identity_locks: dict[tuple[str, str], threading.Lock] = {}
_identity_locks_guard = threading.Lock()
_identity_last_call: dict[tuple[str, str], float] = {}


def _provider_identity(base_url: str, api_key: str) -> tuple[str, str]:
    return ((base_url or "").strip().lower(), api_key or "")


def _get_identity_lock(identity: tuple[str, str]) -> threading.Lock:
    with _identity_locks_guard:
        lock = _identity_locks.get(identity)
        if lock is None:
            lock = threading.Lock()
            _identity_locks[identity] = lock
        return lock


def _acquire_interruptible(sync_primitive, is_cancelled) -> bool:
    """True nếu bị cancel trong lúc chờ acquire (Lock hoặc Semaphore đều có
    .acquire(timeout=...) cùng chữ ký)."""
    while True:
        if is_cancelled():
            return True
        if sync_primitive.acquire(timeout=0.4):
            return False


def _call_with_shared_pacing(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    is_cancelled,
    call,
):
    """Gọi `call()` (1 lượt dịch) khi provider != mock:
    1) khoá + giãn cách dùng chung theo (base_url, api_key) — né rate-limit
       của riêng key đó;
    2) chờ 1 slot trong semaphore toàn cục — chặn tổng số request đồng thời
       của CẢ hệ thống, kể cả khác identity.
    Trả (cancelled, result); result=None nếu cancelled giữa lúc chờ."""
    if provider == "mock":
        return False, call()

    identity = _provider_identity(base_url, api_key)
    lock = _get_identity_lock(identity)
    if _acquire_interruptible(lock, is_cancelled):
        return True, None

    # QUAN TRỌNG: khoá identity chỉ giữ ĐỦ LÂU để giãn cách ĐIỂM BẮT ĐẦU giữa
    # các lệnh gọi cùng identity — nhả khoá NGAY sau đó, KHÔNG giữ suốt lúc
    # `call()` chạy (kể cả lúc nó tự retry nội bộ, có thể tới vài phút). Bug
    # thật gặp phải: pool nhiều model cùng 1 tài khoản (vd 8 model Gemini cùng
    # key) — model A bị nhà cung cấp báo lỗi tạm thời (503 "high demand") tự
    # retry ~3 phút bên trong `_chat()`; nếu giữ khoá suốt lúc đó thì 7 model
    # B..H còn lại (khác slot, CÙNG identity) bị chặn đứng chờ, triệt tiêu hẳn
    # song song thật của pool — y hệt chạy tuần tự dù cấu hình pool.
    try:
        last = _identity_last_call.get(identity)
        if last is not None:
            end = last + MIN_CALL_INTERVAL
            while time.time() < end:
                if is_cancelled():
                    return True, None
                time.sleep(min(0.2, max(0.0, end - time.time())))
        _identity_last_call[identity] = time.time()
    finally:
        lock.release()

    if _acquire_interruptible(_global_call_semaphore, is_cancelled):
        return True, None
    try:
        return False, call()
    finally:
        _global_call_semaphore.release()


def _run_single_ai_segments(
    db: Session,
    *,
    job_id: int,
    variant: Variant,
    chapters_by_index: dict[int, ChapterSource],
    glossary: GlossaryPairs,
    ghash: str,
    mphash: str,
    effective_lang_src: str,
    already_translated: bool,
) -> None:
    """1 AI cho cả job — tôn trọng job.model/provider, hot-swap giữa chừng nếu
    user PATCH provider trong lúc đang chạy. Nhiều key snapshot → round-robin
    + failover 429 (cùng model), giữ dịch tuần tự nên context ít mất."""
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    cache_repo = TranslationCacheRepository(db)

    job = job_repo.get(job_id)
    assert job is not None
    provider_setting, model, base_url, api_key = _creds_from_job(job)
    if model != job.model:
        job.model = model
        job_repo.update(job)

    key_pool = _dedupe_keys(job.api_keys, [api_key])
    rotator = KeyRotator(key_pool)
    requires_key = job.requires_api_key
    current_model = model
    current_sig = (provider_setting, model, base_url, "|".join(key_pool))
    track_story_state = bool((variant.mode_params or {}).get("track_story_state"))
    use_prior = variant.mode in _CONTEXT_CARRY_MODES or track_story_state

    def _is_cancelled() -> bool:
        j = job_repo.get(job_id)
        return j is not None and j.status == JobStatus.CANCELLED

    def _sleep_interruptible(seconds: float) -> bool:
        """True nếu bị cancel trong lúc chờ."""
        end = time.time() + seconds
        while time.time() < end:
            if _is_cancelled():
                return True
            time.sleep(min(0.4, max(0.0, end - time.time())))
        return False

    def _fill_story_state_if_needed(seg: Segment, output: str, summarizer) -> None:
        if not track_story_state:
            return
        if (seg.story_state or "").strip():
            return
        prev_state = _story_state_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
        try:
            seg.story_state = summarizer.summarize_state(
                previous_state=prev_state, new_chapter_text=output
            )
        except Exception:  # noqa: BLE001
            seg.story_state = prev_state

    segments = seg_repo.list_by_job(job_id)
    for seg in segments:
        if _is_cancelled():
            break
        if seg.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue

        # Hot-swap: đọc lại credential job mỗi segment
        fresh = job_repo.get(job_id)
        if fresh is not None:
            if fresh.status == JobStatus.CANCELLED:
                break
            prov, m, bu, key = _creds_from_job(fresh)
            fresh_keys = _dedupe_keys(fresh.api_keys, [key])
            sig = (prov, m, bu, "|".join(fresh_keys))
            if sig != current_sig:
                current_sig = sig
                provider_setting, model, base_url = prov, m, bu
                key_pool = fresh_keys
                rotator = KeyRotator(key_pool)
                requires_key = fresh.requires_api_key
                current_model = m
                seg.cache_key = _segment_cache_key(
                    source_text=seg.source_text,
                    variant=variant,
                    lang_src=effective_lang_src,
                    model=current_model,
                    ghash=ghash,
                    mphash=mphash,
                )

        try:
            cached = cache_repo.get(seg.cache_key) if seg.cache_key else None
            if cached is not None:
                seg.output_text = cached
                seg.status = SegmentStatus.SKIPPED_CACHE
                seg.error = None
                # Cache hit trước đây bỏ qua story_state → đứt chuỗi trí nhớ.
                stub = _build_job_translator(
                    provider_setting, current_model, base_url, key_pool[0] if key_pool else "", requires_key
                )
                _fill_story_state_if_needed(seg, cached, stub)
                seg_repo.update(seg)
                db.commit()
                continue

            ch = chapters_by_index.get(seg.chapter_index)
            title = ch.title if ch else ""
            prior_context = (
                _prior_context_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                if use_prior
                else ""
            )
            prev_state = (
                _story_state_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                if track_story_state
                else ""
            )

            def _do_translate(translator, *, _title=title, _prior=prior_context, _prev=prev_state):
                return translator.translate(
                    text=seg.source_text,
                    lang_src=effective_lang_src,
                    lang_tgt=variant.lang_tgt,
                    title=_title,
                    glossary=glossary,
                    mode=variant.mode,
                    mode_params=variant.mode_params,
                    already_translated=already_translated,
                    prior_context=_prior,
                    story_state=_prev,
                )

            cancelled, out = _call_translate_rotating(
                provider=provider_setting,
                base_url=base_url,
                model=current_model,
                requires_api_key=requires_key,
                keys=key_pool,
                rotator=rotator,
                is_cancelled=_is_cancelled,
                translate_call=_do_translate,
            )
            if cancelled:
                break
            seg.output_text = out
            seg.status = SegmentStatus.DONE
            seg.error = None
            if track_story_state:
                try:
                    # Dùng translator với key hiện tại của rotator để summarize
                    summ = _build_job_translator(
                        provider_setting,
                        current_model,
                        base_url,
                        rotator.keys[0] if rotator.keys else "",
                        requires_key,
                    )
                    seg.story_state = summ.summarize_state(
                        previous_state=prev_state, new_chapter_text=out
                    )
                except Exception:  # noqa: BLE001 — best-effort, giữ nguyên state cũ
                    seg.story_state = prev_state
            seg_repo.update(seg)
            if seg.cache_key:
                cache_repo.put(seg.cache_key, out)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — ghi lỗi segment, tiếp tục
            seg.status = SegmentStatus.FAILED
            seg.error = str(exc)
            seg_repo.update(seg)
            db.commit()
            if looks_rate_limited(exc) or "429" in str(exc) or "Rate limit" in str(exc):
                if _sleep_interruptible(15):
                    break


def _run_pool_worker(job_id: int, slot: JobProviderSlot) -> None:
    """1 AI trong pool nhiều-AI-chia-nhau-dịch — session riêng (SQLAlchemy session
    không thread-safe), chỉ xử lý segment đúng slot_index của mình, không hot-swap
    (đổi AI giữa chừng cho pool job không hỗ trợ — xóa job và tạo lại nếu cần).
    429 trên key của slot → thử sibling key cùng AI/model (failover trong chương)."""
    db = SessionLocal()
    try:
        job_repo = JobRepository(db)
        variant_repo = VariantRepository(db)
        work_repo = WorkRepository(db)
        chapter_repo = ChapterSourceRepository(db)
        seg_repo = SegmentRepository(db)
        cache_repo = TranslationCacheRepository(db)
        slot_repo = JobProviderSlotRepository(db)

        job = job_repo.get(job_id)
        if job is None:
            return
        variant = variant_repo.get(job.variant_id)
        if variant is None:
            return
        work = work_repo.get(variant.work_id)
        if work is None:
            return

        chapters_by_index = {
            ch.index: ch for ch in chapter_repo.list_by_work(work.id)  # type: ignore[arg-type]
        }
        glossary, _ = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
        effective_lang_src = _effective_lang_src(variant, work)
        already_translated = variant.source_variant_id is not None
        track_story_state = bool((variant.mode_params or {}).get("track_story_state"))
        use_prior = variant.mode in _CONTEXT_CARRY_MODES or track_story_state

        all_slots = slot_repo.list_by_job(job_id)
        # Refresh slot entity from list (may have been updated on resume)
        slot = next((s for s in all_slots if s.slot_index == slot.slot_index), slot)
        key_pool = _sibling_keys_for_slot(all_slots, slot)
        rotator = KeyRotator(key_pool)

        prov = (slot.provider or "mock").strip().lower()
        model = (slot.model or "").strip() or "deepseek-chat"
        if prov != "mock" and not key_pool and slot.requires_api_key:
            prov = "mock"

        def _is_cancelled() -> bool:
            j = job_repo.get(job_id)
            return j is not None and j.status == JobStatus.CANCELLED

        def _sleep_interruptible(seconds: float) -> bool:
            end = time.time() + seconds
            while time.time() < end:
                if _is_cancelled():
                    return True
                time.sleep(min(0.4, max(0.0, end - time.time())))
            return False

        segments = seg_repo.list_by_job_and_slot(job_id, slot.slot_index)
        for seg in segments:
            if _is_cancelled():
                break
            if seg.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
                continue
            try:
                cached = cache_repo.get(seg.cache_key) if seg.cache_key else None
                if cached is not None:
                    seg.output_text = cached
                    seg.status = SegmentStatus.SKIPPED_CACHE
                    seg.error = None
                    if track_story_state and not (seg.story_state or "").strip():
                        prev_state = _story_state_tail(
                            seg_repo, job_id=job_id, chapter_index=seg.chapter_index
                        )
                        stub = _build_job_translator(
                            prov, model, slot.base_url, key_pool[0] if key_pool else "", slot.requires_api_key
                        )
                        try:
                            seg.story_state = stub.summarize_state(
                                previous_state=prev_state, new_chapter_text=cached
                            )
                        except Exception:  # noqa: BLE001
                            seg.story_state = prev_state
                    seg_repo.update(seg)
                    db.commit()
                    continue

                ch = chapters_by_index.get(seg.chapter_index)
                title = ch.title if ch else ""
                prior_context = (
                    _prior_context_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                    if use_prior
                    else ""
                )
                prev_state = (
                    _story_state_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                    if track_story_state
                    else ""
                )

                def _do_translate(translator, *, _title=title, _prior=prior_context, _prev=prev_state):
                    return translator.translate(
                        text=seg.source_text,
                        lang_src=effective_lang_src,
                        lang_tgt=variant.lang_tgt,
                        title=_title,
                        glossary=glossary,
                        mode=variant.mode,
                        mode_params=variant.mode_params,
                        already_translated=already_translated,
                        prior_context=_prior,
                        story_state=_prev,
                    )

                cancelled, out = _call_translate_rotating(
                    provider=prov,
                    base_url=slot.base_url,
                    model=model,
                    requires_api_key=slot.requires_api_key,
                    keys=key_pool,
                    rotator=rotator,
                    is_cancelled=_is_cancelled,
                    translate_call=_do_translate,
                )
                if cancelled:
                    break
                seg.output_text = out
                seg.status = SegmentStatus.DONE
                seg.error = None
                if track_story_state:
                    try:
                        summ = _build_job_translator(
                            prov, model, slot.base_url, key_pool[0] if key_pool else "", slot.requires_api_key
                        )
                        seg.story_state = summ.summarize_state(
                            previous_state=prev_state, new_chapter_text=out
                        )
                    except Exception:  # noqa: BLE001 — best-effort, giữ nguyên state cũ
                        seg.story_state = prev_state
                seg_repo.update(seg)
                if seg.cache_key:
                    cache_repo.put(seg.cache_key, out)
                db.commit()
            except Exception as exc:  # noqa: BLE001 — ghi lỗi segment, tiếp tục
                seg.status = SegmentStatus.FAILED
                seg.error = str(exc)
                seg_repo.update(seg)
                db.commit()
                if looks_rate_limited(exc) or "429" in str(exc) or "Rate limit" in str(exc):
                    if _sleep_interruptible(15):
                        break
    finally:
        db.close()


def _slot_translator(slot: JobProviderSlot):
    prov = (slot.provider or "mock").strip().lower()
    if prov != "mock" and not (slot.api_key or "").strip() and slot.requires_api_key:
        prov = "mock"
    return build_translator(
        provider=prov,
        base_url=slot.base_url,
        api_key=slot.api_key,
        model=(slot.model or "").strip() or "deepseek-chat",
        requires_api_key=slot.requires_api_key,
    )


def _run_fallback_chain_segments(
    db: Session,
    *,
    job_id: int,
    variant: Variant,
    chapters_by_index: dict[int, ChapterSource],
    glossary: GlossaryPairs,
    ghash: str,
    mphash: str,
    effective_lang_src: str,
    already_translated: bool,
    slots: list[JobProviderSlot],
) -> None:
    """>=2 AI theo THỨ TỰ ưu tiên, chạy tuần tự (không song song như pool).
    Dùng slot 0 cho tới khi nó lỗi liên tục trên 1 segment — thử hết cả dãy
    slot còn lại cho ĐÚNG segment đó ngay lập tức, rồi "định cư" ở slot mới đó
    cho các segment tiếp theo (không quay lại slot đã chết)."""
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    cache_repo = TranslationCacheRepository(db)
    track_story_state = bool((variant.mode_params or {}).get("track_story_state"))
    use_prior = variant.mode in _CONTEXT_CARRY_MODES or track_story_state

    current_idx = 0
    translator = _slot_translator(slots[current_idx])

    def _is_cancelled() -> bool:
        j = job_repo.get(job_id)
        return j is not None and j.status == JobStatus.CANCELLED

    def _sleep_interruptible(seconds: float) -> bool:
        end = time.time() + seconds
        while time.time() < end:
            if _is_cancelled():
                return True
            time.sleep(min(0.4, max(0.0, end - time.time())))
        return False

    segments = seg_repo.list_by_job(job_id)
    for seg in segments:
        if _is_cancelled():
            break
        if seg.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue

        while True:
            if _is_cancelled():
                return
            slot = slots[current_idx]
            try:
                cached = cache_repo.get(seg.cache_key) if seg.cache_key else None
                if cached is not None:
                    seg.output_text = cached
                    seg.status = SegmentStatus.SKIPPED_CACHE
                    seg.error = None
                    seg.slot_index = current_idx
                    if track_story_state and not (seg.story_state or "").strip():
                        prev_state = _story_state_tail(
                            seg_repo, job_id=job_id, chapter_index=seg.chapter_index
                        )
                        try:
                            seg.story_state = translator.summarize_state(
                                previous_state=prev_state, new_chapter_text=cached
                            )
                        except Exception:  # noqa: BLE001
                            seg.story_state = prev_state
                    seg_repo.update(seg)
                    db.commit()
                    break

                ch = chapters_by_index.get(seg.chapter_index)
                title = ch.title if ch else ""
                prior_context = (
                    _prior_context_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                    if use_prior
                    else ""
                )
                prev_state = (
                    _story_state_tail(seg_repo, job_id=job_id, chapter_index=seg.chapter_index)
                    if track_story_state
                    else ""
                )
                cancelled, out = _call_with_shared_pacing(
                    provider=slot.provider,
                    base_url=slot.base_url,
                    api_key=slot.api_key,
                    is_cancelled=_is_cancelled,
                    call=lambda: translator.translate(
                        text=seg.source_text,
                        lang_src=effective_lang_src,
                        lang_tgt=variant.lang_tgt,
                        title=title,
                        glossary=glossary,
                        mode=variant.mode,
                        mode_params=variant.mode_params,
                        already_translated=already_translated,
                        prior_context=prior_context,
                        story_state=prev_state,
                    ),
                )
                if cancelled:
                    return
                seg.output_text = out
                seg.status = SegmentStatus.DONE
                seg.error = None
                seg.slot_index = current_idx
                if track_story_state:
                    try:
                        seg.story_state = translator.summarize_state(
                            previous_state=prev_state, new_chapter_text=out
                        )
                    except Exception:  # noqa: BLE001 — best-effort, giữ nguyên state cũ
                        seg.story_state = prev_state
                seg_repo.update(seg)
                if seg.cache_key:
                    cache_repo.put(seg.cache_key, out)
                db.commit()
                break
            except Exception as exc:  # noqa: BLE001
                next_idx = current_idx + 1
                if next_idx < len(slots):
                    # AI hiện tại vừa "tạch" — chuyển AI kế, thử lại NGAY đúng
                    # segment này (không đợi/backoff — AI khác, rate-limit khác).
                    current_idx = next_idx
                    translator = _slot_translator(slots[current_idx])
                    seg.cache_key = _segment_cache_key(
                        source_text=seg.source_text,
                        variant=variant,
                        lang_src=effective_lang_src,
                        model=slots[current_idx].model,
                        ghash=ghash,
                        mphash=mphash,
                    )
                    seg.error = f"[{slot.label or slot.model}] {exc} — đã tự chuyển sang AI kế"
                    continue
                # Đã thử hết mọi AI trong danh sách cho segment này — chịu thật.
                seg.status = SegmentStatus.FAILED
                seg.error = str(exc)
                seg.slot_index = current_idx
                seg_repo.update(seg)
                db.commit()
                # QUAN TRỌNG: reset về slot 0 cho CHƯƠNG KẾ TIẾP — nếu không,
                # 1 chương xui xẻo lỗi hết cả dãy (vd rate-limit tạm thời dồn
                # dập) sẽ làm current_idx kẹt mãi ở slot cuối cùng (thường là
                # model chết hẳn), khiến MỌI chương sau đó không bao giờ được
                # thử lại các model vẫn đang sống ở đầu danh sách nữa. Chỉ
                # "định cư" (giữ current_idx) khi có 1 slot THẬT SỰ dịch
                # thành công — thất bại toàn bộ thì không biết slot nào đáng
                # tin, nên cho cả dãy 1 cơ hội công bằng lại từ đầu.
                current_idx = 0
                translator = _slot_translator(slots[current_idx])
                if "429" in str(exc) or "Rate limit" in str(exc):
                    if _sleep_interruptible(15):
                        return
                break


def run_job(job_id: int) -> None:
    """Chạy trong thread nền — mở Session riêng.

    1 AI: tôn trọng job.model/provider (đổi mid-run qua PATCH được).
    Pool (>=2 job_provider_slots — nhiều AI chia nhau dịch): spawn 1 thread/AI,
    mỗi thread chỉ xử lý segment slot của mình (round-robin theo chương lúc
    enqueue), join xong mới sang bước tổng kết chung.
    """
    from translate.infrastructure.persistence.models import JobModel

    db = SessionLocal()
    try:
        job_repo = JobRepository(db)
        seg_repo = SegmentRepository(db)
        variant_repo = VariantRepository(db)
        work_repo = WorkRepository(db)
        chapter_repo = ChapterSourceRepository(db)

        job = job_repo.get(job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELLED:
            return

        variant = variant_repo.get(job.variant_id)
        if variant is None:
            job.status = JobStatus.FAILED
            job.error = "Variant missing"
            job_repo.update(job)
            db.commit()
            return

        work = work_repo.get(variant.work_id)
        if work is None:
            job.status = JobStatus.FAILED
            job.error = "Work missing"
            job_repo.update(job)
            db.commit()
            return

        slots = JobProviderSlotRepository(db).list_by_job(job_id)

        # Chỉ QUEUED → RUNNING (tránh ghi đè CANCELLED nếu user vừa dừng)
        started = (
            db.query(JobModel)
            .filter(JobModel.id == job_id, JobModel.status == JobStatus.QUEUED.value)
            .update(
                {JobModel.status: JobStatus.RUNNING.value, JobModel.error: None},
                synchronize_session=False,
            )
        )
        if started == 0:
            fresh = job_repo.get(job_id)
            if fresh is None or fresh.status == JobStatus.CANCELLED:
                return
            # Đã running (resume race) — tiếp tục với status hiện tại
            if fresh.status != JobStatus.RUNNING:
                return

        variant_repo.update_status(variant.id, VariantStatus.RUNNING)  # type: ignore[arg-type]
        db.commit()

        notify_crawl(
            callback_url=work.callback_url,
            external_id=work.external_id,
            status="translating",
        )

        # Trích glossary TRƯỚC khi dịch chương nào (chỉ job full đầu tiên của
        # Work, glossary còn rỗng) — chạy trước khi spawn pool/fallback/single
        # để MỌI chương của chính job này (dù chương nào do model nào dịch)
        # đều dùng chung tên nhân vật/địa danh ngay từ đầu.
        _auto_seed_glossary_pre_translate(
            db,
            work=work,
            variant=variant,
            chapters=chapter_repo.list_by_work(work.id),  # type: ignore[arg-type]
            job=job,
        )

        if len(slots) >= 2 and job.ai_mode == "pool":
            threads = [
                threading.Thread(target=_run_pool_worker, args=(job_id, slot), daemon=True)
                for slot in slots
            ]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
        elif len(slots) >= 2 and job.ai_mode == "fallback":
            chapters_by_index = {
                ch.index: ch for ch in chapter_repo.list_by_work(work.id)  # type: ignore[arg-type]
            }
            glossary, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
            mphash = make_mode_params_hash(variant.mode_params)
            effective_lang_src = _effective_lang_src(variant, work)
            already_translated = variant.source_variant_id is not None
            _run_fallback_chain_segments(
                db,
                job_id=job_id,
                variant=variant,
                chapters_by_index=chapters_by_index,
                glossary=glossary,
                ghash=ghash,
                mphash=mphash,
                effective_lang_src=effective_lang_src,
                already_translated=already_translated,
                slots=slots,
            )
        else:
            chapters_by_index = {
                ch.index: ch for ch in chapter_repo.list_by_work(work.id)  # type: ignore[arg-type]
            }
            glossary, ghash = _load_glossary_pairs(db, work.id)  # type: ignore[arg-type]
            mphash = make_mode_params_hash(variant.mode_params)
            effective_lang_src = _effective_lang_src(variant, work)
            already_translated = variant.source_variant_id is not None
            _run_single_ai_segments(
                db,
                job_id=job_id,
                variant=variant,
                chapters_by_index=chapters_by_index,
                glossary=glossary,
                ghash=ghash,
                mphash=mphash,
                effective_lang_src=effective_lang_src,
                already_translated=already_translated,
            )

        job = job_repo.get(job_id)
        assert job is not None
        if job.status == JobStatus.CANCELLED:
            variant_repo.update_status(variant.id, VariantStatus.PENDING)  # type: ignore[arg-type]
            db.commit()
            notify_crawl(
                callback_url=work.callback_url,
                external_id=work.external_id,
                status="cancelled",
                message=job.error,
            )
            return

        segments = seg_repo.list_by_job(job_id)
        failed = sum(1 for s in segments if s.status == SegmentStatus.FAILED)
        if failed and failed == len(segments):
            job.status = JobStatus.FAILED
            job.error = f"Tất cả {failed} segment thất bại"
            variant_repo.update_status(variant.id, VariantStatus.FAILED)  # type: ignore[arg-type]
        elif failed:
            job.status = JobStatus.COMPLETED
            job.error = f"{failed}/{len(segments)} segment lỗi"
            variant_repo.update_status(variant.id, VariantStatus.READY)  # type: ignore[arg-type]
        else:
            job.status = JobStatus.COMPLETED
            job.error = None
            variant_repo.update_status(variant.id, VariantStatus.READY)  # type: ignore[arg-type]
        job.updated_at = dt.datetime.utcnow()
        job_repo.update(job)
        db.commit()

        if job.status == JobStatus.COMPLETED and failed == 0:
            _auto_extract_glossary_if_empty(db, work=work, variant=variant, job=job)
            _start_pending_forks(db, source_variant_id=variant.id)  # type: ignore[arg-type]

        if job.status == JobStatus.FAILED:
            notify_crawl(
                callback_url=work.callback_url,
                external_id=work.external_id,
                status="failed",
                message=job.error,
            )
        else:
            notify_crawl(
                callback_url=work.callback_url,
                external_id=work.external_id,
                status="ready_for_video",
                message=job.error,
            )
    finally:
        db.close()
