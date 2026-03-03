from docctl.jsonio import dumps_json


def test_json_output_is_deterministic() -> None:
    payload = {
        "b": 2,
        "a": {
            "d": 4,
            "c": 3,
        },
    }

    first = dumps_json(payload)
    second = dumps_json(payload)

    assert first == second
    assert first == '{"a":{"c":3,"d":4},"b":2}'
