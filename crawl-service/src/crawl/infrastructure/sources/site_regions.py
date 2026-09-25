"""Vùng/ngôn ngữ nguồn — filter tab trang Danh sách site."""
from typing import Literal

SiteRegion = Literal["china", "japan", "korea", "vietnam", "taiwan"]

# Site không liệt kê → `china` (clone biquge tiếng Trung).
_SITE_REGION: dict[str, SiteRegion] = {
    "eights_tw_com": "taiwan",
    "linovelib_com": "japan",
    "syosetu_com": "japan",
    "kakuyomu_com": "japan",
    "novelba_com": "japan",
    "daysneo_com": "japan",
    "alphapolis_co_jp": "japan",
    "pixiv_net": "japan",
    "novelpia_com": "korea",
    "munpia_com": "korea",
    "truyenfull_vn": "vietnam",
    "truyenfull_today": "vietnam",
    "dtruyen_com": "vietnam",
    "sstruyen_net": "vietnam",
    "docln_net": "vietnam",
    "esjzone_cc": "taiwan",
    "ixdzs_tw": "taiwan",
    "ttkan_co": "taiwan",
    "quanben_io": "taiwan",
    "zhihu_com": "china",
}


def site_region(source_key: str) -> SiteRegion:
    return _SITE_REGION.get(source_key, "china")
