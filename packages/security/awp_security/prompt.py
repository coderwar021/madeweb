from __future__ import annotations

import re

MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "忽略之前",
    "忽略以上",
    "忽略前面",
    "system prompt",
    "you are now",
    "begin private key",
    "ssh-rsa",
    "sk-",
)


def clean_copy(text: str, limit: int = 80) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text or "")
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"(?i)javascript:", "", text)
    text = re.sub(r"(?i)https?://\S+", "", text)
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9]{8,}\b", "", text)
    text = re.sub(r"(?i)\b(api[_-]?key|password)\s*[:=]\s*\S+", "", text)
    text = text.replace("..", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def sanitize_prompt(prompt: str) -> str:
    prompt = (prompt or "").replace("\x00", "")
    kept: list[str] = []
    for part in re.split(r"[\n。]+", prompt):
        lowered = part.lower()
        if any(marker in lowered for marker in MARKERS):
            continue
        kept.append(part)
    return clean_copy(" ".join(kept), 500)
