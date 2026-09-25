"""Use case — orchestrate domain services + ports. KHÔNG biết SourcePort nào
đang chạy thật (httpx hay browser), KHÔNG biết Repository lưu SQLite hay
Postgres — chỉ biết qua Protocol khai báo ở domain/ports.py."""
import logging
from collections.abc import Callable
from pathlib import Path

from crawl.application.dto import (
    ChapterContentResult,
    ChapterRetryResult,
    CrawlGenreResult,
    CrawlNovelResult,
    DeleteResult,
    DryRunResult,
    NovelExportStatus,
    ReviewAllResult,
    SmoothNovelResult,
)
from crawl.application.progress import CrawlProgress, ProgressCallback, noop_progress
from crawl.domain.entities import (
    Chapter, ChapterStatus, DomainError, Genre, GenreRunStatus, Novel, NovelLifecycle,
)
from crawl.domain.ports import (
    ChapterRepository,
    DuplicateError,
    GenreRepository,
    NovelRepository,
    ScrapeError,
    SourcePort,
)
from crawl.application.chapter_resolve import try_list_chapters
from crawl.application.fingerprint import content_fingerprint
from crawl.application.opencc_convert import apply_opencc
from crawl.domain.services import (
    CHAPTER_COMMIT_BATCH,
    CHAPTER_SAMPLE_LIMIT,
    MAX_CONSECUTIVE_CHAPTER_FAILURES,
    MAX_EXISTING_SYNCS_PER_SCAN,
    chapter_failure_counts_toward_block,
    evaluate_candidate,
    is_completed,
    is_genre_list_noise,
    matches_narration_filter,
    validate_chapter_content,
)
from crawl.domain.value_objects import ChapterRef

logger = logging.getLogger("crawl")

_NARRATION_FILTER_LABELS = {"first_person": 'ngôi thứ nhất ("tôi")', "third_person": "ngôi thứ ba"}


def _content_locale(source: SourcePort) -> str:
    cfg = getattr(source, "cfg", None)
    return getattr(cfg, "content_locale", "zh") if cfg else "zh"


def _try_fetch_novel_meta(source: SourcePort, novel_url: str) -> tuple[str, str]:
    """author, cover_url — nuốt lỗi parse (không chặn crawl)."""
    author = ""
    cover = ""
    fetch_author = getattr(source, "fetch_novel_author", None)
    fetch_cover = getattr(source, "fetch_novel_cover_url", None)
    if callable(fetch_author):
        try:
            author = (fetch_author(novel_url) or "").strip()
        except Exception:
            logger.debug("fetch_novel_author failed for %s", novel_url, exc_info=True)
    if callable(fetch_cover):
        try:
            cover = (fetch_cover(novel_url) or "").strip()
        except Exception:
            logger.debug("fetch_novel_cover_url failed for %s", novel_url, exc_info=True)
    return author, cover


def is_completed_for_novel(chapters: list[ChapterRef], locale: str) -> bool:
    if not chapters:
        return False
    return is_completed(chapters[-1].title, locale=locale, total_chapters=len(chapters))


def _skip_chapter_and_maybe_stop(
    *,
    novel: Novel,
    ref: ChapterRef,
    reason: str,
    consecutive_block_failures: int,
    novel_repo: NovelRepository,
    pending_since_commit: int,
    crawled_count: int,
    novel_id: int,
) -> tuple[int, int, CrawlNovelResult | None]:
    """Bỏ qua 1 chương lỗi; KHÔNG advance last_chapter_index — để lần sau
    (sau khi cập nhật cookie) còn retry được chương VIP/lỗi. Trả
    (consecutive mới, pending mới, None) hoặc CrawlNovelResult lỗi."""
    counts = chapter_failure_counts_toward_block(reason)
    next_consecutive = consecutive_block_failures + 1 if counts else 0
    logger.warning(
        "Bỏ qua chương %s novel %s — %s (thử chương sau%s)",
        ref.index,
        novel.id,
        reason,
        "" if counts else ", lỗi riêng chương",
    )
    if counts and next_consecutive >= MAX_CONSECUTIVE_CHAPTER_FAILURES:
        novel_repo.commit()
        msg = (
            f"{next_consecutive} chương liên tiếp lỗi "
            f"(cuối: chương {ref.index}: {reason}) — "
            f"site có thể đang lỗi/chặn tạm thời, thử lại sau"
        )
        novel.mark_error(msg)
        novel_repo.update(novel)
        return next_consecutive, pending_since_commit, CrawlNovelResult.failure(
            novel_id, msg, chapters_crawled=crawled_count
        )
    # Chỉ commit định kỳ trạng thái novel (không nhảy last_chapter_index).
    pending = pending_since_commit + 1
    if pending >= CHAPTER_COMMIT_BATCH:
        novel_repo.commit()
        pending = 0
    return next_consecutive, pending, None


def check_narration_filter_sample(
    source: SourcePort, chapters: list[ChapterRef], narration_filter: str
) -> tuple[bool, str]:
    """Lọc theo ngôi kể đã chọn ở Settings (`crawl.narration_filter`:
    "any"/"first_person"/"third_person") — dùng chung giữa CrawlGenreUseCase
    và AddManualNovelUseCase. Tải chương ĐẦU TIÊN làm mẫu (chưa fetch ở bước
    evaluate_candidate, vốn chỉ đọc title) để đoán ngôi kể trên nội dung
    THẬT, không đoán qua tiêu đề. `narration_filter="any"` luôn pass mà
    không tải gì thêm — không tốn request thừa khi không cần lọc."""
    if narration_filter == "any":
        return True, ""
    if not chapters:
        return False, "Không có chương nào để lấy mẫu kiểm tra ngôi kể"
    locale = _content_locale(source)
    sample_limit = min(len(chapters), CHAPTER_SAMPLE_LIMIT)
    last_reason = "Không lấy được mẫu chương đủ dài để kiểm tra ngôi kể"
    for ref in chapters[:sample_limit]:
        try:
            sample_text = source.fetch_chapter_content(ref.url)
        except ScrapeError as exc:
            last_reason = f"Không lấy được mẫu chương {ref.index}: {exc}"
            continue
        ok, reason = validate_chapter_content(sample_text, locale=locale)
        if not ok:
            last_reason = f"Chương {ref.index} mẫu không hợp lệ: {reason}"
            continue
        if not matches_narration_filter(sample_text, narration_filter, locale=locale):
            label = _NARRATION_FILTER_LABELS.get(narration_filter, narration_filter)
            return False, f"Truyện không kể theo {label}"
        return True, ""
    return False, last_reason


class RawTextStorage:
    """Cổng lưu file raw text — tách riêng để test không cần đụng ổ đĩa thật.
    Bản làm mượt nằm song song: data/raw/{id}/N.txt → data/cleaned/{id}/N.txt
    (không đè raw)."""

    def __init__(self, raw_dir):
        self.raw_dir = Path(raw_dir)
        self.cleaned_dir = self.raw_dir.parent / "cleaned"

    def save(self, novel_id: int, chapter_index: int, text: str) -> str:
        novel_dir = self.raw_dir / str(novel_id)
        novel_dir.mkdir(parents=True, exist_ok=True)
        path = novel_dir / f"{chapter_index:04d}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def cleaned_path_for(self, raw_path: str) -> str:
        """Map raw path → cleaned path cùng novel_id/filename."""
        p = Path(raw_path)
        # .../raw/12/0001.txt → .../cleaned/12/0001.txt
        try:
            rel = p.relative_to(self.raw_dir)
        except ValueError:
            # Path lạ (test/tmp) — đặt cạnh file raw trong thư mục cleaned/
            return str(self.cleaned_dir / p.parent.name / p.name)
        return str(self.cleaned_dir / rel)

    def has_cleaned(self, raw_path: str) -> bool:
        return Path(self.cleaned_path_for(raw_path)).is_file()

    def save_cleaned(self, raw_path: str, text: str) -> str:
        out = Path(self.cleaned_path_for(raw_path))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        return str(out)

    def discard_cleaned(self, raw_path: str) -> bool:
        """Xóa bản cleaned nếu có — trở về chỉ dùng raw. Trả True nếu đã xóa."""
        cleaned = Path(self.cleaned_path_for(raw_path))
        if not cleaned.is_file():
            return False
        cleaned.unlink()
        return True

    def delete_chapter_files(self, raw_path: str | None) -> None:
        """Xóa file raw + cleaned của 1 chương (bỏ qua nếu không có)."""
        if not raw_path:
            return
        p = Path(raw_path)
        if p.is_file():
            p.unlink()
        self.discard_cleaned(raw_path)

    def delete_novel_dirs(self, novel_id: int) -> None:
        """Xóa thư mục raw/cleaned của cả truyện (nếu còn)."""
        import shutil

        for base in (self.raw_dir, self.cleaned_dir):
            d = base / str(novel_id)
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    def read_preferred(self, raw_path: str) -> tuple[str, str]:
        """Trả (content, source) — ưu tiên cleaned nếu có."""
        cleaned = Path(self.cleaned_path_for(raw_path))
        if cleaned.is_file():
            return cleaned.read_text(encoding="utf-8"), "cleaned"
        return Path(raw_path).read_text(encoding="utf-8"), "raw"

    def read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def overwrite(self, path: str, text: str) -> None:
        """Dùng khi review/sửa nội dung 1 chương đã crawl (mục "review
        chương") — ghi đè đúng file cũ, KHÔNG đổi raw_path."""
        Path(path).write_text(text, encoding="utf-8")

    def overwrite_preferred(self, raw_path: str, text: str) -> str:
        """Review sau làm mượt: ghi cleaned nếu đã có, không thì ghi raw."""
        if self.has_cleaned(raw_path):
            return self.save_cleaned(raw_path, text)
        self.overwrite(raw_path, text)
        return raw_path


class CrawlNovelUseCase:
    """Crawl TOÀN BỘ 1 truyện (không phải chỉ chương mới — vì chỉ nhận
    truyện đã hoàn thành, đây là lần đầu và cũng là lần duy nhất crawl
    truyện này). Resume: nếu lỗi giữa chừng, lần sau chỉ crawl tiếp phần
    còn thiếu nhờ Novel.last_chapter_index (crawl-service.md mục 6)."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
        source_resolver,
        on_progress: ProgressCallback | None = None,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage
        self.source_resolver = source_resolver
        self.on_progress = on_progress or noop_progress

    def execute(
        self,
        novel_id: int,
        prefetched_chapters: list[ChapterRef] | None = None,
        *,
        incremental: bool = False,
        on_progress: ProgressCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> CrawlNovelResult:
        report = on_progress or self.on_progress
        stop_check = should_stop
        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return CrawlNovelResult.failure(novel_id, "Không tìm thấy novel")

        task_id = f"novel:{novel_id}"

        def emit(**kwargs) -> None:
            report(
                CrawlProgress(
                    task_id=task_id,
                    kind="novel",
                    label=f"novel#{novel_id}",
                    novel_title=novel.title or "",
                    **kwargs,
                )
            )

        try:
            source: SourcePort = self.source_resolver(novel.source_key)
        except KeyError as exc:
            return CrawlNovelResult.failure(novel_id, f"Nguồn không còn hỗ trợ: {exc}")

        if novel.lifecycle_status != NovelLifecycle.CRAWLING:
            try:
                if incremental:
                    novel.start_incremental_crawl()
                else:
                    novel.start_crawling()
            except DomainError as exc:
                return CrawlNovelResult.failure(novel_id, str(exc))
            self.novel_repo.update(novel)

        if prefetched_chapters is not None:
            chapters = prefetched_chapters
        else:
            emit(phase="listing", message="Đang lấy mục lục…")
            chapters, list_err = try_list_chapters(source, novel.source_url)
            if chapters is None:
                novel.mark_error(list_err or "Không lấy được mục lục")
                self.novel_repo.update(novel)
                emit(phase="error", message=list_err or "Không lấy được mục lục")
                return CrawlNovelResult.failure(novel_id, list_err or "Không lấy được mục lục")

        novel.total_chapters = len(chapters)
        self.novel_repo.update(novel, commit=True)
        emit(phase="crawling", chapter_index=novel.last_chapter_index, chapter_total=len(chapters))

        already_saved = {c.chapter_index for c in self.chapter_repo.list_by_novel(novel.id)}
        crawled_count = 0
        pending_since_commit = 0
        consecutive_block_failures = 0
        attempted_new = False
        for ref in chapters:
            # SQLite: nhả write-txn trước HTTP fetch (tránh lock xuyên suốt
            # lúc tải chương — thread quét/API khác bị "database is locked").
            if pending_since_commit:
                self.novel_repo.commit()
                pending_since_commit = 0
            if stop_check and stop_check():
                msg = "Đã hủy quét"
                novel.mark_error(msg)
                self.novel_repo.update(novel)
                emit(
                    phase="cancelled",
                    chapter_index=ref.index,
                    chapter_total=len(chapters),
                    message=msg,
                )
                return CrawlNovelResult.failure(
                    novel_id, msg, chapters_crawled=crawled_count, cancelled=True
                )
            if ref.index in already_saved:
                continue  # đã có trong DB — resume không nhảy qua lỗ nhờ last_chapter_index
            attempted_new = True
            emit(
                phase="crawling",
                chapter_index=ref.index,
                chapter_total=len(chapters),
                message=ref.title or "",
            )
            try:
                text = source.fetch_chapter_content(ref.url)
            except ScrapeError as exc:
                consecutive_block_failures, pending_since_commit, fail = _skip_chapter_and_maybe_stop(
                    novel=novel,
                    ref=ref,
                    reason=str(exc),
                    consecutive_block_failures=consecutive_block_failures,
                    novel_repo=self.novel_repo,
                    pending_since_commit=pending_since_commit,
                    crawled_count=crawled_count,
                    novel_id=novel_id,
                )
                if fail is not None:
                    emit(
                        phase="error", chapter_index=ref.index,
                        chapter_total=len(chapters), message=str(exc),
                    )
                    return fail
                continue

            ok, reason = validate_chapter_content(text, locale=_content_locale(source))
            if not ok:
                assert reason is not None
                consecutive_block_failures, pending_since_commit, fail = _skip_chapter_and_maybe_stop(
                    novel=novel,
                    ref=ref,
                    reason=reason,
                    consecutive_block_failures=consecutive_block_failures,
                    novel_repo=self.novel_repo,
                    pending_since_commit=pending_since_commit,
                    crawled_count=crawled_count,
                    novel_id=novel_id,
                )
                if fail is not None:
                    emit(phase="error", chapter_index=ref.index, chapter_total=len(chapters), message=reason)
                    return fail
                continue

            consecutive_block_failures = 0
            raw_path = self.storage.save(novel.id, ref.index, text)
            chapter = Chapter(
                id=None, novel_id=novel.id, chapter_index=ref.index, title=ref.title, source_url=ref.url,
            )
            chapter.mark_crawled(raw_path)
            try:
                self.chapter_repo.add(chapter, commit=True)
                already_saved.add(ref.index)
            except DuplicateError:
                # Race condition: 1 request khác (vd job lịch + bấm tay
                # cùng lúc) đã crawl xong đúng chương này rồi — không phải
                # lỗi, coi như đã xong, đi tiếp chương sau thay vì fail cả
                # truyện (platform_.locks.keyed_lock ở tầng router là lớp
                # chặn chính, đây là lớp phòng thủ thứ 2).
                logger.warning(
                    "Chương %s của novel %s đã được crawl bởi request khác, bỏ qua", ref.index, novel.id
                )
                already_saved.add(ref.index)
            novel.advance_chapter(ref.index)
            self.novel_repo.update(novel, commit=True)
            crawled_count += 1
            pending_since_commit = 0

        if attempted_new and crawled_count == 0:
            msg = "Không lưu được chương nào (toàn bộ bị bỏ qua/lỗi) — kiểm tra cookie site hoặc thử lại"
            novel.mark_error(msg)
            self.novel_repo.update(novel)
            emit(phase="error", chapter_total=len(chapters), message=msg)
            return CrawlNovelResult.failure(novel_id, msg, chapters_crawled=0)

        missing = [c.index for c in chapters if c.index not in already_saved]
        if missing:
            msg = (
                f"Thiếu {len(missing)} chương (vd {missing[0]}"
                f"{'…' + str(missing[-1]) if len(missing) > 1 else ''}) "
                "— VIP/lỗi nội dung; cập nhật cookie rồi Retry để lấy nốt"
            )
            # Sửa 17/9/2026 (quyết định thật, không tự đoán): 1 vài chương
            # bị bỏ qua LẺ TẺ (không đủ để chạm circuit breaker
            # MAX_CONSECUTIVE_CHAPTER_FAILURES ở trên — trường hợp đó đã
            # return sớm với lifecycle_status=error rồi, không tới được
            # đây) không nên chặn CẢ TRUYỆN thành "error" — mới thấy 1 lỗi
            # mạng thoáng qua ở 1 chương mà bắt người dùng tự bấm Retry cho
            # NGUYÊN 1 truyện là quá nặng tay, trong khi bản chất Retry
            # cũng chỉ bù đúng phần thiếu này (mục 9.2b crawl-service.md).
            # Coi là THÀNH CÔNG có ghi chú — vẫn `error_message` để KHÔNG
            # im lặng (mục 9), FE hiện rõ dù trạng thái không phải "error".
            novel.mark_fully_crawled()
            novel.error_message = msg
            self._apply_content_fingerprint(novel)
            self.novel_repo.update(novel)
            emit(phase="done", chapter_total=len(chapters), message=msg)
            return CrawlNovelResult(
                novel_id=novel_id, chapters_crawled=crawled_count, success=True, error=msg,
            )

        novel.mark_fully_crawled()
        # Xoá ghi chú "thiếu chương" từ lần chạy TRƯỚC nếu lần này đã bù đủ
        # (vd Retry sau khi cập nhật cookie) — không để lại cảnh báo cũ đã
        # hết hiệu lực (mục 9 — "không có gì im lặng" cũng có nghĩa là
        # không giữ lại cảnh báo SAI khi mọi thứ đã ổn).
        novel.error_message = None
        self._apply_content_fingerprint(novel)
        self.novel_repo.update(novel)
        emit(
            phase="done", chapter_index=len(chapters),
            chapter_total=len(chapters), message=f"+{crawled_count} ch",
        )
        return CrawlNovelResult(novel_id=novel_id, chapters_crawled=crawled_count, success=True)

    def _apply_content_fingerprint(self, novel: Novel) -> None:
        """Hash vài chương đầu — cảnh báo nếu trùng nội dung với truyện khác."""
        assert novel.id is not None
        chapters = sorted(
            (c for c in self.chapter_repo.list_by_novel(novel.id) if c.raw_path),
            key=lambda c: c.chapter_index,
        )[:3]
        texts: list[str] = []
        for ch in chapters:
            try:
                texts.append(self.storage.read(ch.raw_path))
            except OSError:
                continue
        if not texts:
            return
        fp = content_fingerprint(*texts)
        novel.content_fingerprint = fp
        other = self.novel_repo.get_by_fingerprint(fp)
        if other is not None and other.id != novel.id:
            note = f"Trùng nội dung với truyện #{other.id} ({other.title})"
            novel.error_message = f"{novel.error_message}; {note}" if novel.error_message else note


class CrawlGenreUseCase:
    """Job hàng ngày cho 1 thể loại: quét scan_window truyện đầu danh sách,
    bỏ qua truyện đã biết, đánh giá tiêu chí ngắn+hoàn thành cho truyện mới,
    crawl toàn bộ nếu đạt (crawl-service.md mục 6)."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        genre_repo: GenreRepository,
        crawl_novel_use_case: CrawlNovelUseCase,
        source_resolver,
        get_scan_window,
        get_max_chapters_per_story,
        get_narration_filter=lambda source_key: "any",
        get_max_pages_per_scan=lambda source_key: 3,
        get_max_consecutive_errors=lambda source_key: 5,
        get_completion_filter=lambda source_key: "completed_only",
        on_progress: ProgressCallback | None = None,
    ):
        """`get_*` nhận `source_key` — mỗi site tự chỉnh setting quét RIÊNG
        (mục 9.0, sửa 16/9/2026 theo yêu cầu "setting riêng cho từng site"),
        không còn dùng chung 1 giá trị toàn hệ thống."""
        self.novel_repo = novel_repo
        self.genre_repo = genre_repo
        self.crawl_novel_use_case = crawl_novel_use_case
        self.source_resolver = source_resolver
        self.get_scan_window = get_scan_window
        self.get_max_chapters_per_story = get_max_chapters_per_story
        self.get_narration_filter = get_narration_filter
        self.get_max_pages_per_scan = get_max_pages_per_scan
        self.get_max_consecutive_errors = get_max_consecutive_errors
        self.get_completion_filter = get_completion_filter
        self.on_progress = on_progress or noop_progress

    def execute(self, genre_id: int) -> CrawlGenreResult:
        """Quét thật có thể mất nhiều phút (nhiều truyện x nhiều chương,
        retry/backoff khi site chậm) — LƯU trạng thái running/done/error vào
        Genre ngay khi bắt đầu/kết thúc (không chỉ trả về response), để FE
        (và cả người bấm "Quét ngay" xong tải lại trang) luôn biết đúng
        trạng thái thay vì tưởng nhầm không có gì chạy (crawl-service.md
        mục 9.2)."""
        from platform_.run_cancel import begin_run, end_run

        begin_run(genre_id)
        try:
            return self._execute_inner(genre_id)
        finally:
            end_run(genre_id)

    def _execute_inner(self, genre_id: int) -> CrawlGenreResult:
        result = CrawlGenreResult(genre_id=genre_id)
        genre = self.genre_repo.get_by_id(genre_id)
        if genre is None or not genre.enabled:
            result.messages.append("Thể loại không tồn tại hoặc đang tắt")
            # Router /run-now có thể đã mark RUNNING trước khi thread này chạy
            # — phải đóng trạng thái, không để kẹt running mãi.
            if genre is not None and genre.last_run_status == GenreRunStatus.RUNNING:
                genre.mark_run_finished(
                    status=GenreRunStatus.ERROR, discovered=0, rejected=0, errors=1,
                    messages=result.messages,
                )
                self.genre_repo.update(genre)
            return result

        if genre.last_run_status != GenreRunStatus.RUNNING:
            genre.mark_run_started()
            self.genre_repo.update(genre)
        try:
            self._scan(genre, result)
        except Exception as exc:
            # An toàn cho tiến trình chạy nền/job lịch — không để crash bất
            # ngờ khiến trạng thái kẹt mãi ở "running".
            logger.exception("Lỗi không mong đợi khi crawl genre %s", genre.label)
            result.errors += 1
            result.messages.append(f"Lỗi không mong đợi: {exc}")
            genre.mark_run_finished(
                status=GenreRunStatus.ERROR, discovered=result.discovered,
                rejected=result.rejected, errors=result.errors, messages=result.messages,
            )
            self.on_progress(
                CrawlProgress(
                    task_id=f"genre:{genre_id}",
                    kind="genre",
                    label=f"{genre.source_key}/{genre.genre_key}",
                    phase="error",
                    discovered=result.discovered,
                    rejected=result.rejected,
                    errors=result.errors,
                    message=str(exc),
                )
            )
        else:
            if result.cancelled:
                status = GenreRunStatus.CANCELLED
                phase = "cancelled"
            elif result.stopped_as_error:
                status = GenreRunStatus.ERROR
                phase = "error"
            else:
                status = GenreRunStatus.DONE
                phase = "done"
            genre.mark_run_finished(
                status=status, discovered=result.discovered,
                rejected=result.rejected, errors=result.errors, messages=result.messages,
            )
            self.on_progress(
                CrawlProgress(
                    task_id=f"genre:{genre_id}",
                    kind="genre",
                    label=f"{genre.source_key}/{genre.genre_key}",
                    phase=phase,
                    discovered=result.discovered,
                    rejected=result.rejected,
                    errors=result.errors,
                    synced=result.synced,
                    message="; ".join(result.messages[:2]) if result.messages else "xong",
                )
            )
        self.genre_repo.update(genre)
        return result

    def _scan(self, genre: Genre, result: CrawlGenreResult) -> None:
        """Quét tới khi đủ `scan_window` truyện MỚI chấp nhận (crawl được),
        hết list, hoặc `max_pages_per_scan`. Dừng sớm nếu
        `max_consecutive_errors` lỗi liên tiếp (site chết / chặn bot)
        hoặc người dùng bấm Dừng quét."""
        from platform_.run_cancel import is_cancelled

        source = self.source_resolver(genre.source_key)
        scan_window = self.get_scan_window(genre.source_key)
        max_chapters_per_story = self.get_max_chapters_per_story(genre.source_key)
        max_pages = max(1, self.get_max_pages_per_scan(genre.source_key))
        max_consecutive_errors = max(1, self.get_max_consecutive_errors(genre.source_key))
        consecutive_errors = 0
        existing_syncs = 0
        skipped_noise = 0
        seen_existing = 0
        evaluated = 0
        list_base_url = getattr(getattr(source, "cfg", None), "base_url", "") or ""
        task_id = f"genre:{genre.id}"
        label = f"{genre.source_key}/{genre.genre_key}"
        locale = _content_locale(source)

        def should_stop() -> bool:
            return is_cancelled(genre.id)

        def emit(**kwargs) -> None:
            self.on_progress(
                CrawlProgress(
                    task_id=task_id,
                    kind="genre",
                    label=label,
                    scan_window=scan_window,
                    max_pages=max_pages,
                    discovered=result.discovered,
                    rejected=result.rejected,
                    errors=result.errors,
                    synced=result.synced,
                    **kwargs,
                )
            )

        def mark_cancelled(page: int = 0, message: str = "Đã dừng theo yêu cầu") -> None:
            result.cancelled = True
            if message not in result.messages:
                result.messages.append(message)
            emit(phase="cancelled", page=page, message=message)

        page = 1
        while result.discovered < scan_window and page <= max_pages:
            if should_stop():
                mark_cancelled(page=page)
                return
            emit(phase="listing", page=page, message=f"Lấy danh sách trang {page}…")
            try:
                candidates = source.list_genre_novels_page(genre.list_url, page)
            except ScrapeError as exc:
                result.errors += 1
                result.messages.append(f"Lỗi lấy danh sách thể loại (trang {page}): {exc}")
                result.stopped_as_error = True
                emit(phase="error", page=page, message=str(exc))
                return
            if not candidates:
                if page == 1:
                    result.messages.append("Danh sách thể loại rỗng")
                break

            for candidate in candidates:
                if should_stop():
                    mark_cancelled(page=page)
                    return
                if result.discovered >= scan_window:
                    break

                if is_genre_list_noise(candidate, base_url=list_base_url):
                    skipped_noise += 1
                    continue

                existing = self.novel_repo.get_by_source_url(genre.source_key, candidate.url)
                if existing is not None:
                    if existing.lifecycle_status == NovelLifecycle.REJECTED:
                        consecutive_errors = self._try_reevaluate_rejected(
                            existing,
                            candidate,
                            source,
                            result,
                            consecutive_errors,
                            max_chapters_per_story,
                            locale,
                            page,
                            emit,
                            should_stop=should_stop,
                        )
                        if result.cancelled:
                            return
                        if consecutive_errors >= max_consecutive_errors:
                            result.messages.append(
                                f"Dừng sớm sau {consecutive_errors} lỗi liên tiếp — site "
                                f"'{genre.source_key}' có thể đang lỗi/chặn, thử lại sau."
                            )
                            result.stopped_as_error = True
                            emit(phase="error", page=page, message="Quá nhiều lỗi liên tiếp")
                            return
                        continue

                    can_sync = (
                        existing_syncs < MAX_EXISTING_SYNCS_PER_SCAN
                        and existing.lifecycle_status
                        in (
                            NovelLifecycle.FULLY_CRAWLED,
                            NovelLifecycle.ERROR,
                            NovelLifecycle.DISCOVERED,
                        )
                    )
                    if can_sync:
                        existing_syncs += 1
                        emit(
                            phase="evaluating",
                            page=page,
                            novel_title=candidate.title,
                            message="Đồng bộ truyện đã có…",
                        )
                        consecutive_errors = self._try_sync_existing_novel(
                            existing,
                            candidate,
                            source,
                            result,
                            consecutive_errors,
                            should_stop=should_stop,
                        )
                        if result.cancelled:
                            return
                        if consecutive_errors >= max_consecutive_errors:
                            result.messages.append(
                                f"Dừng sớm sau {consecutive_errors} lỗi liên tiếp — site "
                                f"'{genre.source_key}' có thể đang lỗi/chặn, thử lại sau."
                            )
                            result.stopped_as_error = True
                            emit(phase="error", page=page, message="Quá nhiều lỗi liên tiếp")
                            return
                    else:
                        seen_existing += 1
                    continue

                emit(
                    phase="evaluating",
                    page=page,
                    novel_title=candidate.title,
                    message="Lấy mục lục / đánh giá…",
                )
                chapters, list_err = try_list_chapters(source, candidate.url)
                if chapters is None:
                    result.errors += 1
                    result.messages.append(
                        f"Lỗi lấy chương của '{candidate.title}': {list_err}"
                    )
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        result.messages.append(
                            f"Dừng sớm sau {consecutive_errors} lỗi liên tiếp — site "
                            f"'{genre.source_key}' có thể đang lỗi/chặn, thử lại sau."
                        )
                        result.stopped_as_error = True
                        emit(phase="error", page=page, message="Quá nhiều lỗi liên tiếp")
                        return
                    continue
                consecutive_errors = 0
                evaluated += 1

                completion_filter = self.get_completion_filter(genre.source_key)
                accepted, reason = evaluate_candidate(
                    chapters,
                    max_chapters_per_story,
                    completion_filter,
                    locale=locale,
                )

                if accepted:
                    narration_filter = self.get_narration_filter(genre.source_key)
                    accepted, reason = check_narration_filter_sample(
                        source, chapters, narration_filter
                    )

                author, cover_url = ("", "")
                if accepted:
                    author, cover_url = _try_fetch_novel_meta(source, candidate.url)

                novel = Novel(
                    id=None, title=candidate.title, source_key=genre.source_key, source_url=candidate.url,
                    genre_id=genre.id, total_chapters=len(chapters),
                    is_complete=bool(chapters) and is_completed_for_novel(chapters, locale),
                    author=author, cover_url=cover_url,
                )
                if not accepted:
                    novel.reject(reason)
                try:
                    saved = self.novel_repo.add(novel)
                except DuplicateError:
                    seen_existing += 1
                    continue

                if not accepted:
                    result.rejected += 1
                    emit(phase="evaluating", page=page, novel_title=candidate.title, message="Loại")
                    continue

                emit(
                    phase="crawling",
                    page=page,
                    novel_title=candidate.title,
                    chapter_total=len(chapters),
                    chapter_index=0,
                    message="Đang crawl…",
                )

                # noqa cho B023: `_nested` chỉ được `execute()` gọi ĐỒNG BỘ
                # ngay bên dưới, luôn xong trước khi vòng lặp `for candidate`
                # sang candidate/page kế tiếp — không có chuyện đọc phải giá
                # trị "stale" của closure dù về mặt cú pháp là bind theo tham chiếu.
                def _nested(p: CrawlProgress) -> None:
                    emit(
                        phase="crawling",
                        page=page,  # noqa: B023
                        novel_title=candidate.title,  # noqa: B023
                        chapter_index=p.chapter_index,
                        chapter_total=p.chapter_total or len(chapters),  # noqa: B023
                        message=p.message or p.phase,
                    )

                crawl_result = self.crawl_novel_use_case.execute(
                    saved.id,
                    prefetched_chapters=chapters,
                    on_progress=_nested,
                    should_stop=should_stop,
                )
                if crawl_result.cancelled:
                    if crawl_result.chapters_crawled > 0:
                        result.discovered += 1
                    mark_cancelled(page=page)
                    return
                if crawl_result.success or crawl_result.chapters_crawled > 0:
                    result.discovered += 1
                if not crawl_result.success:
                    if crawl_result.chapters_crawled > 0:
                        result.messages.append(
                            f"Crawl một phần '{candidate.title}' "
                            f"({crawl_result.chapters_crawled} chương): {crawl_result.error}"
                        )
                    else:
                        result.errors += 1
                        result.messages.append(
                            f"Lỗi crawl '{candidate.title}': {crawl_result.error}"
                        )

            page += 1

        if result.discovered < scan_window and page > max_pages:
            if evaluated == 0 and (skipped_noise or seen_existing):
                bits = []
                if skipped_noise:
                    bits.append(f"{skipped_noise} mục quảng cáo/link ngoài")
                if seen_existing:
                    bits.append(f"{seen_existing} truyện đã có trong thư viện")
                result.messages.append(
                    f"Đã dò {max_pages} trang nhưng không đánh giá được ứng viên mới "
                    f"({', '.join(bits)}) — thử thể loại khác hoặc tăng số trang."
                )
            else:
                result.messages.append(
                    f"Đã dò {max_pages} trang vẫn chưa đủ {scan_window} truyện đạt tiêu chí "
                    "— tăng 'Số trang tối đa/lượt quét' ở Cài đặt nếu muốn dò sâu hơn."
                )
        if result.synced:
            result.messages.append(
                f"Đã bổ sung chương mới cho {result.synced} truyện có sẵn (site đẩy lên đầu danh sách)"
            )

    def _try_reevaluate_rejected(
        self,
        existing: Novel,
        candidate,
        source: SourcePort,
        result: CrawlGenreResult,
        consecutive_errors: int,
        max_chapters_per_story: int,
        locale: str,
        page: int,
        emit,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> int:
        """Truyện từng bị loại — đánh giá lại khi filter/TOC đổi (vd đã hoàn thành)."""
        emit(
            phase="evaluating",
            page=page,
            novel_title=candidate.title,
            message="Đánh giá lại truyện đã loại…",
        )
        chapters, list_err = try_list_chapters(source, candidate.url)
        if chapters is None:
            result.errors += 1
            result.messages.append(
                f"Lỗi lấy chương (re-eval) '{candidate.title}': {list_err}"
            )
            return consecutive_errors + 1

        completion_filter = self.get_completion_filter(existing.source_key)
        accepted, reason = evaluate_candidate(
            chapters, max_chapters_per_story, completion_filter, locale=locale
        )
        if accepted:
            narration_filter = self.get_narration_filter(existing.source_key)
            accepted, reason = check_narration_filter_sample(source, chapters, narration_filter)

        if not accepted:
            if reason and reason != existing.error_message:
                existing.reject(reason)
                self.novel_repo.update(existing)
            return 0

        try:
            existing.force_accept()
        except DomainError:
            return consecutive_errors
        existing.total_chapters = len(chapters)
        if candidate.title:
            existing.title = candidate.title
        existing.is_complete = is_completed_for_novel(chapters, locale)
        self.novel_repo.update(existing)

        crawl_result = self.crawl_novel_use_case.execute(
            existing.id, prefetched_chapters=chapters, should_stop=should_stop
        )
        if crawl_result.cancelled:
            if crawl_result.chapters_crawled > 0:
                result.discovered += 1
            result.cancelled = True
            if "Đã dừng theo yêu cầu" not in result.messages:
                result.messages.append("Đã dừng theo yêu cầu")
            emit(phase="cancelled", page=page, message="Đã dừng theo yêu cầu")
            return consecutive_errors
        if crawl_result.success or crawl_result.chapters_crawled > 0:
            result.discovered += 1
        if not crawl_result.success and crawl_result.chapters_crawled == 0:
            result.errors += 1
            result.messages.append(
                f"Lỗi crawl sau re-eval '{candidate.title}': {crawl_result.error}"
            )
            return consecutive_errors + 1
        return 0

    def _try_sync_existing_novel(
        self,
        existing: Novel,
        candidate,
        source: SourcePort,
        result: CrawlGenreResult,
        consecutive_errors: int,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> int:
        """Truyện đã có trong DB — không tính vào scan_window. Nếu mục lục site
        dài hơn last_chapter_index thì crawl bổ sung chương thiếu (TH 54→55).
        Trả consecutive_errors mới."""
        if existing.lifecycle_status == NovelLifecycle.REJECTED:
            return consecutive_errors
        if existing.lifecycle_status in (
            NovelLifecycle.CRAWLING,
            NovelLifecycle.TRANSLATING,
            NovelLifecycle.READY_FOR_VIDEO,
            NovelLifecycle.PRODUCED,
        ):
            return consecutive_errors

        chapters, list_err = try_list_chapters(source, candidate.url)
        if chapters is None:
            result.errors += 1
            result.messages.append(
                f"Lỗi refresh mục lục '{candidate.title}' (đã có): {list_err}"
            )
            return consecutive_errors + 1

        site_total = len(chapters)
        # ERROR với lỗ chương: luôn thử lại dù TOC không dài hơn last_chapter_index.
        needs_hole_retry = existing.lifecycle_status == NovelLifecycle.ERROR
        if site_total <= existing.last_chapter_index and not needs_hole_retry:
            return 0

        existing.total_chapters = site_total
        if candidate.title and candidate.title != existing.title:
            existing.title = candidate.title
        try:
            existing.start_incremental_crawl()
        except DomainError as exc:
            result.messages.append(f"Bỏ qua sync '{candidate.title}': {exc}")
            return consecutive_errors
        self.novel_repo.update(existing)

        crawl_result = self.crawl_novel_use_case.execute(
            existing.id,
            prefetched_chapters=chapters,
            incremental=True,
            should_stop=should_stop,
        )
        if crawl_result.cancelled:
            if crawl_result.chapters_crawled > 0:
                result.synced += 1
            result.cancelled = True
            if "Đã dừng theo yêu cầu" not in result.messages:
                result.messages.append("Đã dừng theo yêu cầu")
            return consecutive_errors
        if crawl_result.success and crawl_result.chapters_crawled > 0:
            result.synced += 1
        elif crawl_result.success:
            pass
        elif not crawl_result.success:
            if crawl_result.chapters_crawled > 0:
                result.synced += 1
                result.messages.append(
                    f"Sync một phần '{candidate.title}' "
                    f"(+{crawl_result.chapters_crawled} ch): {crawl_result.error}"
                )
            else:
                result.errors += 1
                result.messages.append(
                    f"Lỗi sync chương mới '{candidate.title}': {crawl_result.error}"
                )
                return consecutive_errors + 1
        return 0


class DryRunUseCase:
    """Test 1 URL, KHÔNG lưu DB — dùng khi thêm site mới hoặc site đổi cấu
    trúc (crawl-service.md mục 9.4)."""

    def __init__(self, source_resolver):
        self.source_resolver = source_resolver

    def execute(self, source_key: str, url: str, mode: str) -> DryRunResult:
        try:
            source = self.source_resolver(source_key)
        except KeyError as exc:
            return DryRunResult(ok=False, mode=mode, error=str(exc))

        try:
            if mode == "genre":
                novels = source.list_genre_novels(url, scan_window=10)
                preview = [
                    {"title": n.title, "url": n.url, "latest_chapter_title": n.latest_chapter_title}
                    for n in novels
                ]
                return DryRunResult(ok=True, mode=mode, preview=preview)
            elif mode == "chapters":
                chapters = source.list_chapters(url)
                preview = [{"index": c.index, "title": c.title, "url": c.url} for c in chapters[:10]]
                return DryRunResult(ok=True, mode=mode, preview=preview)
            elif mode == "content":
                chapters, list_err = try_list_chapters(source, url)
                if chapters:
                    sample_urls = [c.url for c in chapters[:CHAPTER_SAMPLE_LIMIT]]
                else:
                    sample_urls = [url]
                last_err = list_err
                text = ""
                ok, reason = False, last_err
                for sample_url in sample_urls:
                    try:
                        text = source.fetch_chapter_content(sample_url)
                    except ScrapeError as exc:
                        last_err = str(exc)
                        continue
                    ok, reason = validate_chapter_content(text, locale=_content_locale(source))
                    if ok:
                        break
                    last_err = reason
                return DryRunResult(
                    ok=True,
                    mode=mode,
                    content_preview=text[:300] if text else "",
                    content_length=len(text),
                    validation_passed=ok,
                    error=reason if ok else last_err,
                )
            else:
                return DryRunResult(ok=False, mode=mode, error=f"mode không hợp lệ: {mode}")
        except ScrapeError as exc:
            return DryRunResult(ok=False, mode=mode, error=str(exc))


class AddManualNovelUseCase:
    """Thêm 1 truyện bằng URL tay — người dùng đã chủ động chọn URL thì
    crawl TOÀN BỘ, KHÔNG áp filter ngắn/hoàn thành/ngôi kể (settings chỉ
    dùng cho job 'Quét ngay' theo thể loại)."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        crawl_novel_use_case: CrawlNovelUseCase,
        source_resolver,
    ):
        self.novel_repo = novel_repo
        self.crawl_novel_use_case = crawl_novel_use_case
        self.source_resolver = source_resolver

    def execute(self, source_key: str, url: str, *, start_crawl: bool = True) -> CrawlNovelResult:
        existing = self.novel_repo.get_by_source_url(source_key, url)
        if existing is not None:
            return CrawlNovelResult.failure(existing.id, "Truyện này đã có trong hệ thống")

        source = self.source_resolver(source_key)
        resolved_url, chapters, error = self._resolve_chapters(source, source_key, url)
        if error is not None:
            return error

        title = source.fetch_novel_title(resolved_url) or Path(resolved_url).name or resolved_url
        author, cover_url = _try_fetch_novel_meta(source, resolved_url)
        novel = Novel(
            id=None, title=title, source_key=source_key, source_url=resolved_url,
            is_manual=True, total_chapters=len(chapters), is_complete=True,
            lifecycle_status=NovelLifecycle.DISCOVERED,
            author=author, cover_url=cover_url,
        )
        try:
            saved = self.novel_repo.add(novel)
        except DuplicateError:
            existing_after_race = self.novel_repo.get_by_source_url(source_key, resolved_url)
            return CrawlNovelResult.failure(
                existing_after_race.id if existing_after_race else 0,
                "Truyện này đã có trong hệ thống (bị thêm trùng do 2 yêu cầu gần như đồng thời)",
            )
        if not start_crawl:
            return CrawlNovelResult(novel_id=saved.id, chapters_crawled=0, success=True)
        return self.crawl_novel_use_case.execute(saved.id, prefetched_chapters=chapters)

    def _resolve_chapters(
        self, source: SourcePort, source_key: str, url: str
    ) -> tuple[str, list[ChapterRef], CrawlNovelResult | None]:
        """Thử coi `url` là trang mục lục trước. Nếu lỗi VÀ site này hỗ trợ
        suy ra mục lục từ URL 1 chương (`derive_novel_url`), thử lại với URL
        đã suy ra — cho phép người dùng dán nhầm/cố ý dán link 1 chương.
        Site không hỗ trợ suy ra (`derive_novel_url` trả None) thì báo đúng
        lỗi gốc, không giả vờ làm được."""
        chapters, list_err = try_list_chapters(source, url)
        resolved = source.derive_novel_url(url) or url
        if chapters is not None:
            existing = self.novel_repo.get_by_source_url(source_key, resolved)
            if existing is not None:
                msg = (
                    "Truyện này đã có trong hệ thống (suy ra từ URL chương)"
                    if resolved != url
                    else "Truyện này đã có trong hệ thống"
                )
                return resolved, [], CrawlNovelResult.failure(existing.id, msg)
            return resolved, chapters, None
        return resolved, [], CrawlNovelResult.failure(0, list_err or "Không lấy được mục lục")


class ForceAcceptNovelUseCase:
    def __init__(self, novel_repo: NovelRepository, crawl_novel_use_case: CrawlNovelUseCase):
        self.novel_repo = novel_repo
        self.crawl_novel_use_case = crawl_novel_use_case

    def execute(self, novel_id: int, *, start_crawl: bool = True) -> CrawlNovelResult:
        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return CrawlNovelResult.failure(novel_id, "Không tìm thấy novel")
        try:
            novel.force_accept()
        except DomainError as exc:
            return CrawlNovelResult.failure(novel_id, str(exc))
        self.novel_repo.update(novel)
        if not start_crawl:
            return CrawlNovelResult(novel_id=novel_id, chapters_crawled=0, success=True)
        return self.crawl_novel_use_case.execute(novel_id)


class SetActiveGenreUseCase:
    """1 site chỉ có ĐÚNG 1 lựa chọn "active" tại 1 thời điểm — khớp UI 1
    select box DUY NHẤT mỗi site (mục 9.0/9.2, sửa 17/9/2026: gộp lại còn
    đúng 1 card/site theo phản hồi thật "sao vẫn chia làm 2 block" — trước
    đó có 1 phiên bản tách theo "kind" thành 2 select box độc lập, nay bỏ
    hẳn khái niệm "kind", mọi option kể cả "Hot nhất (mọi thể loại)" nằm
    CHUNG 1 danh sách). Chọn 1 option mới tự động tắt MỌI option KHÁC CÙNG
    site, FE không phải tự điều phối nhiều lời gọi API."""

    def __init__(self, genre_repo: GenreRepository):
        self.genre_repo = genre_repo

    def execute(self, genre_id: int) -> Genre | None:
        genre = self.genre_repo.get_by_id(genre_id)
        if genre is None:
            return None
        for sibling in self.genre_repo.list_by_source_key(genre.source_key):
            if sibling.id != genre_id and sibling.enabled:
                sibling.enabled = False
                self.genre_repo.update(sibling)
        if not genre.enabled:
            genre.enabled = True
            self.genre_repo.update(genre)
        return genre


class GetChapterContentUseCase:
    """Đọc nội dung chương — ưu tiên bản đã làm mượt (cleaned), không thì raw."""

    def __init__(self, chapter_repo: ChapterRepository, storage: RawTextStorage):
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, chapter_id: int) -> ChapterContentResult:
        chapter = self.chapter_repo.get_by_id(chapter_id)
        if chapter is None:
            return ChapterContentResult.failure(chapter_id, "Không tìm thấy chương")
        if not chapter.raw_path:
            return ChapterContentResult.failure(chapter_id, "Chương này chưa có nội dung (chưa crawl xong)")
        try:
            raw = self.storage.read(chapter.raw_path)
        except OSError as exc:
            return ChapterContentResult.failure(chapter_id, f"Không đọc được file: {exc}")
        cleaned: str | None = None
        if self.storage.has_cleaned(chapter.raw_path):
            try:
                cleaned = self.storage.read(self.storage.cleaned_path_for(chapter.raw_path))
            except OSError as exc:
                return ChapterContentResult.failure(chapter_id, f"Không đọc được bản cleaned: {exc}")
        content = cleaned if cleaned is not None else raw
        source = "cleaned" if cleaned is not None else "raw"
        return ChapterContentResult(
            chapter_id=chapter_id,
            success=True,
            content=content,
            reviewed=chapter.reviewed,
            has_cleaned=cleaned is not None,
            content_source=source,
            raw_content=raw,
            cleaned_content=cleaned,
        )


class UpdateChapterContentUseCase:
    """Lưu nội dung đã sửa — ghi cleaned nếu đã làm mượt, không thì raw."""

    def __init__(self, chapter_repo: ChapterRepository, storage: RawTextStorage):
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, chapter_id: int, content: str) -> ChapterContentResult:
        chapter = self.chapter_repo.get_by_id(chapter_id)
        if chapter is None:
            return ChapterContentResult.failure(chapter_id, "Không tìm thấy chương")
        if not chapter.raw_path:
            return ChapterContentResult.failure(chapter_id, "Chương này chưa có nội dung (chưa crawl xong)")
        if not content.strip():
            return ChapterContentResult.failure(chapter_id, "Nội dung không được để trống")

        try:
            self.storage.overwrite_preferred(chapter.raw_path, content)
        except OSError as exc:
            return ChapterContentResult.failure(chapter_id, f"Không ghi được file: {exc}")

        has_cleaned = self.storage.has_cleaned(chapter.raw_path)
        chapter.mark_reviewed()
        self.chapter_repo.update(chapter)
        return ChapterContentResult(
            chapter_id=chapter_id,
            success=True,
            content=content,
            reviewed=True,
            has_cleaned=has_cleaned,
            content_source="cleaned" if has_cleaned else "raw",
            raw_content=None,
            cleaned_content=content if has_cleaned else None,
        )


class DiscardChapterCleanedUseCase:
    """Xóa bản cleaned — modal/review trở về chỉ raw (như trước khi làm mượt)."""

    def __init__(self, chapter_repo: ChapterRepository, storage: RawTextStorage):
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, chapter_id: int) -> ChapterContentResult:
        chapter = self.chapter_repo.get_by_id(chapter_id)
        if chapter is None:
            return ChapterContentResult.failure(chapter_id, "Không tìm thấy chương")
        if not chapter.raw_path:
            return ChapterContentResult.failure(chapter_id, "Chương này chưa có nội dung (chưa crawl xong)")
        try:
            self.storage.discard_cleaned(chapter.raw_path)
            raw = self.storage.read(chapter.raw_path)
        except OSError as exc:
            return ChapterContentResult.failure(chapter_id, f"Không khôi phục được raw: {exc}")
        return ChapterContentResult(
            chapter_id=chapter_id,
            success=True,
            content=raw,
            reviewed=chapter.reviewed,
            has_cleaned=False,
            content_source="raw",
            raw_content=raw,
            cleaned_content=None,
        )


class RetryChapterUseCase:
    """Crawl lại ĐÚNG 1 chương lỗi (`failed`/`unsupported`) — KHÔNG đụng
    chương khác, không crawl lại cả truyện (khác "Thử lại" mục 9.2b vốn
    chạy lại nguyên `CrawlNovelUseCase` cho cả truyện). Theo yêu cầu thật
    17/9/2026: "mỗi chap lỗi sẽ có nút crawl lại" — bổ sung nốt phần còn
    thiếu trong luồng "bỏ qua chương lỗi, crawl tiếp" (mục 9.6 `_skip_
    chapter_and_maybe_stop`), vốn trước đây chỉ có đường "Thử lại" cả
    truyện để bù chương thiếu."""

    def __init__(
        self,
        chapter_repo: ChapterRepository,
        novel_repo: NovelRepository,
        storage: RawTextStorage,
        source_resolver,
    ):
        self.chapter_repo = chapter_repo
        self.novel_repo = novel_repo
        self.storage = storage
        self.source_resolver = source_resolver

    def execute(self, chapter_id: int) -> ChapterRetryResult:
        chapter = self.chapter_repo.get_by_id(chapter_id)
        if chapter is None:
            return ChapterRetryResult.failure(chapter_id, "Không tìm thấy chương")
        novel = self.novel_repo.get_by_id(chapter.novel_id)
        if novel is None:
            return ChapterRetryResult.failure(chapter_id, "Không tìm thấy truyện của chương này")
        try:
            source: SourcePort = self.source_resolver(novel.source_key)
        except KeyError as exc:
            # Không đụng DB — trạng thái chương không đổi, trả lại ĐÚNG
            # status hiện có (không mặc định "failed" nếu chương đang
            # "unsupported"...).
            return ChapterRetryResult.failure(
                chapter_id, f"Nguồn không còn hỗ trợ: {exc}", status=chapter.status.value,
            )

        try:
            text = source.fetch_chapter_content(chapter.source_url)
        except ScrapeError as exc:
            chapter.mark_failed(str(exc))
            self.chapter_repo.update(chapter)
            return ChapterRetryResult.failure(chapter_id, str(exc), status=chapter.status.value)

        ok, reason = validate_chapter_content(text, locale=_content_locale(source))
        if not ok:
            assert reason is not None
            chapter.mark_failed(reason)
            self.chapter_repo.update(chapter)
            return ChapterRetryResult.failure(chapter_id, reason, status=chapter.status.value)

        raw_path = self.storage.save(novel.id, chapter.chapter_index, text)
        chapter.mark_crawled(raw_path)
        self.chapter_repo.update(chapter)

        novel_completed = self._maybe_complete_novel(novel)
        return ChapterRetryResult(
            chapter_id=chapter_id, success=True, status=chapter.status.value, novel_completed=novel_completed,
        )

    def _maybe_complete_novel(self, novel: Novel) -> bool:
        """Chương vừa retry có thể là chương THIẾU CUỐI CÙNG mà "Quét ngay"/
        "Thử lại" từng bỏ qua (mục 9.2b — novel vẫn `fully_crawled`/`error`
        kèm ghi chú "Thiếu N chương"). Nếu giờ đã đủ ĐÚNG `total_chapters`
        chương, xoá ghi chú + đảm bảo `fully_crawled` — không tự dừng ở
        `error` mãi chỉ vì 1 chương lẻ tẻ trước đây."""
        if novel.total_chapters is None:
            return False
        saved = {c.chapter_index for c in self.chapter_repo.list_by_novel(novel.id)}
        if len(saved) < novel.total_chapters:
            return False
        if novel.lifecycle_status not in (NovelLifecycle.FULLY_CRAWLED, NovelLifecycle.ERROR):
            return False
        novel.mark_fully_crawled()
        novel.error_message = None
        self.novel_repo.update(novel)
        return True


class SmoothNovelUseCase:
    """Làm mượt rule mọi chương đã crawl của 1 truyện — ghi data/cleaned/,
    không đè raw. Kỹ thuật từ novel-processor (MIT)."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
        get_opencc_mode=None,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage
        self.get_opencc_mode = get_opencc_mode or (lambda _source_key: "none")

    def execute(self, novel_id: int, chapter_ids: list[int] | None = None) -> SmoothNovelResult:
        from crawl.domain.rule_smooth import smooth_chapter_text

        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return SmoothNovelResult(novel_id=novel_id, success=False, error="Không tìm thấy novel")
        if novel.lifecycle_status not in (
            NovelLifecycle.FULLY_CRAWLED,
            NovelLifecycle.ERROR,
            NovelLifecycle.TRANSLATING,
            NovelLifecycle.READY_FOR_VIDEO,
        ):
            return SmoothNovelResult(
                novel_id=novel_id,
                success=False,
                error=f"Chỉ làm mượt được truyện đã crawl (hiện: {novel.lifecycle_status.value})",
            )

        chapters = self.chapter_repo.list_by_novel(novel_id)
        if chapter_ids:
            want = set(chapter_ids)
            chapters = [c for c in chapters if c.id in want]
            if not chapters:
                return SmoothNovelResult(
                    novel_id=novel_id,
                    success=False,
                    error="Không có chương nào khớp danh sách đã chọn",
                )

        locale = "zh"
        try:
            from crawl.infrastructure.sources.registry import SOURCES

            source = SOURCES.get(novel.source_key)
            cfg = getattr(source, "cfg", None) if source is not None else None
            locale = getattr(cfg, "content_locale", "zh") if cfg else "zh"
        except Exception:
            locale = "zh"

        opencc_mode = self.get_opencc_mode(novel.source_key)

        smoothed = 0
        skipped = 0
        removed_total = 0
        done_ids: list[int] = []
        dirty = False
        try:
            for ch in chapters:
                if not ch.raw_path or ch.status != ChapterStatus.CRAWLED:
                    skipped += 1
                    continue
                try:
                    raw = self.storage.read(ch.raw_path)
                except OSError:
                    skipped += 1
                    continue
                result = smooth_chapter_text(raw, locale=locale)
                text = apply_opencc(result.text, opencc_mode)
                self.storage.save_cleaned(ch.raw_path, text)
                if ch.reviewed:
                    ch.reviewed = False
                    self.chapter_repo.update(ch, commit=False)
                    dirty = True
                assert ch.id is not None
                done_ids.append(ch.id)
                smoothed += 1
                removed_total += result.removed_lines
            if dirty:
                self.chapter_repo.commit()
        except Exception as exc:
            db = getattr(self.chapter_repo, "db", None)
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            if "database is locked" in str(exc):
                return SmoothNovelResult(
                    novel_id=novel_id,
                    success=False,
                    error="DB đang bận (có crawl đang chạy). Thử lại sau vài giây.",
                )
            raise

        return SmoothNovelResult(
            novel_id=novel_id,
            success=True,
            chapters_smoothed=smoothed,
            chapters_skipped=skipped,
            removed_lines=removed_total,
            chapter_ids=done_ids,
        )


class DeleteNovelUseCase:
    """Xóa truyện + mọi chương + file raw/cleaned trên đĩa."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, novel_id: int) -> DeleteResult:
        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return DeleteResult(success=False, error="Không tìm thấy novel")
        if novel.lifecycle_status == NovelLifecycle.CRAWLING:
            return DeleteResult(success=False, error="Đang crawl — không xóa được. Đợi xong rồi thử lại.")

        chapters = self.chapter_repo.list_by_novel(novel_id)
        for ch in chapters:
            self.storage.delete_chapter_files(ch.raw_path)
        self.storage.delete_novel_dirs(novel_id)

        if not self.novel_repo.delete(novel_id):
            return DeleteResult(success=False, error="Không xóa được novel")
        return DeleteResult(success=True)


class DeleteChapterUseCase:
    """Xóa 1 chương + file raw/cleaned; cập nhật last_chapter_index."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, chapter_id: int) -> DeleteResult:
        chapter = self.chapter_repo.get_by_id(chapter_id)
        if chapter is None:
            return DeleteResult(success=False, error="Không tìm thấy chương")
        novel = self.novel_repo.get_by_id(chapter.novel_id)
        if novel is None:
            return DeleteResult(success=False, error="Không tìm thấy novel")
        if novel.lifecycle_status == NovelLifecycle.CRAWLING:
            return DeleteResult(success=False, error="Đang crawl — không xóa được. Đợi xong rồi thử lại.")

        self.storage.delete_chapter_files(chapter.raw_path)
        if not self.chapter_repo.delete(chapter_id):
            return DeleteResult(success=False, error="Không xóa được chương")

        remaining = self.chapter_repo.list_by_novel(chapter.novel_id)
        crawled_idx = [
            c.chapter_index for c in remaining if c.status == ChapterStatus.CRAWLED
        ]
        novel.last_chapter_index = max(crawled_idx) if crawled_idx else 0
        self.novel_repo.update(novel)
        return DeleteResult(success=True)


class NovelExportUseCase:
    """Xuất Excel / TXT / EPUB / bundle zip — ưu tiên cleaned."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage

    def status(self, novel_id: int) -> NovelExportStatus | None:
        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return None
        crawled = 0
        cleaned = 0
        reviewed = 0
        for ch in self.chapter_repo.list_by_novel(novel_id):
            if ch.status != ChapterStatus.CRAWLED or not ch.raw_path:
                continue
            crawled += 1
            if self.storage.has_cleaned(ch.raw_path):
                cleaned += 1
            if ch.reviewed:
                reviewed += 1
        can = crawled > 0
        return NovelExportStatus(
            crawled=crawled,
            cleaned=cleaned,
            reviewed=reviewed,
            can_export_workbook=can,
            can_export_txt=can,
            can_export_epub=can,
            can_export_bundle=can,
        )

    def _rows(self, novel_id: int) -> list:
        from crawl.application.excel_export import ChapterExportRow

        pairs: list[tuple[int, ChapterExportRow]] = []
        for ch in self.chapter_repo.list_by_novel(novel_id):
            if ch.status != ChapterStatus.CRAWLED or not ch.raw_path:
                continue
            try:
                content, _src = self.storage.read_preferred(ch.raw_path)
            except OSError:
                content = ""
            pairs.append((ch.chapter_index, ChapterExportRow(title=ch.title, content=content)))
        pairs.sort(key=lambda p: p[0])
        return [row for _, row in pairs]

    def _meta(self, novel: Novel):
        from crawl.application.book_export import NovelExportMeta

        return NovelExportMeta(
            title=novel.title,
            author=novel.author or "",
            source_key=novel.source_key,
            source_url=novel.source_url,
        )

    def export_workbook(self, novel_id: int) -> tuple[bytes | None, str | None, str | None]:
        """Trả (bytes, filename, error)."""
        from crawl.application.excel_export import build_novel_workbook, sanitize_filename

        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return None, None, "Không tìm thấy novel"
        rows = self._rows(novel_id)
        if not rows:
            return None, None, "Chưa có chương crawled để xuất"
        data = build_novel_workbook(rows)
        name = f"{sanitize_filename(novel.title)}.xlsx"
        return data, name, None

    def export_txt(self, novel_id: int) -> tuple[bytes | None, str | None, str | None]:
        from crawl.application.book_export import build_novel_txt
        from crawl.application.excel_export import sanitize_filename

        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return None, None, "Không tìm thấy novel"
        rows = self._rows(novel_id)
        if not rows:
            return None, None, "Chưa có chương crawled để xuất"
        data = build_novel_txt(self._meta(novel), rows)
        return data, f"{sanitize_filename(novel.title)}.txt", None

    def export_epub(self, novel_id: int) -> tuple[bytes | None, str | None, str | None]:
        from crawl.application.book_export import build_novel_epub
        from crawl.application.excel_export import sanitize_filename

        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return None, None, "Không tìm thấy novel"
        rows = self._rows(novel_id)
        if not rows:
            return None, None, "Chưa có chương crawled để xuất"
        data = build_novel_epub(self._meta(novel), rows)
        return data, f"{sanitize_filename(novel.title)}.epub", None

    def export_bundle(self, novel_id: int) -> tuple[bytes | None, str | None, str | None]:
        from crawl.application.book_export import build_novel_bundle_zip
        from crawl.application.excel_export import sanitize_filename

        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return None, None, "Không tìm thấy novel"
        rows = self._rows(novel_id)
        if not rows:
            return None, None, "Chưa có chương crawled để xuất"
        data = build_novel_bundle_zip(self._meta(novel), rows)
        return data, f"{sanitize_filename(novel.title)}.zip", None

    def export_batch(
        self, novel_ids: list[int], fmt: str = "bundle"
    ) -> tuple[bytes | None, str | None, str | None]:
        """Zip nhiều truyện — mỗi entry theo format (xlsx|txt|epub|bundle)."""
        import io
        import zipfile

        from crawl.application.excel_export import sanitize_filename

        if not novel_ids:
            return None, None, "Chưa chọn truyện nào"
        fmt = (fmt or "bundle").strip().lower()
        exporters = {
            "xlsx": self.export_workbook,
            "txt": self.export_txt,
            "epub": self.export_epub,
            "bundle": self.export_bundle,
        }
        export_one = exporters.get(fmt)
        if export_one is None:
            return None, None, f"Format không hỗ trợ: {fmt}"

        buf = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for nid in novel_ids:
                data, filename, error = export_one(nid)
                if error or data is None or not filename:
                    continue
                novel = self.novel_repo.get_by_id(nid)
                folder = sanitize_filename(novel.title if novel else f"novel-{nid}")
                # bundle đã là zip — đặt trong thư mục con với tên file gốc
                zf.writestr(f"{folder}/{filename}", data)
                written += 1
        if written == 0:
            return None, None, "Không có truyện nào xuất được (chưa crawl?)"
        return buf.getvalue(), f"export-{written}-novels.zip", None


class ReviewAllChaptersUseCase:
    """Đánh dấu đã review mọi chương đã crawl + đã có cleaned — không mở từng dialog."""

    def __init__(
        self,
        novel_repo: NovelRepository,
        chapter_repo: ChapterRepository,
        storage: RawTextStorage,
    ):
        self.novel_repo = novel_repo
        self.chapter_repo = chapter_repo
        self.storage = storage

    def execute(self, novel_id: int) -> ReviewAllResult:
        novel = self.novel_repo.get_by_id(novel_id)
        if novel is None:
            return ReviewAllResult(success=False, error="Không tìm thấy novel")
        if novel.lifecycle_status == NovelLifecycle.CRAWLING:
            return ReviewAllResult(success=False, error="Đang crawl — không review all được")

        reviewed_n = 0
        skipped = 0
        dirty = False
        for ch in self.chapter_repo.list_by_novel(novel_id):
            if ch.status != ChapterStatus.CRAWLED or not ch.raw_path:
                skipped += 1
                continue
            if not self.storage.has_cleaned(ch.raw_path):
                skipped += 1
                continue
            if ch.reviewed:
                skipped += 1
                continue
            ch.mark_reviewed()
            self.chapter_repo.update(ch, commit=False)
            dirty = True
            reviewed_n += 1
        if dirty:
            self.chapter_repo.commit()
        if reviewed_n == 0 and skipped > 0:
            # Có thể chưa smooth gì — vẫn success với 0
            return ReviewAllResult(success=True, chapters_reviewed=0, chapters_skipped=skipped)
        return ReviewAllResult(success=True, chapters_reviewed=reviewed_n, chapters_skipped=skipped)
