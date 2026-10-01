"""Microsoft Edge neural voices. Style đi qua SSML express-as khi có."""
from __future__ import annotations

import asyncio
import threading
import time
from xml.sax.saxutils import escape

import edge_tts
from edge_tts import communicate as edge_communicate

_lock = threading.Lock()
_BACKOFF = 1.0  # giây; lần thử sau đợi gấp đôi


def ssml_with_style(tc, escaped_text: str, style: str) -> str:
    body = escaped_text
    xmlns = ""
    if style:
        safe = escape(style, {"'": "&apos;", '"': "&quot;"})
        body = f"<mstts:express-as style='{safe}'>{escaped_text}</mstts:express-as>"
        xmlns = " xmlns:mstts='http://www.w3.org/2001/mstts'"
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'{xmlns} xml:lang='en-US'>"
        f"<voice name='{tc.voice}'>"
        f"<prosody pitch='{tc.pitch}' rate='{tc.rate}' volume='{tc.volume}'>"
        f"{body}</prosody></voice></speak>"
    )


class EdgeEngine:
    name = "edge"

    def speak(
        self,
        *,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        style: str,
    ) -> bytes:
        last: Exception | None = None
        for attempt in range(3):
            try:
                return _speak_once(
                    text=text,
                    voice=voice,
                    rate=rate,
                    pitch=pitch,
                    volume=volume,
                    style=style,
                )
            except Exception as exc:  # noqa: BLE001 — retry lỗi mạng tạm
                last = exc
                if attempt < 2:
                    time.sleep(_BACKOFF * (2**attempt))
        raise RuntimeError(f"edge-tts: {last}")


def _speak_once(*, text: str, voice: str, rate: str, pitch: str, volume: str, style: str) -> bytes:
    async def _run() -> bytes:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        if not buf:
            raise RuntimeError("edge-tts trả audio rỗng")
        return bytes(buf)

    if not style:
        return asyncio.run(_run())

    def _patched(tc, escaped_text):
        text_s = escaped_text.decode("utf-8") if isinstance(escaped_text, bytes) else escaped_text
        return ssml_with_style(tc, text_s, style)

    with _lock:
        original = edge_communicate.mkssml
        edge_communicate.mkssml = _patched
        try:
            return asyncio.run(_run())
        finally:
            edge_communicate.mkssml = original
