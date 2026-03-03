"""Text sanitization helpers for safe JSON output."""

from __future__ import annotations

import re

_UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str) -> str:
    """Remove unsafe ASCII control characters while preserving tabs/newlines."""
    return _UNSAFE_CONTROL_RE.sub("", value)
