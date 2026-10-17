from __future__ import annotations

import logging
import re

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)
_SK = re.compile(r"(?i)\bsk-[A-Za-z0-9]{8,}\b")
_AUTH = re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?\S+")
_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|password|secret|token|cookie)\b(\s*[:=]\s*)(\S+)"
)


def redact(text: str) -> str:
    text = _PRIVATE_KEY.sub("[REDACTED]", text)
    text = _SK.sub("[REDACTED]", text)
    text = _AUTH.sub(r"\1[REDACTED]", text)
    text = _ASSIGN.sub(r"\1\2[REDACTED]", text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True
