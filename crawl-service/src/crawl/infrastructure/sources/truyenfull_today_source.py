"""Adapter truyenfull.today — mirror chính (lncrawl); thường cần CRAWL_PROXY_VN."""
from crawl.infrastructure.sources.truyenfull_family import TruyenfullFamilySource


class TruyenfullTodaySource(TruyenfullFamilySource):
    use_ajax_chapter_list = True

    def __init__(self) -> None:
        super().__init__(
            key="truyenfull_today",
            name="TruyenFull.today (VN · cần proxy)",
            base_url="https://truyenfull.today",
        )
