"""Shared coercion and request-validation helpers for loosely typed values."""

from __future__ import annotations

from typing import Any

from .errors import DocctlError


def to_int(value: object, *, default: int = 0) -> int:
    """Coerce a value into an integer.

    Args:
        value: Input value from storage or external payloads.
        default: Fallback integer when coercion fails.

    Returns:
        Parsed integer or `default` when the value cannot be interpreted as int.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def to_non_negative_int(value: object) -> int:
    """Coerce a value into a non-negative integer.

    Args:
        value: Input value from manifest or external payloads.

    Returns:
        Parsed integer clamped to zero for negative or invalid values.
    """
    return max(to_int(value, default=0), 0)


def to_optional_str(value: object) -> str | None:
    """Coerce value to optional string.

    Args:
        value: Input value to inspect.

    Returns:
        The string when `value` is `str`; otherwise `None`.
    """
    if isinstance(value, str):
        return value
    return None


def parse_optional_str(value: Any, *, field_name: str) -> str | None:
    """Validate a request field as optional string.

    Args:
        value: Incoming request value.
        field_name: Field label used in deterministic error messages.

    Returns:
        A string or `None` when field is omitted.

    Raises:
        DocctlError: If value is present but not a string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)


def parse_optional_int(
    value: Any,
    *,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Validate a request field as optional integer with bounds.

    Args:
        value: Incoming request value.
        field_name: Field label used in deterministic error messages.
        minimum: Optional inclusive lower bound.
        maximum: Optional inclusive upper bound.

    Returns:
        Parsed integer or `None` when field is omitted.

    Raises:
        DocctlError: If value is not int or violates bounds.
    """
    if value is None:
        return None
    if not isinstance(value, int):
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    if minimum is not None and value < minimum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    if maximum is not None and value > maximum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    return value


def parse_optional_float(
    value: Any,
    *,
    field_name: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """Validate a request field as optional float with bounds.

    Args:
        value: Incoming request value.
        field_name: Field label used in deterministic error messages.
        minimum: Optional inclusive lower bound.
        maximum: Optional inclusive upper bound.

    Returns:
        Parsed float or `None` when field is omitted.

    Raises:
        DocctlError: If value is not numeric or violates bounds.
    """
    if value is None:
        return None
    if not isinstance(value, (float, int)):
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    if maximum is not None and parsed > maximum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    return parsed
