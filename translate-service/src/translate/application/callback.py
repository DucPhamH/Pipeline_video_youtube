"""Gọi crawl lifecycle callback (best-effort, không fail job)."""
from __future__ import annotations

import logging
import re

import httpx

from platform_.auth import outgoing_headers
from platform_.config import config

logger = logging.getLogger("translate.callback")

_CRAWL_NOVEL_RE = re.compile(r"^crawl:novel:(\d+)$")


def resolve_callback_url(*, callback_url: str | None, external_id: str | None) -> str | None:
    if callback_url and callback_url.strip():
        return callback_url.strip()
    if not external_id:
        return None
    m = _CRAWL_NOVEL_RE.match(external_id.strip())
    if not m:
        return None
    base = (config.crawl_service_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/api/crawl/novels/{m.group(1)}/translate-lifecycle"


def notify_crawl(*, callback_url: str | None, external_id: str | None, status: str, message: str | None = None) -> None:
    url = resolve_callback_url(callback_url=callback_url, external_id=external_id)
    if not url:
        return
    payload = {"status": status, "message": message}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload, headers=outgoing_headers())
            if r.status_code >= 400:
                logger.warning("callback %s → %s %s", url, r.status_code, r.text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("callback %s failed: %s", url, exc)
