"""Engine không gọi mạng. Mỗi lần speak ghi lại để test đếm giọng."""
from __future__ import annotations

# ID3 header + padding. Đủ để API trả audio/mpeg trong test; Edge mới ra mp3 nghe được.
SILENT_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 64

calls: list[dict] = []
fail_remaining = 0


class MockEngine:
    name = "mock"

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
        global fail_remaining
        calls.append(
            {
                "text": text,
                "voice": voice,
                "rate": rate,
                "pitch": pitch,
                "volume": volume,
                "style": style,
            }
        )
        if fail_remaining > 0:
            fail_remaining -= 1
            raise RuntimeError("mock fail")
        return SILENT_MP3
