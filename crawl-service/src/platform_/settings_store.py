"""Bảng Settings key-value dùng chung mọi context (quy ước
docs/platform-and-licensing.md mục 3). Thêm 1 setting mới = thêm 1 dòng
trong SEED_DEFAULTS, KHÔNG migrate schema.

Lưu ý đặt tên package `platform_` (có gạch dưới) thay vì `platform` để
tránh đè lên module chuẩn `platform` của Python (stdlib) — 1 số thư viện
(vd APScheduler) tự `import platform` bên trong, nếu trùng tên gói của
mình sẽ import nhầm, lỗi rất khó debug.
"""
import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_.db import Base

# Giá trị seed lần đầu — sau đó người dùng chỉnh qua UI (PATCH /settings),
# job/luồng nghiệp vụ luôn đọc giá trị hiện tại trong DB, không đọc hằng số này.
#
# CHỈ giữ ở đây các setting THẬT SỰ toàn cục (không thuộc riêng site nào) —
# cap dịch/video áp dụng chung mọi truyện bất kể crawl từ site nào. Các
# setting quyết định CÁCH QUÉT (scan_window, ngưỡng ngắn, lọc ngôi kể...) đã
# chuyển thành setting RIÊNG TỪNG SITE (`PER_SITE_CRAWL_DEFAULTS` bên dưới) —
# sửa 16/9/2026 theo yêu cầu "setting riêng cho từng site" khi mở rộng nhiều
# site khác nhau (mỗi site có tốc độ, độ dài truyện phổ biến khác nhau).
SEED_DEFAULTS: dict[str, Any] = {
    "crawl.max_chapters_translate_per_day": 20,
    # Discord webhook URL hoặc Telegram `https://api.telegram.org/bot…/sendMessage?chat_id=…`
    # (body JSON tự detect). Rỗng = tắt báo cáo sau quét daily.
    "notify.webhook_url": "",
    # Proxy mặc định theo vùng (UI Settings) — giống lncrawl: cấu hình trong app,
    # không bắt buộc env. Env `CRAWL_PROXY_VN`… vẫn là fallback khi UI trống.
    "crawl.proxy": "",
    "crawl.proxy.vn": "",
    "crawl.proxy.jp": "",
    "crawl.proxy.kr": "",
    "crawl.proxy.tw": "",
    "crawl.proxy.cn": "",
}

# Setting RIÊNG cho từng site — lúc seed sẽ nhân bản thành 1 dòng/site theo
# key dạng "crawl.<key>.<source_key>" (xem `per_site_key()`,
# main.py `_seed_per_site_settings`). Vẫn KHÔNG cần migrate schema — chỉ là
# nhiều dòng hơn trong cùng bảng key-value.
PER_SITE_CRAWL_DEFAULTS: dict[str, Any] = {
    # Số truyện MỚI muốn CHẤP NHẬN mỗi lượt quét — không phải "số truyện đầu
    # danh sách xét rồi dừng" (CrawlGenreUseCase tự dò sang trang sau nếu
    # top đầu danh sách bị loại hết, tới khi đủ số này hoặc hết
    # max_pages_per_scan, xem mục 7d).
    "scan_window": 5,
    "max_chapters_per_story": 50,
    # Chặn dò vô tận khi tỉ lệ loại quá cao (vd chọn thể loại "hot" — đa số
    # truyện dài, gần như bị loại hết bởi max_chapters_per_story).
    "max_pages_per_scan": 3,
    # Chặn quét "cày" qua hàng chục candidate khi CẢ SITE đang lỗi (mỗi lỗi
    # tốn tới ~1 phút retry+backoff) — quá N lỗi LIÊN TIẾP thì dừng hẳn lượt
    # quét, không cố quét nốt phần còn lại (bug thật đã gặp 16/9/2026).
    "max_consecutive_errors": 5,
    # "Option" chọn ngôi kể — "any" | "first_person" | "third_person" (xem
    # crawl.domain.services.NARRATION_FILTERS). Mặc định "first_person" vì
    # hợp giọng đọc audio kể chuyện (hướng kinh doanh hiện tại), chỉnh được
    # qua UI Settings — chọn "any" để tắt hẳn lọc.
    "narration_filter": "first_person",
    # "Option" lọc theo trạng thái hoàn thành — "completed_only" |
    # "ongoing_only" | "any" (xem crawl.domain.services.COMPLETION_FILTERS).
    # Trước 17/9/2026 đây là 1 điều kiện CỨNG trong evaluate_candidate()
    # (luôn bắt buộc đã hoàn thành, không tắt được) — giờ thành setting
    # chỉnh được qua UI, giống narration_filter, theo yêu cầu "để động hết,
    # không cần auto lọc cứng trong code". Mặc định giữ nguyên hành vi cũ
    # (chỉ nhận truyện đã hoàn thành — đúng tinh thần "1-5 video/truyện").
    "completion_filter": "completed_only",
    # OpenCC: none | t2s | s2t | s2tw | tw2s — áp dụng SAU rule_smooth khi làm mượt.
    "opencc_mode": "none",
    # Lịch quét hàng ngày RIÊNG từng site — MẶC ĐỊNH TẮT. Chỉ chạy khi
    # người dùng bật trong cài đặt site + chọn thể loại + giờ chạy.
    # (trước đây scheduler quét mọi genre.enabled lúc crawl_hour toàn cục).
    "daily_enabled": False,
    "daily_hour": 6,
    "daily_minute": 0,
    # genre_key trong bảng Genre của site đó — "" = chưa chọn → bỏ qua dù đã bật.
    "daily_genre_key": "",
    # HTTP/SOCKS proxy riêng site (vd Clash `http://127.0.0.1:7890`). Rỗng =
    # dùng proxy vùng (Settings) / env. Ưu tiên cao hơn vùng + env.
    "http_proxy": "",
}


def per_site_key(key: str, source_key: str) -> str:
    """`"scan_window"` + `"bqgxs_com"` -> `"crawl.scan_window.bqgxs_com"`."""
    return f"crawl.{key}.{source_key}"


class SettingsModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


def seed_missing(db: Session, defaults: dict[str, Any]) -> None:
    """Chỉ tạo key nào CHƯA có, không ghi đè giá trị người dùng đã chỉnh —
    dùng chung cho cả seed global (`seed_defaults`) lẫn seed riêng từng site
    (`main._seed_per_site_settings`)."""
    existing = {row.key for row in db.query(SettingsModel.key).all()}
    for key, value in defaults.items():
        if key not in existing:
            db.add(SettingsModel(key=key, value=value))
    db.commit()


def seed_defaults(db: Session) -> None:
    """Gọi lúc khởi động app — seed các setting TOÀN CỤC."""
    seed_missing(db, SEED_DEFAULTS)


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(SettingsModel, key)
    if row is None:
        return SEED_DEFAULTS.get(key, default)
    return row.value


def get_per_site_setting(db: Session, key: str, source_key: str) -> Any:
    """Đọc 1 setting RIÊNG của 1 site (vd `key="scan_window"`) — fallback về
    `PER_SITE_CRAWL_DEFAULTS` nếu site đó chưa được seed (vd site mới thêm,
    chưa restart app lần nào)."""
    value = get_setting(db, per_site_key(key, source_key))
    return value if value is not None else PER_SITE_CRAWL_DEFAULTS.get(key)


def get_per_site_int(db: Session, key: str, source_key: str) -> int:
    return int(get_per_site_setting(db, key, source_key))


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(SettingsModel, key)
    if row is None:
        db.add(SettingsModel(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_all(db: Session) -> dict[str, Any]:
    merged = dict(SEED_DEFAULTS)
    for row in db.query(SettingsModel).all():
        merged[row.key] = row.value
    return merged
