"""SourcePort đọc từ file cố định trên đĩa — KHÔNG dùng cho khách hàng thật,
chỉ để test toàn bộ pipeline (crawl -> validate -> lifecycle) mà không phụ
thuộc mạng/site thật hay bị chặn bot. Đăng ký trong registry.py với
source_key='demo_local'."""
from pathlib import Path

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef


class DemoLocalSource:
    key = "demo_local"
    name = "Demo (đọc từ file cục bộ, chỉ để test)"
    # KHÔNG hiện trong trang "Danh sách site" cho người dùng thật (mục 9.0)
    # — chỉ dùng nội bộ (pytest, trang Nâng cao/dry-run) để test pipeline mà
    # không cần mạng thật. Sửa 16/9/2026 theo phản hồi "UI đang sai, có
    # site demo lẫn vào không dùng được".
    is_test = True

    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = Path(fixtures_dir)
        self.novel_dir = self.fixtures_dir / "demo_novel"

    def _safe_path(self, raw: str) -> Path:
        """Chỉ cho đọc trong thư mục fixtures — URL demo là đường dẫn file,
        không giới hạn thì dry-run/thêm truyện đọc được file bất kỳ."""
        root = self.fixtures_dir.resolve()
        path = Path(raw).resolve()
        if path != root and not path.is_relative_to(root):
            raise ScrapeError(f"[{self.key}] Đường dẫn ngoài thư mục fixtures bị từ chối: {raw}")
        return path

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        return self.list_genre_novels_page(genre_list_url, page=1)[:scan_window]

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        # Nguồn demo chỉ có ĐÚNG 1 truyện giả -> chỉ "có" ở trang 1, dò thêm
        # trang sau luôn trả rỗng (giống hành vi 1 site thật đã hết truyện).
        if page != 1:
            return []
        return [
            NovelRef(
                title="[Demo] Sơn Trung Sơ Ngộ",
                url=str(self.novel_dir),
                latest_chapter_title="第二章 下山之约（完结）",
            )
        ]

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        novel_dir = self._safe_path(novel_url)
        files = sorted(novel_dir.glob("chapter_*.txt"))
        if not files:
            raise ScrapeError(f"[{self.key}] Không tìm thấy file chương nào trong {novel_dir}")
        last = len(files)
        return [
            # Chương cuối gắn từ khoá hoàn thành thật ("完结") — evaluate_candidate
            # (domain/services.py) xác nhận qua chương cuối THẬT lấy được, không
            # còn tin text tóm tắt trên listing nữa, nên dữ liệu demo phải phản
            # ánh đúng hành vi 1 site thật.
            ChapterRef(index=i, title=f"Chương {i}" + (" 完结" if i == last else ""), url=str(f))
            for i, f in enumerate(files, start=1)
        ]

    def derive_novel_url(self, chapter_url: str) -> str | None:
        """Suy ra thư mục truyện từ đường dẫn file 1 chương — luôn suy ra
        được vì nguồn demo dùng thẳng đường dẫn file làm 'url'."""
        try:
            path = self._safe_path(chapter_url)
        except ScrapeError:
            return None
        if path.is_dir():
            return str(path)
        return str(path.parent)

    def fetch_novel_title(self, novel_url: str) -> str | None:
        novel_dir = Path(novel_url)
        if novel_dir.name == "demo_novel":
            return "[Demo] Sơn Trung Sơ Ngộ"
        return f"[Demo] {novel_dir.name}"

    def fetch_chapter_content(self, chapter_url: str) -> str:
        path = self._safe_path(chapter_url)
        if not path.is_file():
            raise ScrapeError(f"[{self.key}] File không tồn tại: {path}")
        return path.read_text(encoding="utf-8")
