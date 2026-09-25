# Thêm 1 site nguồn mới (buyer / integrator)

Mọi site là 1 class implement `SourcePort`, đăng ký trong
`crawl-service/src/crawl/infrastructure/sources/registry.py`.

## 1. Copy template

Site HTML thuần → kế thừa `BaseHtmlSource` + `SourceConfig`:

```python
# crawl-service/src/crawl/infrastructure/sources/my_site_source.py
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

class MySiteSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="my_site",           # unique, snake_case
                name="example.com",
                base_url="https://www.example.com",
                genre_item_selector="...",
                genre_title_selector="...",
                chapter_list_selector="...",
                content_selector="...",
                novel_title_selector="h1",
                # optional:
                # novel_author_selector="...",
                # novel_cover_selector="...",
                # paginate_list_url=self._paginate,
                # novel_url_from_chapter=self._derive,
            )
        )
```

Site cần Playwright/TLS → xem `BaseBrowserSource` / `qidian_com_source.py`.

## 2. Đăng ký

Trong `registry.py`:

1. `from ... import MySiteSource`
2. `_my = MySiteSource()`
3. Thêm vào dict `SOURCES`
4. Thêm `GENRE_SEEDS` (đúng URL thể loại **thật** trên site — không bịa)

## 3. Kiểm tra nhanh

```bash
# Dev tools (chỉ bản DEV FE) hoặc:
cd crawl-service && PYTHONPATH=src .venv/bin/python - <<'PY'
from crawl.infrastructure.sources.registry import get_source
s = get_source("my_site")
print(s.list_genre_novels_page("https://...", 1)[:3])
PY
```

## 4. Setting mặc định

Sau restart API, per-site settings tự seed từ `PER_SITE_CRAWL_DEFAULTS`.
Site non-zh thường nên `narration_filter=any`, `completion_filter=any`
(đã có logic seed trong `main.py`).

## Supported vs experimental

Ghi rõ trong README / hợp đồng: site nào bạn **cam kết** sửa khi gãy.
Số lượng site trong registry ≠ cam kết hỗ trợ.
