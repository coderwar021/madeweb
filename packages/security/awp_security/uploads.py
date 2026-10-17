from __future__ import annotations

SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
)


def sniff_image(data: bytes) -> tuple[str, str] | None:
    if len(data) < 12 or len(data) > 5 * 1024 * 1024:
        return None
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    for magic, mime, ext in SIGNATURES:
        if data.startswith(magic):
            return mime, ext
    return None
