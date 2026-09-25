"""Domain logic thuần — không đụng DB/HTTP, test được không cần mock nặng.
Đây là nơi áp dụng trực tiếp các bài học rút từ lncrawl/novel-downloader
(crawl-service.md mục 2)."""
import re
from typing import Sequence
from urllib.parse import urlparse

from crawl.domain.value_objects import ChapterRef, NovelRef

# Từ khoá cho biết trang là challenge/chặn bot, không phải nội dung thật
# ("silent success" — trang trả HTTP 200 nhưng là rác, mục 2 bài học #1).
# KHÔNG dùng marker quá ngắn kiểu "验证" đơn lẻ — dễ false-positive trong
# nội dung truyện (验证身份/验证了…). Chỉ cụm rõ là trang challenge.
_BLOCK_MARKERS = [
    "请稍后",
    "访问频繁",
    "验证码",
    "人机验证",
    "安全验证",
    "滑动验证",
    "访问验证",
    "请完成验证",
    "请进行验证",
    "captcha",
    "cloudflare",
    "just a moment",
    "attention required",
]

# Từ khoá nhận biết truyện đã hoàn thành, dùng để lọc "ngắn+hoàn thành".
COMPLETION_MARKERS = ["完本", "大结局", "尾声", "完结"]

# Đại từ nhân xưng dùng để đoán truyện kể theo ngôi thứ mấy — phong cách
# "xưng tôi" (ngôi thứ nhất) hợp giọng đọc audio kể chuyện hơn ngôi thứ ba
# thông thường. Đây là heuristic tần suất đơn giản, KHÔNG chính xác 100%
# (không phải mô hình NLP), chỉ đủ lọc sơ bộ trên chương mẫu.
_FIRST_PERSON_BY_LOCALE: dict[str, tuple[str, ...]] = {
    "zh": ("我",),
    "ja": ("私", "僕", "俺", "わたし", "あたし"),
    "ko": ("나", "저", "내가", "저는", "나는"),
    "vi": ("tôi", "mình", "tao", "tớ", "em"),
}
_THIRD_PERSON_BY_LOCALE: dict[str, tuple[str, ...]] = {
    # CHỈ "他"/"她" — KHÔNG thêm "他们"/"她们" riêng (đã chứa tiền tố).
    "zh": ("他", "她"),
    "ja": ("彼", "彼女"),
    "ko": ("그", "그녀"),
    "vi": ("anh ấy", "cô ấy", "họ", "ông ấy", "bà ấy"),
}
_FIRST_PERSON_MARKER = "我"  # tương thích test/call cũ
_THIRD_PERSON_MARKERS = ["他", "她"]
FIRST_PERSON_RATIO_THRESHOLD = 0.6

_CHINESE_CHAR_RE = re.compile(r"[一-鿿]")
_JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")
_KOREAN_CHAR_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_VIETNAMESE_CHAR_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    r"ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]"
)

MIN_CONTENT_CHARS = 50
MIN_CHINESE_RATIO = 0.3
MIN_SCRIPT_RATIO = 0.25

COMPLETION_MARKERS_BY_LOCALE: dict[str, tuple[str, ...]] = {
    "zh": COMPLETION_MARKERS,
    # Không dùng marker đơn "完" — dính false-positive (完全/完璧…). 短編
    # 1 chương được coi hoàn thành qua total_chapters==1 ở is_completed().
    "ja": ("完結", "完結済", "連載終了", "終了"),
    "ko": ("완결", "완료", "完結"),
    "vi": ("Hoàn thành", "hoàn thành", "Full", "FULL", "Hết", "End"),
}

# Crawl linh hoạt — dùng chung mọi site (use_cases.py).
MAX_CONSECUTIVE_CHAPTER_FAILURES = 3
CHAPTER_SAMPLE_LIMIT = 5
# Commit mỗi N chương — giảm fsync SQLite, vẫn đủ dày để resume.
CHAPTER_COMMIT_BATCH = 10
# Mỗi lượt quét: tối đa N lần refresh mục lục cho truyện ĐÃ CÓ (site đẩy
# truyện mới update lên đầu list). Tránh list_chapters hàng loạt khi library lớn.
MAX_EXISTING_SYNCS_PER_SCAN = 5

# Lỗi chỉ ảnh hưởng 1 chương (VIP, thiếu quyền…) — bỏ qua, không tính vào
# "N chương liên tiếp = site chết".
_PER_CHAPTER_FAILURE_MARKERS = (
    "vip",
    "khoá",
    "khoa",
    "cần cookie",
    "cookie đăng nhập",
    "cần đăng nhập",
    "đăng nhập",
    "chưa mua",
    "验证码",
    "captcha",
    "付费",
    "未订阅",
    "订阅",
    "ảnh vip",
    "quyền vip",
    "chương khoá",
    "marker=",  # assert_not_vip_locked
    "ocr",
    "decrypt",
    "giải mã",
    "ywguid",
    "anti-bot qidian",
)


_LIST_AD_MARKERS = ("广告", "推广", "点击查看", "赞助", "quảng cáo", "广告位")


def _same_site_host(host_a: str, host_b: str) -> bool:
    """Cùng site kể cả subdomain anh em (yomou.syosetu.com ↔ ncode.syosetu.com)."""
    a = host_a.lower().removeprefix("www.")
    b = host_b.lower().removeprefix("www.")
    if a == b:
        return True
    parts_a, parts_b = a.split("."), b.split(".")
    # So sánh 2 nhãn cuối (syosetu.com) — đủ cho novel host; không xử lý co.uk.
    return len(parts_a) >= 2 and len(parts_b) >= 2 and parts_a[-2:] == parts_b[-2:]


def is_genre_list_noise(ref: NovelRef, *, base_url: str = "") -> bool:
    """Mục quảng cáo / link rác trên trang danh sách thể loại — bỏ qua khi quét."""
    title = (ref.title or "").strip()
    url = (ref.url or "").strip()
    if not title or not url:
        return True
    if url.startswith(("javascript:", "mailto:", "#")):
        return True
    title_lower = title.lower()
    if any(marker in title_lower for marker in _LIST_AD_MARKERS):
        return True
    if base_url:
        ref_host = urlparse(url).netloc
        base_host = urlparse(base_url).netloc
        if ref_host and base_host and not _same_site_host(ref_host, base_host):
            return True
    return False


def chapter_failure_counts_toward_block(reason: str) -> bool:
    """False = lỗi lẻ 1 chương (VIP, OCR ảnh…) — skip và thử chương sau."""
    lowered = reason.lower()
    return not any(marker in lowered for marker in _PER_CHAPTER_FAILURE_MARKERS)


def _script_ratio(text: str, locale: str) -> float:
    if locale == "ja":
        return len(_JAPANESE_CHAR_RE.findall(text)) / len(text)
    if locale == "ko":
        return len(_KOREAN_CHAR_RE.findall(text)) / len(text)
    if locale == "vi":
        latin = sum(1 for c in text if c.isalpha())
        if latin == 0:
            return 0.0
        return len(_VIETNAMESE_CHAR_RE.findall(text)) / latin
    return len(_CHINESE_CHAR_RE.findall(text)) / len(text)


def validate_chapter_content(text: str, *, locale: str = "zh") -> tuple[bool, str | None]:
    """Trả (hợp lệ?, lý do nếu không hợp lệ). Chống lưu rác khi site chặn
    bot nhưng vẫn trả HTTP 200 (bài học #1, mục 2 crawl-service.md)."""
    if not text or len(text) < MIN_CONTENT_CHARS:
        return False, f"Nội dung quá ngắn (<{MIN_CONTENT_CHARS} ký tự) — có thể trang chặn bot"

    lowered = text.lower()
    for marker in _BLOCK_MARKERS:
        if marker.lower() in lowered:
            return False, f"Nội dung chứa cụm nghi ngờ trang chặn bot: '{marker}'"

    ratio = _script_ratio(text, locale)
    min_ratio = MIN_CHINESE_RATIO if locale == "zh" else MIN_SCRIPT_RATIO
    if ratio < min_ratio:
        label = {"zh": "Hán", "ja": "Nhật", "ko": "Hàn", "vi": "Việt"}.get(locale, locale)
        return False, f"Tỉ lệ ký tự {label} quá thấp ({ratio:.0%}) — nội dung có thể không đúng"

    return True, None


def is_completed(
    latest_chapter_title: str,
    *,
    locale: str = "zh",
    total_chapters: int | None = None,
) -> bool:
    # 短編 / one-shot: chỉ JA/KO thường 1 chương không gắn 完結 — coi đã xong.
    # Không áp dụng cho zh (1 chương có thể là TOC lỗi / stub dài).
    if total_chapters == 1 and locale in ("ja", "ko"):
        return True
    markers = COMPLETION_MARKERS_BY_LOCALE.get(locale, COMPLETION_MARKERS)
    title = latest_chapter_title or ""
    return any(marker in title for marker in markers)


def is_short_enough(total_chapters: int, max_chapters_per_story: int) -> bool:
    return total_chapters <= max_chapters_per_story


def first_person_ratio(text: str, *, locale: str = "zh") -> float:
    """Tỉ lệ đại từ ngôi 1 trên tổng ngôi 1+3. Trả 0.0 nếu không có đại từ
    nào (không đủ dữ liệu — caller phải xử lý riêng, không suy ra ngôi 3)."""
    ratio, _total = first_person_stats(text, locale=locale)
    return ratio


def first_person_stats(text: str, *, locale: str = "zh") -> tuple[float, int]:
    first_markers = _FIRST_PERSON_BY_LOCALE.get(locale) or _FIRST_PERSON_BY_LOCALE["zh"]
    third_markers = _THIRD_PERSON_BY_LOCALE.get(locale) or _THIRD_PERSON_BY_LOCALE["zh"]
    # VI/EN markers so khớp không phân biệt hoa thường.
    haystack = text.lower() if locale == "vi" else text
    if locale == "vi":
        first = sum(haystack.count(m.lower()) for m in first_markers)
        third = sum(haystack.count(m.lower()) for m in third_markers)
    else:
        first = sum(text.count(m) for m in first_markers)
        third = sum(text.count(m) for m in third_markers)
    total = first + third
    if total == 0:
        return 0.0, 0
    return first / total, total


def is_first_person_narrated(
    text: str, threshold: float = FIRST_PERSON_RATIO_THRESHOLD, *, locale: str = "zh"
) -> bool:
    """Đoán truyện kể theo ngôi thứ nhất dựa trên chương mẫu (thường là
    chương 1) — dùng khi lọc thêm phong cách "xưng tôi" bên cạnh tiêu chí
    ngắn+hoàn thành (crawl-service.md, tính năng lọc phong cách trần thuật)."""
    ratio, total = first_person_stats(text, locale=locale)
    if total == 0:
        return False
    return ratio >= threshold


# "Option" chọn ngôi kể — tổng quát hoá thay vì 1 cờ bật/tắt cứng riêng cho
# ngôi thứ nhất, để sau này chọn được cả ngôi thứ ba hoặc tắt hẳn lọc.
NARRATION_FILTERS = ("any", "first_person", "third_person")
NarrationFilter = str  # giá trị hợp lệ: 1 trong NARRATION_FILTERS


def matches_narration_filter(
    text: str, narration_filter: NarrationFilter, *, locale: str = "zh"
) -> bool:
    """Giá trị lạ (không nằm trong NARRATION_FILTERS) coi như "any" —
    không lọc, an toàn hơn là chặn nhầm. Không có đại từ → không khớp
    first lẫn third (tránh JP/KO bị nhận nhầm là ngôi 3)."""
    if narration_filter == "any":
        return True
    ratio, total = first_person_stats(text, locale=locale)
    if total == 0:
        return False
    if narration_filter == "first_person":
        return ratio >= FIRST_PERSON_RATIO_THRESHOLD
    if narration_filter == "third_person":
        return ratio < FIRST_PERSON_RATIO_THRESHOLD
    return True


# "Option" lọc theo trạng thái hoàn thành — trước 17/9/2026 đây là điều
# kiện CỨNG luôn bật (mọi truyện chưa hoàn thành đều bị loại, không tắt
# được), giờ tổng quát hoá thành setting chỉnh được (giống NARRATION_FILTERS)
# theo yêu cầu "để động hết, không cần auto lọc cứng trong code".
COMPLETION_FILTERS = ("completed_only", "ongoing_only", "any")
CompletionFilter = str  # giá trị hợp lệ: 1 trong COMPLETION_FILTERS


def matches_completion_filter(
    latest_chapter_title: str,
    completion_filter: CompletionFilter,
    *,
    locale: str = "zh",
    total_chapters: int | None = None,
) -> bool:
    """Giá trị lạ (không nằm trong COMPLETION_FILTERS) coi như "any" —
    không lọc, an toàn hơn là chặn nhầm."""
    completed = is_completed(
        latest_chapter_title, locale=locale, total_chapters=total_chapters
    )
    if completion_filter == "completed_only":
        return completed
    if completion_filter == "ongoing_only":
        return not completed
    return True


def evaluate_candidate(
    chapters: Sequence[ChapterRef],
    max_chapters_per_story: int,
    completion_filter: CompletionFilter = "completed_only",
    *,
    locale: str = "zh",
) -> tuple[bool, str]:
    """Tiêu chí 'ngắn + [lọc hoàn thành tuỳ chọn]' (crawl-service.md mục 7),
    đánh giá trên chính danh sách chương đã fetch được. Trả (được nhận?, lý
    do — dùng để lưu vào Novel.error_message khi reject).

    QUAN TRỌNG: nhận `chapters` (danh sách chương THẬT đã fetch), KHÔNG
    nhận text tóm tắt trên trang danh sách thể loại — vì không phải site
    nào cũng có tóm tắt đó (vd trang search của bqgxs.com), và tóm tắt
    trên listing có thể không đáng tin (bài học 'đừng tin dữ liệu tóm tắt'
    — mục 2 crawl-service.md). Nhận nguyên `chapters` thay vì bắt caller tự
    tách `len()`/`[-1].title` cũng tránh 2 call site (CrawlGenreUseCase,
    AddManualNovelUseCase) lặp lại đúng 2 dòng suy ra đó."""
    total_chapters = len(chapters)
    if total_chapters == 0:
        return False, "Mục lục rỗng — không có chương để crawl"
    latest_title = chapters[-1].title if chapters else ""
    if not matches_completion_filter(
        latest_title,
        completion_filter,
        locale=locale,
        total_chapters=total_chapters,
    ):
        label = {"completed_only": "đã hoàn thành", "ongoing_only": "đang ra (chưa hoàn thành)"}.get(
            completion_filter, completion_filter
        )
        return False, f"Truyện không khớp bộ lọc trạng thái đang chọn (chỉ nhận truyện {label})"
    if not is_short_enough(total_chapters, max_chapters_per_story):
        return False, f"Truyện dài hơn ngưỡng ({total_chapters} > {max_chapters_per_story} chương)"
    return True, ""
