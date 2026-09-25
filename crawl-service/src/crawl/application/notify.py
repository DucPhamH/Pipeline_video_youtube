"""Webhook thông báo (Discord / Telegram / generic JSON POST)."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("notify")


def _looks_like_discord(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "discord.com" in host or "discordapp.com" in host


def _looks_like_telegram(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "api.telegram.org" in host


def send_webhook(url: str, *, title: str, body: str, extra: dict[str, Any] | None = None) -> bool:
    """Gửi thông báo. Trả True nếu HTTP 2xx. Nuốt lỗi mạng (không làm fail crawl)."""
    url = (url or "").strip()
    if not url:
        return False
    payload: dict[str, Any]
    if _looks_like_discord(url):
        payload = {"content": f"**{title}**\n{body}"[:1900]}
    elif _looks_like_telegram(url):
        # Expect full sendMessage URL: https://api.telegram.org/botTOKEN/sendMessage?chat_id=ID
        # or base sendMessage endpoint — caller should put chat_id in query; we POST JSON.
        payload = {"text": f"{title}\n{body}"[:3500]}
        if extra and "chat_id" in extra:
            payload["chat_id"] = extra["chat_id"]
    else:
        payload = {"title": title, "body": body, **(extra or {})}

    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if r.status_code >= 300:
            logger.warning("Webhook HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception:
        logger.exception("Webhook failed")
        return False


def format_scan_summary(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Không có site nào chạy lịch hôm nay."
    lines = []
    for item in results:
        lines.append(
            f"• {item.get('source_key')}/{item.get('genre_label')}: "
            f"+{item.get('discovered', 0)} mới, sync={item.get('synced', 0)}, "
            f"loại={item.get('rejected', 0)}, lỗi={item.get('errors', 0)}"
        )
    return "\n".join(lines)
