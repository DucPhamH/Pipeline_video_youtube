"""Pipeline nội dung sau fetch — VIP lock, OCR ảnh, hook decrypt Qidian."""
from __future__ import annotations

import re
from pathlib import Path

from crawl.domain.ports import ScrapeError

class NonRetryableScrapeError(ScrapeError):
    """Lỗi retry cũng vô ích (404/403, chương VIP khoá) — bỏ qua backoff."""


class VipLockedError(NonRetryableScrapeError):
    """Chương khoá VIP / cần cookie đăng nhập."""


class ChallengeError(NonRetryableScrapeError):
    """Trang Cloudflare/JS-challenge thay cho nội dung thật (chương, mục lục,
    danh sách) — báo lỗi rõ thay vì parse ra 0 kết quả. Không retry ngay
    (httpx thường không qua được challenge; cần cookie cf_clearance/tầng browser)."""


class RateLimitedError(ScrapeError):
    """HTTP 429 — `retry_after` (giây) lấy từ header Retry-After nếu có."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


_VIP_LOCK_MARKERS = (
    "您还没有订阅本章节",
    "请登录后在继续阅读",
    "请登录后继续阅读",
    "这是VIP章节",
    "订阅后可阅读",
    "需要订阅",
    "付费章节",
    "VIP章节, 余下还有",
)


def assert_not_vip_locked(html: str, *, source_key: str, url: str) -> None:
    for marker in _VIP_LOCK_MARKERS:
        if marker in html:
            raise VipLockedError(
                f"[{source_key}] Chương khoá VIP/cần cookie đăng nhập "
                f"(marker={marker!r}) tại {url}"
            )


def check_fetched_html(html: str, *, source_key: str, url: str) -> None:
    """Kiểm tra HTML sau fetch — dùng chung mọi adapter (httpx/TLS/browser).

    Phát hiện sớm trang CF/challenge và chương VIP để crawl linh hoạt có thể
    bỏ qua từng chương thay vì lưu rác hoặc fail cả truyện."""
    from crawl.infrastructure.sources.tls_fetch import looks_like_cloudflare_challenge

    if looks_like_cloudflare_challenge(html):
        raise ChallengeError(f"[{source_key}] Cloudflare/challenge tại {url}")
    assert_not_vip_locked(html, source_key=source_key, url=url)


def ocr_image_bytes(image_bytes: bytes) -> str:
    """OCR ảnh chương (ciweimao VIP…). Cần `rapidocr-onnxruntime`."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ScrapeError(
            "Thiếu rapidocr-onnxruntime — pip install rapidocr-onnxruntime để OCR VIP ảnh"
        ) from exc

    engine = RapidOCR()
    result, _ = engine(image_bytes)
    if not result:
        raise ScrapeError("OCR không đọc được chữ từ ảnh chương")
    lines = [line[1] for line in result if len(line) > 1 and line[1]]
    text = "\n".join(lines).strip()
    if not text:
        raise ScrapeError("OCR trả về rỗng")
    return text


def ocr_image_file(path: Path | str) -> str:
    return ocr_image_bytes(Path(path).read_bytes())


_QIDIAN_TOOLS = Path(__file__).resolve().parents[4] / "tools" / "qidian_decrypt"


def qidian_decrypt_vip(
    ciphertext: str,
    chapter_id: str,
    fkp: str,
    fuid: str,
) -> str:
    """Gọi Node script giải mã VIP Qidian. Cần Node 18+ và asset Fock."""
    import json
    import shutil
    import subprocess

    if not shutil.which("node"):
        raise ScrapeError(
            "VIP Qidian cần Node.js 18+ trên PATH "
            "(và tools/qidian_decrypt đã chuẩn bị asset)"
        )
    if not (ciphertext and chapter_id and fkp and fuid):
        raise ScrapeError("VIP Qidian thiếu tham số decrypt (content/fkp/fuid/cookie ywguid)")

    script = _QIDIAN_TOOLS / "qidian_decrypt_node.js"
    if not script.is_file():
        raise ScrapeError(f"Thiếu script decrypt: {script}")

    from crawl.infrastructure.sources.qidian_decrypt_assets import ensure_fock_asset

    ensure_fock_asset(_QIDIAN_TOOLS)

    payload = json.dumps([ciphertext, chapter_id, fkp, fuid], ensure_ascii=False)
    try:
        proc = subprocess.run(
            ["node", str(script)],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=60,
            cwd=str(_QIDIAN_TOOLS),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScrapeError("Node decrypt Qidian timeout") from exc

    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="ignore")[:300]
        raise ScrapeError(f"Node decrypt Qidian thất bại: {err or proc.returncode}")

    out = (proc.stdout or b"").decode("utf-8", errors="ignore").strip()
    if not out:
        raise ScrapeError("Node decrypt Qidian trả về rỗng")
    return out


def extract_qidian_ssr_chapter(html: str) -> dict | None:
    """Lấy ssr chapterInfo từ trang Qidian (nếu có)."""
    import json

    # g_data / pageContext patterns — tối giản, đủ free chapter
    m = re.search(
        r'{"pageContext":\{.*?"chapterInfo"\s*:\s*(\{.*?\})\s*,\s*"chapterNavInfo"',
        html,
        re.DOTALL,
    )
    if not m:
        # fallback: tìm "chapterInfo":{...} trong script
        m2 = re.search(r'"chapterInfo"\s*:\s*(\{.+?\})\s*,\s*"chapterNavInfo"', html, re.DOTALL)
        if not m2:
            return None
        raw = m2.group(1)
    else:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # thử unescape
        try:
            return json.loads(raw.encode("utf-8").decode("unicode_escape"))
        except Exception:
            return None
