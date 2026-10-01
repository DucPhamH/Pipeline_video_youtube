"""Webhook thông báo (Discord / Telegram / generic JSON POST)."""
from __future__ import annotations

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


def webhook_url_error(url: str) -> str | None:
    """None nếu URL webhook dùng được: http(s), host không phải IP private/
    loopback (trừ khi NOTIFY_ALLOW_PRIVATE_WEBHOOK=true). Rỗng = tắt, hợp lệ."""
    url = (url or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return "Webhook URL phải là http(s)://…"
    try:
        from platform_.config import config

        allow_private = bool(config.notify_allow_private_webhook)
    except Exception:
        allow_private = False
    if not allow_private:
        from crawl.infrastructure.sources.fetch_guard import host_is_private

        if host_is_private(parsed.hostname):
            return "Webhook URL trỏ tới địa chỉ nội bộ/private — bật NOTIFY_ALLOW_PRIVATE_WEBHOOK nếu cố ý"
    return None


def send_webhook(url: str, *, title: str, body: str, extra: dict[str, Any] | None = None) -> bool:
    """Gửi thông báo. Trả True nếu HTTP 2xx. Nuốt lỗi mạng (không làm fail crawl)."""
    url = (url or "").strip()
    if not url:
        return False
    err = webhook_url_error(url)
    if err:
        logger.warning("Bỏ qua webhook: %s", err)
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


def notify_configured(db, *, title: str, body: str) -> bool:
    """Gửi tới webhook trong setting `notify.webhook_url` (rỗng = tắt, không gửi)."""
    try:
        from platform_.settings_store import get_setting

        url = (get_setting(db, "notify.webhook_url", "") or "").strip()
    except Exception:
        logger.exception("Không đọc được notify.webhook_url")
        return False
    if not url:
        return False
    return send_webhook(url, title=title, body=body)
