from docctl.text_sanitize import sanitize_text


def test_sanitize_text_removes_unsafe_control_chars() -> None:
    value = "a\x00b\tc\nd\x1fe\x7ff"
    assert sanitize_text(value) == "ab\tc\ndef"
