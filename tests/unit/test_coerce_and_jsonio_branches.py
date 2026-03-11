from __future__ import annotations

from dataclasses import dataclass

import pytest

from docctl.coerce import (
    parse_optional_bool,
    parse_optional_float,
    parse_optional_int,
    to_int,
    to_optional_str,
)
from docctl.errors import DocctlError
from docctl.jsonio import dumps_json


def test_to_int_handles_supported_types_and_fallback() -> None:
    assert to_int(True) == 1
    assert to_int(9) == 9
    assert to_int(3.9) == 3
    assert to_int("7") == 7
    assert to_int("not-a-number", default=5) == 5


def test_to_optional_str_returns_string_or_none() -> None:
    assert to_optional_str("value") == "value"
    assert to_optional_str(123) is None


def test_parse_optional_int_validates_type_and_bounds() -> None:
    assert parse_optional_int(None, field_name="page") is None
    assert parse_optional_int(2, field_name="page", minimum=1, maximum=3) == 2

    with pytest.raises(DocctlError):
        parse_optional_int("2", field_name="page")
    with pytest.raises(DocctlError):
        parse_optional_int(0, field_name="page", minimum=1)
    with pytest.raises(DocctlError):
        parse_optional_int(4, field_name="page", maximum=3)


def test_parse_optional_float_validates_type_and_bounds() -> None:
    assert parse_optional_float(None, field_name="score") is None
    assert parse_optional_float(0.4, field_name="score", minimum=0.0, maximum=1.0) == 0.4
    assert parse_optional_float(1, field_name="score", minimum=0.0, maximum=1.0) == 1.0

    with pytest.raises(DocctlError):
        parse_optional_float("0.5", field_name="score")
    with pytest.raises(DocctlError):
        parse_optional_float(-0.1, field_name="score", minimum=0.0)
    with pytest.raises(DocctlError):
        parse_optional_float(1.1, field_name="score", maximum=1.0)


def test_parse_optional_bool_validates_type() -> None:
    assert parse_optional_bool(None, field_name="rerank") is None
    assert parse_optional_bool(True, field_name="rerank") is True
    assert parse_optional_bool(False, field_name="rerank") is False

    with pytest.raises(DocctlError):
        parse_optional_bool("true", field_name="rerank")


def test_dumps_json_serializes_dataclass_payloads() -> None:
    @dataclass(slots=True)
    class _Payload:
        value: int

    payload = {"items": [_Payload(value=1)]}
    assert dumps_json(payload) == '{"items":[{"value":1}]}'
