"""Redaction helpers for text that crosses into shared coordination state."""

from __future__ import annotations

import re


def redact_sensitive_text(text: object) -> str:
    """Mask common credentials and secret-bearing process arguments."""
    masked = str(text)
    masked = re.sub(r"ctx7sk-[A-Za-z0-9-]+", "ctx7sk-***", masked)
    masked = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "sk-ant-***", masked)
    masked = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", masked, flags=re.IGNORECASE
    )
    masked = re.sub(
        r"((?:ANTHROPIC|OPENAI|CONTEXT7|GITHUB|GH|NPM|API|AUTH|ACCESS|REFRESH)?_?"
        r"(?:API_)?(?:KEY|TOKEN|SECRET|PASSWORD)=)[^\s\"']+",
        r"\1***",
        masked,
        flags=re.IGNORECASE,
    )
    masked = re.sub(
        r"((?:token|secret|password|api[_-]?key|access[_-]?token)[\"']?"
        r"\s*[:=]\s*[\"']?)[^\"'\s,}]+",
        r"\1***",
        masked,
        flags=re.IGNORECASE,
    )
    return masked
