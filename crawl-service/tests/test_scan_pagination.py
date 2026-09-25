"""Verify `crawl.scan_window` là số truyện MUỐN CHẤP NHẬN, không phải "số
truyện đầu danh sách xét rồi dừng" — bug thật đã gặp: chọn thể loại/bảng xếp
hạng có tỉ lệ loại cao (vd đa số truyện dài) khiến 1 trang không đủ truyện
đạt tiêu chí, phải dò sang trang sau (SourcePort.list_genre_novels_page) tới
khi đủ, hết danh sách, hoặc chạm `max_pages_per_scan` (mục 7c)."""
from pathlib import Path

from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)

_SAMPLE_TEXT = "他走在路上，看见前方有一道光，心里很害怕，不知道该怎么办。" * 5


class _MultiPageFakeSource:
    """Source giả nhiều trang — `pages` map page number -> danh sách
    NovelRef; truyện có url kết thúc bằng "#long" bị coi là dài (không đạt
    tiêu chí ngắn), còn lại là ngắn+hoàn thành. Ghi lại `requested_pages` để
    test xác nhận có dừng SỚM (không dò thừa trang) hay không."""

    key = "fake_pagination_test"
    name = "fake source for pagination test"

    def __init__(self, pages: dict[int, list[NovelRef]], fail_all_chapters: bool = False):
        self.pages = pages
        self.requested_pages: list[int] = []
        self.fail_all_chapters = fail_all_chapters
        self.list_chapters_calls = 0

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        self.requested_pages.append(page)
        return self.pages.get(page, [])

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        self.list_chapters_calls += 1
        if self.fail_all_chapters:
            # Mô phỏng site đang lỗi (HTTP 520 kéo dài) — MỌI
            # candidate đều lỗi hạ tầng, không phải "rejected" bình thường.
            raise ScrapeError(f"[fake] lỗi giả lập tại {novel_url}")
        if novel_url.endswith("#long"):
            total = 60  # > max_chapters_per_story mặc định trong test (50) -> bị loại
            return [
                ChapterRef(
                    index=i, title=f"第{i}章" + (" 大结局" if i == total else ""), url=f"{novel_url}/{i}"
                )
                for i in range(1, total + 1)
            ]
        return [
            ChapterRef(index=i, title=f"第{i}章" + (" 大结局" if i == 3 else ""), url=f"{novel_url}/{i}")
            for i in range(1, 4)
        ]

    def fetch_chapter_content(self, chapter_url: str) -> str:
        return _SAMPLE_TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _build_use_case(
    db, source, scan_window: int, max_pages_per_scan: int, max_consecutive_errors: int = 5
) -> CrawlGenreUseCase:
    novel_repo = SqlAlchemyNovelRepository(db)
    chapter_repo = SqlAlchemyChapterRepository(db)
    crawl_novel_use_case = CrawlNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(Path("/tmp/scan_pagination_test_raw")),
        source_resolver=lambda _key: source,
    )
    return CrawlGenreUseCase(
        novel_repo=novel_repo,
        genre_repo=SqlAlchemyGenreRepository(db),
        crawl_novel_use_case=crawl_novel_use_case,
        source_resolver=lambda _key: source,
        get_scan_window=lambda source_key: scan_window,
        get_max_chapters_per_story=lambda source_key: 50,
        get_narration_filter=lambda source_key: "any",
        get_max_pages_per_scan=lambda source_key: max_pages_per_scan,
        get_max_consecutive_errors=lambda source_key: max_consecutive_errors,
    )


def test_scan_continues_to_next_page_when_page_one_all_rejected(client):  # noqa: ARG001
    db = _db()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        genre = genre_repo.get_or_create(
            source_key="fake_pagination_test", genre_key="g1", label="G1", list_url="http://x/list-a"
        )
        source = _MultiPageFakeSource(
            pages={
                1: [NovelRef(title=f"Dài {i}", url=f"http://x/list-a/long{i}#long", latest_chapter_title="")
                    for i in range(3)],
                2: [NovelRef(title=f"Ngắn {i}", url=f"http://x/list-a/short{i}", latest_chapter_title="")
                    for i in range(3)],
                # Trang 3 không được khai trong `pages` -> nếu bị gọi tới sẽ
                # trả [] (source coi như hết truyện), KHÔNG raise — nhưng
                # requested_pages sẽ lộ ra nếu scan dò thừa quá mức cần.
            }
        )
        use_case = _build_use_case(db, source, scan_window=2, max_pages_per_scan=5)

        result = use_case.execute(genre.id)

        assert result.rejected == 3  # cả 3 truyện dài ở trang 1 đều bị loại
        assert result.discovered == 2  # đủ 2 truyện ngắn lấy được ở trang 2
        # Dừng NGAY khi đủ scan_window, không dò thêm trang 3 dù max_pages=5.
        assert source.requested_pages == [1, 2]
    finally:
        db.close()


def test_scan_stops_at_max_pages_cap_without_hanging(client):  # noqa: ARG001
    db = _db()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        genre = genre_repo.get_or_create(
            source_key="fake_pagination_test", genre_key="g2", label="G2", list_url="http://x/list-b"
        )
        # MỌI trang đều toàn truyện dài -> không bao giờ đủ scan_window=5,
        # nhưng phải dừng đúng ở max_pages_per_scan=3 thay vì dò vô tận.
        def _long_novel(p: int, i: int) -> NovelRef:
            url = f"http://x/list-b/p{p}-{i}#long"
            return NovelRef(title=f"Dài p{p}-{i}", url=url, latest_chapter_title="")

        source = _MultiPageFakeSource(pages={p: [_long_novel(p, i) for i in range(2)] for p in range(1, 10)})
        use_case = _build_use_case(db, source, scan_window=5, max_pages_per_scan=3)

        result = use_case.execute(genre.id)

        assert result.discovered == 0
        assert source.requested_pages == [1, 2, 3]  # không vượt quá cap
        assert any("chưa đủ" in m for m in result.messages)

        saved = genre_repo.get_by_id(genre.id)
        assert saved.last_run_status == "done"  # dừng vì hết cap, KHÔNG phải lỗi
    finally:
        db.close()


def test_scan_stops_when_list_exhausted_before_reaching_scan_window(client):  # noqa: ARG001
    db = _db()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        genre = genre_repo.get_or_create(
            source_key="fake_pagination_test", genre_key="g3", label="G3", list_url="http://x/list-c"
        )
        # Chỉ có 1 trang, 1 truyện ngắn -> trang 2 rỗng (hết danh sách thật
        # sự, không phải do site lỗi) -> dừng sớm, không lãng phí quét thêm.
        only = NovelRef(title="Truyện duy nhất", url="http://x/list-c/only", latest_chapter_title="")
        source = _MultiPageFakeSource(pages={1: [only]})
        use_case = _build_use_case(db, source, scan_window=5, max_pages_per_scan=10)

        result = use_case.execute(genre.id)

        assert result.discovered == 1
        assert source.requested_pages == [1, 2]  # thử trang 2, thấy rỗng thì dừng ngay
    finally:
        db.close()


def test_scan_stops_early_when_site_appears_down(client):  # noqa: ARG001
    """Bug thật (16/9/2026): khi CẢ SITE lỗi (vd `/novel/xxx.html` HTTP
    520 kéo dài), mọi candidate rơi vào lỗi hạ tầng — không phải "rejected"
    nên trước đây vòng lặp cứ ăn hết toàn bộ trang (có thể hàng chục/trăm
    candidate, mỗi cái tốn tới ~1 phút retry) mới dừng, nút "Quét ngay" cứ
    treo "Đang quét…" rất lâu. `max_consecutive_errors` phải chặn việc này
    lại SỚM, không đợi hết cả trang."""
    db = _db()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        genre = genre_repo.get_or_create(
            source_key="fake_pagination_test", genre_key="g4", label="G4", list_url="http://x/list-d"
        )
        # 1 trang "to" (20 candidate) nhưng list_chapters() lỗi 100% -> mô
        # phỏng site đang chết hoàn toàn.
        many = [
            NovelRef(title=f"X{i}", url=f"http://x/list-d/x{i}", latest_chapter_title="") for i in range(20)
        ]
        source = _MultiPageFakeSource(pages={1: many}, fail_all_chapters=True)
        use_case = _build_use_case(db, source, scan_window=5, max_pages_per_scan=3, max_consecutive_errors=3)

        result = use_case.execute(genre.id)

        assert result.discovered == 0
        # Dừng sau ĐÚNG 3 lỗi liên tiếp (max_consecutive_errors=3), KHÔNG ăn
        # hết 20 candidate của trang 1, và KHÔNG sang trang 2.
        assert source.list_chapters_calls == 3
        assert source.requested_pages == [1]
        assert any("liên tiếp" in m for m in result.messages)

        saved = genre_repo.get_by_id(genre.id)
        assert saved.last_run_status == "error"
        assert result.stopped_as_error is True
    finally:
        db.close()


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
