"""Chuẩn hoá URL — thuần Python, dùng chung cho so khớp chương (resume/sync)
và tra truyện đã có khi thêm bằng URL tay."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_HOST_PREFIXES = ("www.", "m.", "wap.")


def chapter_url_key(url: str) -> str:
    """Khoá so khớp 1 URL chương: bỏ khoảng trắng, scheme http/https coi như
    nhau, host viết thường, bỏ "/" cuối path. GIỮ query + fragment (một số
    nguồn phân biệt chương bằng `?id=`/`#n`)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme in ("http", "https"):
        scheme = "https"
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, parts.netloc.lower(), path, parts.query, parts.fragment))


def normalize_novel_url(url: str) -> str:
    """URL mục lục người dùng dán vào: bỏ khoảng trắng + fragment,
    scheme/host viết thường. Không đổi host (bản m./www. có thể có path khác
    hẳn). Chuỗi không phải http(s) (vd đường dẫn file của nguồn demo) giữ
    nguyên."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return raw
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def _bare_host(host: str) -> str:
    for prefix in _HOST_PREFIXES:
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def novel_url_variants(url: str, *, base_url: str = "") -> list[str]:
    """Các biến thể tương đương để tra truyện đã có: http/https, có/không "/"
    cuối, và host www./m. — chỉ khi host thuộc cùng domain với `base_url` của
    nguồn. Phần tử đầu là bản chuẩn hoá."""
    norm = normalize_novel_url(url)
    if not norm:
        return []
    parts = urlsplit(norm)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return [norm]
    hosts = [parts.netloc]
    base_host = urlsplit(base_url).netloc.lower() if base_url else ""
    if base_host and _bare_host(parts.netloc) == _bare_host(base_host):
        bare = _bare_host(base_host)
        for h in (base_host, bare, *(p + bare for p in _HOST_PREFIXES)):
            if h not in hosts:
                hosts.append(h)
    paths = [parts.path]
    if parts.path.endswith("/") and len(parts.path) > 1:
        paths.append(parts.path.rstrip("/"))
    elif parts.path and not parts.path.endswith("/"):
        paths.append(parts.path + "/")
    out: list[str] = []
    raw = (url or "").strip()
    for candidate in [norm, raw]:
        if candidate and candidate not in out:
            out.append(candidate)
    for scheme in (parts.scheme, "https" if parts.scheme == "http" else "http"):
        for host in hosts:
            for path in paths:
                v = urlunsplit((scheme, host, path, parts.query, ""))
                if v not in out:
                    out.append(v)
    return out


def url_host(url: str) -> str:
    """Host viết thường của 1 URL http(s) — "" nếu không phải http(s)."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ("http", "https"):
        return ""
    return (parts.hostname or "").lower()


def host_matches_source(url: str, base_url: str, extra_hosts: tuple[str, ...] | list[str] = ()) -> bool:
    """URL có thuộc domain của nguồn không: cùng host gốc với `base_url` (bỏ
    www./m./wap.), subdomain của host gốc đó, hoặc 1 mirror khai báo
    (`extra_hosts`, cũng tính cả subdomain)."""
    host = url_host(url)
    if not host:
        return False
    roots = []
    base_host = url_host(base_url) if "://" in (base_url or "") else (base_url or "").lower()
    if base_host:
        roots.append(_bare_host(base_host))
    for extra in extra_hosts or ():
        h = url_host(extra) if "://" in extra else extra.strip().lower()
        if h:
            roots.append(_bare_host(h))
    bare = _bare_host(host)
    return any(bare == root or host == root or host.endswith("." + root) for root in roots if root)
