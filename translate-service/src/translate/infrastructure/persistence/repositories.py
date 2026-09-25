"""Map ORM ↔ domain entities."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from translate.domain.entities import (
    AiProvider,
    ChapterSource,
    GlossaryTerm,
    Job,
    JobProviderSlot,
    JobStatus,
    Segment,
    SegmentStatus,
    SourceType,
    Variant,
    VariantStatus,
    Work,
    WorkStatus,
)
from translate.infrastructure.persistence.models import (
    AiProviderModel,
    ChapterSourceModel,
    GlossaryTermModel,
    JobModel,
    JobProviderSlotModel,
    SegmentModel,
    TranslationCacheModel,
    VariantModel,
    WorkModel,
)


def _work_to_entity(m: WorkModel) -> Work:
    return Work(
        id=m.id,
        external_id=m.external_id,
        title=m.title,
        author=m.author or "",
        lang_src=m.lang_src,
        lang_tgt=m.lang_tgt,
        source_type=SourceType(m.source_type),
        status=WorkStatus(m.status),
        callback_url=m.callback_url,
        missing_cleaned=getattr(m, "missing_cleaned", None) or 0,
        unreviewed_chapters=getattr(m, "unreviewed_chapters", None) or 0,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _chapter_to_entity(m: ChapterSourceModel) -> ChapterSource:
    return ChapterSource(
        id=m.id,
        work_id=m.work_id,
        index=m.index,
        title=m.title or "",
        text=m.text or "",
        fingerprint=m.fingerprint or "",
    )


def _variant_to_entity(m: VariantModel) -> Variant:
    return Variant(
        id=m.id,
        work_id=m.work_id,
        mode=m.mode,
        status=VariantStatus(m.status),
        lang_tgt=m.lang_tgt,
        mode_params=dict(m.mode_params or {}),
        source_variant_id=m.source_variant_id,
        created_at=m.created_at,
    )


def _job_to_entity(m: JobModel) -> Job:
    return Job(
        id=m.id,
        variant_id=m.variant_id,
        status=JobStatus(m.status),
        provider=m.provider,
        model=m.model or "",
        prompt_version=m.prompt_version or "v1",
        error=m.error,
        base_url=getattr(m, "base_url", None) or "",
        api_key=getattr(m, "api_key", None) or "",
        requires_api_key=bool(getattr(m, "requires_api_key", 1)),
        ai_provider_id=getattr(m, "ai_provider_id", None),
        api_keys=_parse_json_str_list(getattr(m, "api_keys_json", None)),
        ai_mode=getattr(m, "ai_mode", None) or "single",
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _parse_json_str_list(raw: str | None) -> list[str]:
    try:
        items = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    return [str(x).strip() for x in items if str(x).strip()]


def _ai_provider_to_entity(m: AiProviderModel) -> AiProvider:
    return AiProvider(
        id=m.id,
        label=m.label,
        kind=m.kind,
        provider=m.provider,
        base_url=m.base_url or "",
        model=m.model or "",
        api_key=m.api_key or "",
        requires_api_key=bool(m.requires_api_key),
        api_keys=_parse_json_str_list(getattr(m, "api_keys_json", None)),
        sort_order=m.sort_order,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _segment_to_entity(m: SegmentModel) -> Segment:
    return Segment(
        id=m.id,
        job_id=m.job_id,
        chapter_index=m.chapter_index,
        status=SegmentStatus(m.status),
        source_text=m.source_text or "",
        output_text=m.output_text,
        cache_key=m.cache_key or "",
        error=m.error,
        reviewed=bool(m.reviewed),
        slot_index=getattr(m, "slot_index", None) or 0,
        story_state=getattr(m, "story_state", None) or "",
    )


def _job_provider_slot_to_entity(m: JobProviderSlotModel) -> JobProviderSlot:
    return JobProviderSlot(
        id=m.id,
        job_id=m.job_id,
        slot_index=m.slot_index,
        provider=m.provider,
        model=m.model or "",
        base_url=m.base_url or "",
        api_key=m.api_key or "",
        requires_api_key=bool(m.requires_api_key),
        label=m.label or "",
        ai_provider_id=getattr(m, "ai_provider_id", None),
    )


def _glossary_to_entity(m: GlossaryTermModel) -> GlossaryTerm:
    return GlossaryTerm(
        id=m.id,
        work_id=m.work_id,
        source_term=m.source_term,
        target_term=m.target_term or "",
        protected=bool(m.protected),
        notes=m.notes or "",
    )


class WorkRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, work: Work) -> Work:
        m = WorkModel(
            external_id=work.external_id,
            title=work.title,
            author=work.author,
            lang_src=work.lang_src,
            lang_tgt=work.lang_tgt,
            source_type=work.source_type.value,
            status=work.status.value,
            callback_url=work.callback_url,
            missing_cleaned=work.missing_cleaned,
            unreviewed_chapters=work.unreviewed_chapters,
        )
        self.db.add(m)
        self.db.flush()
        work.id = m.id
        return work

    def get(self, work_id: int) -> Work | None:
        m = self.db.get(WorkModel, work_id)
        return _work_to_entity(m) if m else None

    def get_by_external_id(self, external_id: str) -> Work | None:
        m = self.db.query(WorkModel).filter(WorkModel.external_id == external_id).first()
        return _work_to_entity(m) if m else None

    def list_all(self, *, limit: int = 100) -> list[Work]:
        rows = (
            self.db.query(WorkModel)
            .order_by(WorkModel.id.desc())
            .limit(limit)
            .all()
        )
        return [_work_to_entity(m) for m in rows]

    def update(self, work: Work) -> None:
        m = self.db.get(WorkModel, work.id)
        if m is None:
            return
        m.title = work.title
        m.author = work.author
        m.lang_src = work.lang_src
        m.lang_tgt = work.lang_tgt
        m.status = work.status.value
        m.callback_url = work.callback_url
        m.missing_cleaned = work.missing_cleaned
        m.unreviewed_chapters = work.unreviewed_chapters
        self.db.flush()

    def delete(self, work_id: int) -> bool:
        m = self.db.get(WorkModel, work_id)
        if m is None:
            return False
        self.db.delete(m)  # cascade ORM: chapters, variants -> jobs -> segments
        self.db.flush()
        return True


class ChapterSourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_many(self, chapters: list[ChapterSource]) -> list[ChapterSource]:
        out: list[ChapterSource] = []
        for ch in chapters:
            m = ChapterSourceModel(
                work_id=ch.work_id,
                index=ch.index,
                title=ch.title,
                text=ch.text,
                fingerprint=ch.fingerprint,
            )
            self.db.add(m)
            self.db.flush()
            ch.id = m.id
            out.append(ch)
        return out

    def list_by_work(self, work_id: int) -> list[ChapterSource]:
        rows = (
            self.db.query(ChapterSourceModel)
            .filter(ChapterSourceModel.work_id == work_id)
            .order_by(ChapterSourceModel.index)
            .all()
        )
        return [_chapter_to_entity(m) for m in rows]

    def replace_for_work(self, work_id: int, chapters: list[ChapterSource]) -> list[ChapterSource]:
        self.db.query(ChapterSourceModel).filter(ChapterSourceModel.work_id == work_id).delete()
        self.db.flush()
        for ch in chapters:
            ch.work_id = work_id
        return self.add_many(chapters)


class VariantRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, variant: Variant) -> Variant:
        m = VariantModel(
            work_id=variant.work_id,
            mode=variant.mode,
            status=variant.status.value,
            lang_tgt=variant.lang_tgt,
            mode_params=variant.mode_params or {},
            source_variant_id=variant.source_variant_id,
        )
        self.db.add(m)
        self.db.flush()
        variant.id = m.id
        return variant

    def get(self, variant_id: int) -> Variant | None:
        m = self.db.get(VariantModel, variant_id)
        return _variant_to_entity(m) if m else None

    def list_by_work(self, work_id: int) -> list[Variant]:
        rows = self.db.query(VariantModel).filter(VariantModel.work_id == work_id).all()
        return [_variant_to_entity(m) for m in rows]

    def update_status(self, variant_id: int, status: VariantStatus) -> None:
        m = self.db.get(VariantModel, variant_id)
        if m is None:
            return
        m.status = status.value
        self.db.flush()

    def update(self, variant: Variant) -> None:
        m = self.db.get(VariantModel, variant.id)
        if m is None:
            return
        m.mode = variant.mode
        m.lang_tgt = variant.lang_tgt
        m.mode_params = variant.mode_params or {}
        m.status = variant.status.value
        m.source_variant_id = variant.source_variant_id
        self.db.flush()


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, job: Job) -> Job:
        m = JobModel(
            variant_id=job.variant_id,
            status=job.status.value,
            provider=job.provider,
            model=job.model,
            base_url=job.base_url or "",
            api_key=job.api_key or "",
            requires_api_key=1 if job.requires_api_key else 0,
            ai_provider_id=job.ai_provider_id,
            api_keys_json=json.dumps(job.api_keys or [], ensure_ascii=False),
            ai_mode=job.ai_mode,
            prompt_version=job.prompt_version,
            error=job.error,
        )
        self.db.add(m)
        self.db.flush()
        job.id = m.id
        return job

    def get(self, job_id: int) -> Job | None:
        m = self.db.get(JobModel, job_id)
        return _job_to_entity(m) if m else None

    def latest_for_variant(self, variant_id: int) -> Job | None:
        m = (
            self.db.query(JobModel)
            .filter(JobModel.variant_id == variant_id)
            .order_by(JobModel.id.desc())
            .first()
        )
        return _job_to_entity(m) if m else None

    def update(self, job: Job) -> None:
        m = self.db.get(JobModel, job.id)
        if m is None:
            return
        m.status = job.status.value
        m.error = job.error
        m.provider = job.provider
        m.model = job.model
        m.base_url = job.base_url or ""
        m.api_key = job.api_key or ""
        m.requires_api_key = 1 if job.requires_api_key else 0
        m.ai_provider_id = job.ai_provider_id
        m.api_keys_json = json.dumps(job.api_keys or [], ensure_ascii=False)
        self.db.flush()


class SegmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_many(self, segments: list[Segment]) -> list[Segment]:
        out: list[Segment] = []
        for seg in segments:
            m = SegmentModel(
                job_id=seg.job_id,
                chapter_index=seg.chapter_index,
                status=seg.status.value,
                source_text=seg.source_text,
                output_text=seg.output_text,
                cache_key=seg.cache_key,
                error=seg.error,
                reviewed=1 if seg.reviewed else 0,
                slot_index=seg.slot_index,
                story_state=seg.story_state,
            )
            self.db.add(m)
            self.db.flush()
            seg.id = m.id
            out.append(seg)
        return out

    def get(self, segment_id: int) -> Segment | None:
        m = self.db.get(SegmentModel, segment_id)
        return _segment_to_entity(m) if m else None

    def list_by_job(self, job_id: int) -> list[Segment]:
        rows = (
            self.db.query(SegmentModel)
            .filter(SegmentModel.job_id == job_id)
            .order_by(SegmentModel.chapter_index)
            .all()
        )
        return [_segment_to_entity(m) for m in rows]

    def get_by_job_and_chapter(self, job_id: int, chapter_index: int) -> Segment | None:
        m = (
            self.db.query(SegmentModel)
            .filter(SegmentModel.job_id == job_id, SegmentModel.chapter_index == chapter_index)
            .first()
        )
        return _segment_to_entity(m) if m else None

    def list_by_job_and_slot(self, job_id: int, slot_index: int) -> list[Segment]:
        rows = (
            self.db.query(SegmentModel)
            .filter(SegmentModel.job_id == job_id, SegmentModel.slot_index == slot_index)
            .order_by(SegmentModel.chapter_index)
            .all()
        )
        return [_segment_to_entity(m) for m in rows]

    def update(self, seg: Segment) -> None:
        m = self.db.get(SegmentModel, seg.id)
        if m is None:
            return
        m.status = seg.status.value
        m.output_text = seg.output_text
        m.cache_key = seg.cache_key
        m.error = seg.error
        m.reviewed = 1 if seg.reviewed else 0
        m.slot_index = seg.slot_index
        m.story_state = seg.story_state
        self.db.flush()


class GlossaryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_work(self, work_id: int) -> list[GlossaryTerm]:
        rows = (
            self.db.query(GlossaryTermModel)
            .filter(GlossaryTermModel.work_id == work_id)
            .order_by(GlossaryTermModel.source_term)
            .all()
        )
        return [_glossary_to_entity(m) for m in rows]

    def get(self, term_id: int) -> GlossaryTerm | None:
        m = self.db.get(GlossaryTermModel, term_id)
        return _glossary_to_entity(m) if m else None

    def add(self, term: GlossaryTerm) -> GlossaryTerm:
        m = GlossaryTermModel(
            work_id=term.work_id,
            source_term=term.source_term.strip(),
            target_term=term.target_term.strip(),
            protected=1 if term.protected else 0,
            notes=term.notes or "",
        )
        self.db.add(m)
        self.db.flush()
        term.id = m.id
        return term

    def update(self, term: GlossaryTerm) -> None:
        m = self.db.get(GlossaryTermModel, term.id)
        if m is None:
            return
        m.source_term = term.source_term.strip()
        m.target_term = term.target_term.strip()
        m.protected = 1 if term.protected else 0
        m.notes = term.notes or ""
        self.db.flush()

    def delete(self, term_id: int) -> bool:
        m = self.db.get(GlossaryTermModel, term_id)
        if m is None:
            return False
        self.db.delete(m)
        self.db.flush()
        return True


class TranslationCacheRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str) -> str | None:
        m = self.db.get(TranslationCacheModel, key)
        return m.output_text if m else None

    def put(self, key: str, output_text: str) -> None:
        m = self.db.get(TranslationCacheModel, key)
        if m is None:
            self.db.add(TranslationCacheModel(cache_key=key, output_text=output_text))
        else:
            m.output_text = output_text
        self.db.flush()


class AiProviderRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, p: AiProvider) -> AiProvider:
        m = AiProviderModel(
            label=p.label,
            kind=p.kind,
            provider=p.provider,
            base_url=p.base_url,
            model=p.model,
            api_key=p.api_key,
            api_keys_json=json.dumps(p.api_keys, ensure_ascii=False),
            requires_api_key=1 if p.requires_api_key else 0,
            sort_order=p.sort_order,
        )
        self.db.add(m)
        self.db.flush()
        p.id = m.id
        return p

    def get(self, provider_id: int) -> AiProvider | None:
        m = self.db.get(AiProviderModel, provider_id)
        return _ai_provider_to_entity(m) if m else None

    def list_all(self) -> list[AiProvider]:
        rows = (
            self.db.query(AiProviderModel)
            .order_by(AiProviderModel.sort_order, AiProviderModel.id)
            .all()
        )
        return [_ai_provider_to_entity(m) for m in rows]

    def count(self) -> int:
        return self.db.query(AiProviderModel).count()

    def update(self, p: AiProvider) -> None:
        m = self.db.get(AiProviderModel, p.id)
        if m is None:
            return
        m.label = p.label
        m.kind = p.kind
        m.provider = p.provider
        m.base_url = p.base_url
        m.model = p.model
        m.api_key = p.api_key
        m.api_keys_json = json.dumps(p.api_keys, ensure_ascii=False)
        m.requires_api_key = 1 if p.requires_api_key else 0
        m.sort_order = p.sort_order
        self.db.flush()

    def delete(self, provider_id: int) -> bool:
        m = self.db.get(AiProviderModel, provider_id)
        if m is None:
            return False
        self.db.delete(m)
        self.db.flush()
        return True


class JobProviderSlotRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_many(self, slots: list[JobProviderSlot]) -> list[JobProviderSlot]:
        out: list[JobProviderSlot] = []
        for s in slots:
            m = JobProviderSlotModel(
                job_id=s.job_id,
                slot_index=s.slot_index,
                provider=s.provider,
                model=s.model,
                base_url=s.base_url,
                api_key=s.api_key,
                requires_api_key=1 if s.requires_api_key else 0,
                label=s.label,
                ai_provider_id=s.ai_provider_id,
            )
            self.db.add(m)
            self.db.flush()
            s.id = m.id
            out.append(s)
        return out

    def list_by_job(self, job_id: int) -> list[JobProviderSlot]:
        rows = (
            self.db.query(JobProviderSlotModel)
            .filter(JobProviderSlotModel.job_id == job_id)
            .order_by(JobProviderSlotModel.slot_index)
            .all()
        )
        return [_job_provider_slot_to_entity(m) for m in rows]

    def update(self, slot: JobProviderSlot) -> None:
        m = self.db.get(JobProviderSlotModel, slot.id)
        if m is None:
            return
        m.provider = slot.provider
        m.model = slot.model
        m.base_url = slot.base_url or ""
        m.api_key = slot.api_key or ""
        m.requires_api_key = 1 if slot.requires_api_key else 0
        m.label = slot.label or ""
        m.ai_provider_id = slot.ai_provider_id
        self.db.flush()
