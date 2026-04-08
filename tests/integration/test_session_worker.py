from __future__ import annotations

import json
import os
import time
from pathlib import Path

from docctl.cli import app


def _runtime_dir(test_name: str) -> Path:
    return Path("/tmp") / f"docctl-session-{os.getpid()}-{test_name}-{time.time_ns()}"


def test_session_worker_start_status_stop_singleton(runner, tmp_path) -> None:
    _ = tmp_path
    runtime_dir = _runtime_dir("start-stop")
    env = {"DOCCTL_SESSION_DIR": str(runtime_dir)}

    start_result = runner.invoke(app, ["--json", "session", "start"], env=env)
    assert start_result.exit_code == 0, start_result.output
    start_payload = json.loads(start_result.output)
    assert start_payload["status"] == "running"
    pid = start_payload["pid"]

    second_start = runner.invoke(app, ["session", "start"], env=env)
    assert second_start.exit_code == 50
    assert "session already running" in second_start.output

    status_result = runner.invoke(app, ["--json", "session", "status"], env=env)
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    assert status_payload["status"] == "running"
    assert status_payload["pid"] == pid

    stop_result = runner.invoke(app, ["--json", "session", "stop"], env=env)
    assert stop_result.exit_code == 0, stop_result.output
    stop_payload = json.loads(stop_result.output)
    assert stop_payload["status"] == "stopped"


def test_session_exec_auto_start_and_config_mismatch(runner, tmp_path) -> None:
    _ = tmp_path
    runtime_dir = _runtime_dir("exec")
    env = {"DOCCTL_SESSION_DIR": str(runtime_dir)}
    request_lines = '{"id":"q1","op":"stats"}\n'

    exec_result = runner.invoke(app, ["session", "exec"], input=request_lines, env=env)
    assert exec_result.exit_code == 0, exec_result.output
    responses = [json.loads(line) for line in exec_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == "q1"

    status_result = runner.invoke(app, ["--json", "session", "status"], env=env)
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    assert status_payload["status"] == "running"

    mismatch_result = runner.invoke(
        app,
        ["--collection", "other", "session", "exec"],
        input=request_lines,
        env=env,
    )
    assert mismatch_result.exit_code == 50
    assert "running session configuration does not match current options" in mismatch_result.output

    stop_result = runner.invoke(app, ["session", "stop"], env=env)
    assert stop_result.exit_code == 0, stop_result.output


def test_session_worker_idle_ttl_self_terminates(runner, tmp_path) -> None:
    _ = tmp_path
    runtime_dir = _runtime_dir("ttl")
    env = {"DOCCTL_SESSION_DIR": str(runtime_dir)}

    start_result = runner.invoke(
        app,
        ["--json", "session", "start", "--idle-ttl", "1"],
        env=env,
    )
    assert start_result.exit_code == 0, start_result.output
    start_payload = json.loads(start_result.output)
    assert start_payload["status"] == "running"

    deadline = time.time() + 5.0
    while time.time() < deadline:
        status_result = runner.invoke(app, ["--json", "session", "status"], env=env)
        assert status_result.exit_code == 0, status_result.output
        status_payload = json.loads(status_result.output)
        if status_payload["status"] == "stopped":
            break
        time.sleep(0.1)

    final_status = runner.invoke(app, ["--json", "session", "status"], env=env)
    assert final_status.exit_code == 0, final_status.output
    final_payload = json.loads(final_status.output)
    assert final_payload["status"] == "stopped"
