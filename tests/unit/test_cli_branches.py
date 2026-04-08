from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_callback_sets_rerank_and_embedding_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DOCCTL_EMBEDDING_MODEL", "embed-x")
    monkeypatch.setenv("DOCCTL_RERANK_MODEL", "rerank-x")
    monkeypatch.setenv("DOCCTL_REQUIRE_WRITE_APPROVAL", "1")
    ctx = SimpleNamespace(obj=None)

    cli.callback(
        ctx=ctx,
        index_path=tmp_path,
        collection="c",
        json_output=False,
        verbose=False,
    )

    config = ctx.obj
    assert config.embedding_model == "embed-x"
    assert config.rerank_model == "rerank-x"
    assert config.require_write_approval is True


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


def test_session_start_command_handles_runtime_exception(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "start_session_worker",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("session start failed")),
    )

    result = runner.invoke(cli.app, ["session", "start"])
    assert result.exit_code == 50
    assert "session start failed" in result.output


def test_session_exec_command_handles_runtime_exception(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "exec_session_requests",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("session exec failed")),
    )

    result = runner.invoke(cli.app, ["session", "exec"], input='{"id":"x","op":"stats"}\n')
    assert result.exit_code == 50
    assert "session exec failed" in result.output


def test_session_status_command_handles_runtime_exception(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "session_worker_status",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("session status failed")),
    )

    result = runner.invoke(cli.app, ["session", "status"])
    assert result.exit_code == 50
    assert "session status failed" in result.output


def test_session_stop_command_handles_runtime_exception(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "stop_session_worker",
        lambda: (_ for _ in ()).throw(RuntimeError("session stop failed")),
    )

    result = runner.invoke(cli.app, ["session", "stop"])
    assert result.exit_code == 50
    assert "session stop failed" in result.output


def test_search_command_rejects_rerank_candidates_below_top_k(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "search_chunks", lambda **kwargs: {"hits": []})

    result = runner.invoke(
        cli.app,
        ["search", "query", "--top-k", "5", "--rerank", "--rerank-candidates", "4"],
    )
    assert result.exit_code == 50
    assert "invalid rerank candidate count" in result.output


def test_search_command_returns_early_after_invalid_rerank_candidates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def _fake_handle_error(error: Exception) -> None:
        captured["error"] = str(error)

    monkeypatch.setattr(cli, "_handle_error", _fake_handle_error)
    monkeypatch.setattr(
        cli,
        "search_chunks",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("search should not execute")),
    )

    ctx = SimpleNamespace(obj=_config(tmp_path))
    result = cli.search(
        ctx=ctx,
        query="query",
        top_k=5,
        rerank=True,
        rerank_candidates=4,
    )

    assert result is None
    assert "invalid rerank candidate count" in str(captured.get("error", ""))


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


def test_export_command_handles_runtime_exception(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "export_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("export failed")),
    )

    result = runner.invoke(cli.app, ["export", "snapshot.zip"])
    assert result.exit_code == 50
    assert "export failed" in result.output


def test_import_command_handles_runtime_exception(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "import_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("import failed")),
    )

    result = runner.invoke(cli.app, ["import", "snapshot.zip", "--approve-write"])
    assert result.exit_code == 50
    assert "import failed" in result.output
