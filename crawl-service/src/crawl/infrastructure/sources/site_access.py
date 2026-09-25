"""Phân loại site theo nhu cầu phiên đăng nhập — dùng filter trang Danh sách site.

- `free`: quét thể loại + chương free không cần cookie.
- `session_optional`: crawl cơ bản OK; VIP/một số chương cần login.
- `session_required`: quét thể loại hoặc crawl chính cần cookie (anti-bot/login).
"""
from typing import Literal

SiteAccessKind = Literal["free", "session_optional", "session_required"]

# Site không liệt kê → mặc định `free` (clone biquge HTML).
_SITE_ACCESS: dict[str, SiteAccessKind] = {
    "qidian_com": "session_required",
    "wenku8_net": "session_required",
    "ciweimao_com": "session_optional",
    "faloo_com": "session_optional",
    "n17k_com": "session_optional",
    "syosetu_com": "free",
    "kakuyomu_com": "free",
    "novelba_com": "free",
    "daysneo_com": "free",
    "alphapolis_co_jp": "free",
    "pixiv_net": "free",
    "munpia_com": "free",
    "jjwxc_net": "session_optional",
    "novelpia_com": "session_optional",
    "truyenfull_vn": "free",
    "truyenfull_today": "free",
    "dtruyen_com": "free",
    "sstruyen_net": "free",
    "docln_net": "session_optional",
    "esjzone_cc": "free",
    "zhihu_com": "session_required",
    "ixdzs_tw": "free",
    "ttkan_co": "free",
    "quanben_io": "free",
}


def site_access_kind(source_key: str) -> SiteAccessKind:
    return _SITE_ACCESS.get(source_key, "free")
