import base64
import json

import pytest
from bs4 import BeautifulSoup

from crawl.infrastructure.sources.docln_net_source import decode_protected


def _encode(html: str, scheme: str, key: str = "") -> list[str]:
    parts = [html[: len(html) // 2], html[len(html) // 2 :]]
    chunks = []
    for i, part in enumerate(parts):
        raw = part.encode("utf-8")
        if scheme == "xor_shuffle":
            raw = bytes(b ^ ord(key[j % len(key)]) for j, b in enumerate(raw))
        body = base64.b64encode(raw).decode()
        if scheme == "base64_reverse":
            body = body[::-1]
        chunks.append(f"{i:04d}{body}")
    return list(reversed(chunks))


def _node(chunks: list[str], scheme: str, key: str = ""):
    div = (
        f"<div id='chapter-c-protected' data-s='{scheme}' data-k='{key}' "
        f"data-c='{json.dumps(chunks)}'></div>"
    )
    return BeautifulSoup(div, "html.parser").div


HTML = "<p>Chương một: rồng độc ác.</p><p>Đoạn hai dài hơn một chút.</p>"


@pytest.mark.parametrize(
    "scheme,key", [("xor_shuffle", "2c0e82f09c3f8526"), ("base64_reverse", ""), ("none", "")]
)
def test_decode_protected_schemes(scheme, key):
    assert decode_protected(_node(_encode(HTML, scheme, key), scheme, key)) == HTML


def test_decode_protected_bad_json_returns_none():
    div = BeautifulSoup("<div data-s='none' data-c='not-json'></div>", "html.parser").div
    assert decode_protected(div) is None
