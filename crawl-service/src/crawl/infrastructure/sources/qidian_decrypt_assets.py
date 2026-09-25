"""Tải asset Fock JS cho Node decrypt Qidian (lần đầu)."""
from __future__ import annotations

from pathlib import Path

import httpx

from crawl.domain.ports import ScrapeError

FOCK_URL = "https://cococdn.qidian.com/coco/s12062024/4819793b.qeooxh.js"
FOCK_NAME = "4819793b.qeooxh.js"


def ensure_fock_asset(tools_dir: Path) -> Path:
    tools_dir.mkdir(parents=True, exist_ok=True)
    dest = tools_dir / FOCK_NAME
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(FOCK_URL)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    except Exception as exc:
        raise ScrapeError(
            f"Không tải được Fock asset Qidian từ CDN — "
            f"đặt thủ công {FOCK_NAME} vào {tools_dir}: {exc}"
        ) from exc
    return dest
