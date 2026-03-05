from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest
import typer

from docctl import cli
from docctl.config import CliConfig
from docctl.models import DoctorCheck, DoctorReport


def _config(tmp_path: Path, *, json_output: bool = False, verbose: bool = False) -> CliConfig:
    return CliConfig(
        index_path=tmp_path,
        collection="test",
        json_output=json_output,
        verbose=verbose,
        embedding_model="model",
        require_write_approval=False,
    )


def test_emit_success_human_output_uses_key_value_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lines: list[str] = []
    monkeypatch.setattr(cli.typer, "echo", lambda value, err=False: lines.append(str(value)))

    cli._emit_success(config=_config(tmp_path, json_output=False), payload={"a": 1, "b": "two"})

    assert lines == ["a: 1", "b: two"]


def test_emit_doctor_human_output_prints_checks_warnings_and_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lines: list[str] = []
    monkeypatch.setattr(cli.typer, "echo", lambda value, err=False: lines.append(str(value)))
    report = DoctorReport(
        ok=False,
        checks=[DoctorCheck(name="embedding", ok=False, message="missing model")],
        warnings=["w1"],
        errors=["e1"],
    )

    cli._emit_doctor(config=_config(tmp_path, json_output=False), report=report)

    assert lines == [
        "ok: False",
        "[FAIL] embedding: missing model",
        "warning: w1",
        "error: e1",
    ]


def test_machine_output_guard_disabled_does_not_redirect_streams(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with cli._machine_output_guard(enabled=False):
        print("visible")
    assert capsys.readouterr().out.strip() == "visible"


def test_handle_error_reraises_typer_exit() -> None:
    with pytest.raises(typer.Exit):
        cli._handle_error(typer.Exit(code=7))


def test_handle_error_maps_generic_exception_to_internal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        cli.typer,
        "echo",
        lambda value, err=False: calls.append((str(value), err)),
    )

    with pytest.raises(typer.Exit) as exc_info:
        cli._handle_error(RuntimeError("boom"))

    assert exc_info.value.exit_code == 50
    assert calls[-1] == ("error: boom", True)


def test_catalog_command_handles_runtime_exception(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "collect_catalog",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("catalog failed")),
    )

    result = runner.invoke(cli.app, ["catalog"])
    assert result.exit_code == 50
    assert "catalog failed" in result.output


def test_doctor_command_fails_when_report_is_not_ok(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda **kwargs: DoctorReport(ok=False, checks=[], warnings=[], errors=["bad"]),
    )

    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 40
    assert "doctor checks failed" in result.output


def test_session_command_handles_runtime_exception(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_session_requests",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("session failed")),
    )

    result = runner.invoke(cli.app, ["session"], input='{"id":"x","op":"stats"}\n')
    assert result.exit_code == 50
    assert "session failed" in result.output


def test_main_invokes_typer_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def _fake_app() -> None:
        calls["count"] += 1

    monkeypatch.setattr(cli, "app", _fake_app)
    cli.main()
    assert calls["count"] == 1


def test_module_main_guard_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(typer.main.Typer, "__call__", lambda self, *args, **kwargs: None)
    existing = sys.modules.pop("docctl.cli", None)
    try:
        runpy.run_module("docctl.cli", run_name="__main__", alter_sys=True)
    finally:
        if existing is not None:
            sys.modules["docctl.cli"] = existing
