"""JSON output helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any


def _to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_to_serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_serializable(val) for key, val in value.items()}
    return value


def dumps_json(payload: Any) -> str:
    """Serialize payload to deterministic JSON."""
    return json.dumps(
        _to_serializable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
