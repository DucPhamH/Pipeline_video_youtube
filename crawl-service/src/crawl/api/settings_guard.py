"""Allow-list + kiểm kiểu cho PATCH /settings, và che giá trị nhạy cảm khi
GET /settings. Bảng settings là key-value tự do — không chặn thì client ghi
được key bất kỳ (kể cả cookie phiên / trạng thái nội bộ của scheduler)."""
from __future__ import annotations

from typing import Any

from crawl.application.notify import webhook_url_error
from crawl.application.opencc_convert import OPENCC_MODES
from crawl.domain.services import COMPLETION_FILTERS, NARRATION_FILTERS
from crawl.infrastructure.sources.registry import SOURCES
from platform_.session_cookies import SESSION_COOKIE_SETTING, cookie_hint
from platform_.settings_store import PER_SITE_CRAWL_DEFAULTS, SEED_DEFAULTS, per_site_key

# Key nội bộ — không trả ra API, không cho ghi qua PATCH.
HIDDEN_PREFIXES = ("scheduler.daily_last_fired.", "crawl.migration.")
_COOKIE_PREFIX = f"crawl.{SESSION_COOKIE_SETTING}."

_ENUMS: dict[str, tuple[str, ...]] = {
    "narration_filter": NARRATION_FILTERS,
    "completion_filter": COMPLETION_FILTERS,
    "opencc_mode": tuple(OPENCC_MODES),
}
_INT_RANGES: dict[str, tuple[int, int]] = {
    "scan_window": (1, 1000),
    "max_chapters_per_story": (1, 100000),
    "max_pages_per_scan": (1, 1000),
    "max_consecutive_errors": (1, 1000),
    "daily_hour": (0, 23),
    "daily_minute": (0, 59),
    "crawl.max_chapters_translate_per_day": (0, 100000),
}


def _per_site_lookup() -> dict[str, tuple[str, str]]:
    """full key -> (setting key, source_key)."""
    out: dict[str, tuple[str, str]] = {}
    for source_key in SOURCES:
        for key in PER_SITE_CRAWL_DEFAULTS:
            out[per_site_key(key, source_key)] = (key, source_key)
    return out


def _check_type(name: str, default: Any, value: Any) -> tuple[Any, str | None]:
    if isinstance(default, bool):
        if not isinstance(value, bool):
            return None, f"{name}: phải là boolean"
        return value, None
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"{name}: phải là số nguyên"
        return value, None
    if isinstance(default, str):
        if not isinstance(value, str):
            return None, f"{name}: phải là chuỗi"
        return value.strip(), None
    return value, None


def validate_settings_patch(values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Trả (giá trị đã chuẩn hoá, danh sách lỗi). Có lỗi -> không ghi gì."""
    per_site = _per_site_lookup()
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for full_key, value in values.items():
        if full_key in SEED_DEFAULTS:
            setting_key, default = full_key, SEED_DEFAULTS[full_key]
        elif full_key in per_site:
            setting_key = per_site[full_key][0]
            default = PER_SITE_CRAWL_DEFAULTS[setting_key]
        else:
            errors.append(f"{full_key}: key không được phép")
            continue
        checked, err = _check_type(full_key, default, value)
        if err:
            errors.append(err)
            continue
        if setting_key in _ENUMS and checked not in _ENUMS[setting_key]:
            errors.append(f"{full_key}: phải là 1 trong {', '.join(_ENUMS[setting_key])}")
            continue
        if setting_key in _INT_RANGES:
            lo, hi = _INT_RANGES[setting_key]
            if not lo <= checked <= hi:
                errors.append(f"{full_key}: phải trong khoảng {lo}..{hi}")
                continue
        if setting_key == "notify.webhook_url":
            werr = webhook_url_error(checked)
            if werr:
                errors.append(f"{full_key}: {werr}")
                continue
        clean[full_key] = checked
    return clean, errors


def public_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Bản trả ra API: bỏ key nội bộ, cookie phiên chỉ còn has_cookie + hint."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key.startswith(HIDDEN_PREFIXES):
            continue
        if key.startswith(_COOKIE_PREFIX):
            raw = value if isinstance(value, str) else ("" if value is None else str(value))
            out[key] = {"has_cookie": bool(raw.strip()), "hint": cookie_hint(raw)}
            continue
        out[key] = value
    return out


def daily_schedule_sources(keys: list[str]) -> set[str]:
    """source_key có setting lịch hàng ngày (daily_*) nằm trong `keys`."""
    per_site = _per_site_lookup()
    return {
        per_site[k][1]
        for k in keys
        if k in per_site and per_site[k][0].startswith("daily_")
    }
