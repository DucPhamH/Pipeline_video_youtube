"""Adapter truyenfull.live — mở được nhiều IP; vẫn dùng CRAWL_PROXY_VN nếu set."""
from crawl.infrastructure.sources.truyenfull_family import TruyenfullFamilySource


class TruyenfullVnSource(TruyenfullFamilySource):
    def __init__(self) -> None:
        super().__init__(
            key="truyenfull_vn",
            name="TruyenFull.live (Việt Nam)",
            base_url="https://truyenfull.live",
        )
