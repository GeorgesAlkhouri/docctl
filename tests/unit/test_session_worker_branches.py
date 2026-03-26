from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from docctl import service_session_worker as session_worker
from docctl.config import CliConfig
from docctl.errors import DocctlError, InternalDocctlError
from docctl.service_types import ServiceDependencies


def _config(tmp_path: Path) -> CliConfig:
    return CliConfig(
        index_path=tmp_path / "index",
        collection="test",
        json_output=False,
        verbose=False,
        embedding_model="embed",
        rerank_model="rerank",
        require_write_approval=False,
    )


def _deps() -> ServiceDependencies:
    return ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: object(),
        reranker_factory=None,
    )


@contextmanager
def _noop_lock(_path: Path):
    yield


class _ProcessStub:
    def __init__(self, *, pid: int | None, alive: bool = True, exitcode: int | None = None) -> None:
        self.pid = pid
        self._alive = alive
        self.exitcode = exitcode

    def is_alive(self) -> bool:
        return self._alive


def _state(*, socket_path: Path, pid: int = 123) -> session_worker.SessionState:
    return session_worker.SessionState(
        schema_version=1,
        protocol_version=1,
        status="running",
        pid=pid,
        socket_path=str(socket_path),
        index_path="/tmp/index",
        collection="default",
        embedding_model="embed",
        rerank_model="rerank",
        allow_model_download=False,
        idle_ttl_seconds=10,
        started_at="2026-01-01T00:00:00+00:00",
        last_used_at="2026-01-01T00:00:00+00:00",
        expires_at="2026-01-01T00:00:10+00:00",
    )


def test_require_posix_and_validate_idle_ttl_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_worker.os, "name", "nt", raising=False)
    with pytest.raises(DocctlError, match="POSIX systems only"):
        session_worker._require_posix()

    with pytest.raises(DocctlError, match="invalid idle ttl"):
        session_worker._validate_idle_ttl(0)


def test_session_artifacts_falls_back_to_tempdir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(session_worker.ENV_SESSION_DIR, raising=False)
    monkeypatch.setattr(session_worker.tempfile, "gettempdir", lambda: "/tmp")
    monkeypatch.setattr(session_worker.os, "getuid", lambda: 42)

    artifacts = session_worker._session_artifacts()
    assert str(artifacts.runtime_dir) == "/tmp/docctl-session-42"


def test_stop_session_worker_returns_stopped_when_no_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = session_worker.SessionArtifacts(
        runtime_dir=tmp_path,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        socket_path=tmp_path / "sock",
    )
    calls: dict[str, int] = {"clear": 0}
    monkeypatch.setattr(session_worker, "_require_posix", lambda: None)
    monkeypatch.setattr(session_worker, "_session_artifacts", lambda: artifacts)
    monkeypatch.setattr(session_worker, "_ensure_runtime_dir", lambda runtime_dir: None)
    monkeypatch.setattr(session_worker, "_session_lock", _noop_lock)
    monkeypatch.setattr(session_worker, "_read_state", lambda **kwargs: None)
    monkeypatch.setattr(
        session_worker,
        "_clear_artifacts_locked",
        lambda **kwargs: calls.__setitem__("clear", calls["clear"] + 1),
    )

    payload = session_worker.stop_session_worker()
    assert payload == {"status": "stopped"}
    assert calls["clear"] == 1


class _ServerStub:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self.closed = False

    def bind(self, _path: str) -> None:
        return None

    def listen(self) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        return None

    def accept(self):  # noqa: ANN201
        event = self._events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event, None

    def close(self) -> None:
        self.closed = True


class _ServerNeverAccept:
    def __init__(self) -> None:
        self.closed = False
        self.accept_calls = 0

    def bind(self, _path: str) -> None:
        return None

    def listen(self) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        return None

    def accept(self):  # noqa: ANN201
        self.accept_calls += 1
        raise AssertionError("accept should not be called when idle timeout already elapsed")

    def close(self) -> None:
        self.closed = True


class _ConnStub:
    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
        _ = (exc_type, exc, tb)
        return False


def test_serve_session_worker_handles_timeout_and_socket_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker.sock"
    state_path = tmp_path / "state.json"
    server = _ServerStub(events=[TimeoutError(), OSError("stop")])
    cleanup_calls: dict[str, int] = {"unlink": 0, "remove_state": 0}
    time_values = iter([0.0, 0.1, 0.2])

    monkeypatch.setattr(session_worker, "_require_posix", lambda: None)
    monkeypatch.setattr(session_worker.os, "chmod", lambda _path, _mode: None)
    monkeypatch.setattr(session_worker, "SessionRuntime", lambda request, deps: object())
    monkeypatch.setattr(session_worker.socket, "socket", lambda *args, **kwargs: server)
    monkeypatch.setattr(session_worker.time, "time", lambda: next(time_values))
    monkeypatch.setattr(
        session_worker,
        "_safe_unlink",
        lambda **kwargs: cleanup_calls.__setitem__("unlink", cleanup_calls["unlink"] + 1),
    )
    monkeypatch.setattr(
        session_worker,
        "_safe_remove_state_if_owned",
        lambda **kwargs: cleanup_calls.__setitem__(
            "remove_state", cleanup_calls["remove_state"] + 1
        ),
    )

    session_worker.serve_session_worker(
        config=_config(tmp_path),
        socket_path=socket_path,
        state_path=state_path,
        idle_ttl_seconds=10,
        allow_model_download=False,
        deps=_deps(),
    )

    assert server.closed is True
    assert cleanup_calls["unlink"] >= 1
    assert cleanup_calls["remove_state"] == 1


def test_serve_session_worker_updates_last_used_on_handled_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker.sock"
    state_path = tmp_path / "state.json"
    server = _ServerStub(events=[_ConnStub(), OSError("stop")])
    update_calls: dict[str, int] = {"count": 0}
    time_values = iter([0.0, 0.1, 0.2, 0.3])

    monkeypatch.setattr(session_worker, "_require_posix", lambda: None)
    monkeypatch.setattr(session_worker.os, "chmod", lambda _path, _mode: None)
    monkeypatch.setattr(session_worker, "SessionRuntime", lambda request, deps: object())
    monkeypatch.setattr(session_worker.socket, "socket", lambda *args, **kwargs: server)
    monkeypatch.setattr(session_worker.time, "time", lambda: next(time_values))
    monkeypatch.setattr(session_worker, "_safe_unlink", lambda **kwargs: None)
    monkeypatch.setattr(session_worker, "_safe_remove_state_if_owned", lambda **kwargs: None)
    monkeypatch.setattr(session_worker, "_serve_connection", lambda **kwargs: True)
    monkeypatch.setattr(
        session_worker,
        "_update_last_used_state",
        lambda **kwargs: update_calls.__setitem__("count", update_calls["count"] + 1),
    )

    session_worker.serve_session_worker(
        config=_config(tmp_path),
        socket_path=socket_path,
        state_path=state_path,
        idle_ttl_seconds=5,
        allow_model_download=False,
        deps=_deps(),
    )

    assert update_calls["count"] == 1


def test_serve_session_worker_exits_on_idle_timeout_without_accept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker.sock"
    state_path = tmp_path / "state.json"
    server = _ServerNeverAccept()
    cleanup_calls: dict[str, int] = {"unlink": 0, "remove_state": 0}
    # Initial last_used=0.0 then loop check sees 10.0-0.0 >= 1 and breaks.
    time_values = iter([0.0, 10.0])

    monkeypatch.setattr(session_worker, "_require_posix", lambda: None)
    monkeypatch.setattr(session_worker.os, "chmod", lambda _path, _mode: None)
    monkeypatch.setattr(session_worker, "SessionRuntime", lambda request, deps: object())
    monkeypatch.setattr(session_worker.socket, "socket", lambda *args, **kwargs: server)
    monkeypatch.setattr(session_worker.time, "time", lambda: next(time_values))
    monkeypatch.setattr(
        session_worker,
        "_safe_unlink",
        lambda **kwargs: cleanup_calls.__setitem__("unlink", cleanup_calls["unlink"] + 1),
    )
    monkeypatch.setattr(
        session_worker,
        "_safe_remove_state_if_owned",
        lambda **kwargs: cleanup_calls.__setitem__(
            "remove_state", cleanup_calls["remove_state"] + 1
        ),
    )

    session_worker.serve_session_worker(
        config=_config(tmp_path),
        socket_path=socket_path,
        state_path=state_path,
        idle_ttl_seconds=1,
        allow_model_download=False,
        deps=_deps(),
    )

    assert server.accept_calls == 0
    assert server.closed is True
    assert cleanup_calls["remove_state"] == 1


def test_load_running_state_clears_stale_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = session_worker.SessionArtifacts(
        runtime_dir=tmp_path,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        socket_path=tmp_path / "sock",
    )
    stale_state = _state(socket_path=artifacts.socket_path)
    cleared: dict[str, int] = {"count": 0}

    monkeypatch.setattr(session_worker, "_read_state", lambda **kwargs: stale_state)
    monkeypatch.setattr(session_worker, "_pid_is_running", lambda **kwargs: False)
    monkeypatch.setattr(
        session_worker,
        "_clear_artifacts_locked",
        lambda **kwargs: cleared.__setitem__("count", cleared["count"] + 1),
    )

    assert session_worker._load_running_state_locked(artifacts=artifacts) is None
    assert cleared["count"] == 1


def test_read_state_handles_invalid_content(tmp_path: Path) -> None:
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    assert session_worker._read_state(path=invalid_json) is None

    invalid_payload = tmp_path / "payload.json"
    invalid_payload.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert session_worker._read_state(path=invalid_payload) is None


def test_state_from_payload_handles_invalid_mapping() -> None:
    assert session_worker._state_from_payload(payload={"schema_version": "x"}) is None


def test_start_worker_locked_raises_on_missing_pid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = session_worker.SessionArtifacts(
        runtime_dir=tmp_path,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        socket_path=tmp_path / "sock",
    )
    binding = session_worker.SessionBinding(
        index_path="/tmp/index",
        collection="default",
        embedding_model="embed",
        rerank_model="rerank",
        allow_model_download=False,
    )

    monkeypatch.setattr(
        session_worker,
        "_start_worker_process",
        lambda **kwargs: _ProcessStub(pid=None),
    )

    with pytest.raises(InternalDocctlError, match="failed to start"):
        session_worker._start_worker_locked(
            config=_config(tmp_path),
            artifacts=artifacts,
            binding=binding,
            idle_ttl_seconds=10,
            allow_model_download=False,
            deps=_deps(),
        )


def test_start_worker_locked_handles_start_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = session_worker.SessionArtifacts(
        runtime_dir=tmp_path,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        socket_path=tmp_path / "sock",
    )
    binding = session_worker.SessionBinding(
        index_path="/tmp/index",
        collection="default",
        embedding_model="embed",
        rerank_model="rerank",
        allow_model_download=False,
    )
    calls: dict[str, int] = {"term": 0, "clear": 0}
    process = _ProcessStub(pid=33)

    monkeypatch.setattr(session_worker, "_start_worker_process", lambda **kwargs: process)
    monkeypatch.setattr(session_worker, "_wait_for_socket_ready", lambda **kwargs: False)
    monkeypatch.setattr(
        session_worker,
        "_terminate_pid",
        lambda **kwargs: calls.__setitem__("term", calls["term"] + 1),
    )
    monkeypatch.setattr(
        session_worker,
        "_clear_artifacts_locked",
        lambda **kwargs: calls.__setitem__("clear", calls["clear"] + 1),
    )

    with pytest.raises(InternalDocctlError, match="failed to start"):
        session_worker._start_worker_locked(
            config=_config(tmp_path),
            artifacts=artifacts,
            binding=binding,
            idle_ttl_seconds=10,
            allow_model_download=False,
            deps=_deps(),
        )
    assert calls == {"term": 1, "clear": 1}


def test_wait_for_socket_ready_dead_or_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dead = _ProcessStub(pid=1, alive=False, exitcode=1)
    assert session_worker._wait_for_socket_ready(process=dead, socket_path=tmp_path / "s") is False

    alive = _ProcessStub(pid=1, alive=True, exitcode=None)
    time_values = iter([0.0, 0.1, 100.0])
    monkeypatch.setattr(session_worker.time, "time", lambda: next(time_values))
    monkeypatch.setattr(session_worker.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(session_worker, "_socket_reachable", lambda **kwargs: False)
    assert session_worker._wait_for_socket_ready(process=alive, socket_path=tmp_path / "s") is False


class _ReaderStub:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.closed = False

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)

    def __iter__(self):  # noqa: ANN204
        return iter(self._lines)

    def close(self) -> None:
        self.closed = True


class _WriterStub:
    def __init__(self) -> None:
        self.buffer: list[str] = []
        self.closed = False

    def write(self, value: str) -> None:
        self.buffer.append(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _ClientSocketStub:
    def __init__(self, reader: _ReaderStub, writer: _WriterStub) -> None:
        self._reader = reader
        self._writer = writer

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
        _ = (exc_type, exc, tb)
        return False

    def settimeout(self, _timeout: float) -> None:
        return None

    def connect(self, _path: str) -> None:
        return None

    def makefile(self, mode: str, encoding: str):  # noqa: ANN001, ANN201
        _ = encoding
        if mode == "r":
            return self._reader
        return self._writer


def test_send_requests_over_socket_handles_blank_and_closed_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blank_reader = _ReaderStub(lines=[])
    blank_writer = _WriterStub()
    monkeypatch.setattr(
        session_worker.socket,
        "socket",
        lambda *args, **kwargs: _ClientSocketStub(blank_reader, blank_writer),
    )
    responses = session_worker._send_requests_over_socket(
        socket_path=tmp_path / "sock",
        request_lines=["   "],
    )
    assert responses == []

    closed_reader = _ReaderStub(lines=[""])
    closed_writer = _WriterStub()
    monkeypatch.setattr(
        session_worker.socket,
        "socket",
        lambda *args, **kwargs: _ClientSocketStub(closed_reader, closed_writer),
    )
    with pytest.raises(InternalDocctlError, match="connection closed unexpectedly"):
        session_worker._send_requests_over_socket(
            socket_path=tmp_path / "sock",
            request_lines=['{"id":"x","op":"stats"}'],
        )


def test_parse_worker_response_validation_errors() -> None:
    with pytest.raises(InternalDocctlError, match="invalid JSON"):
        session_worker._parse_worker_response(line="{")
    with pytest.raises(InternalDocctlError, match="invalid response payload"):
        session_worker._parse_worker_response(line='["not-a-dict"]')


def test_pid_and_socket_helpers_error_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        session_worker.os, "kill", lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError)
    )
    assert session_worker._pid_is_running(pid=1) is False

    monkeypatch.setattr(
        session_worker.os, "kill", lambda pid, signal: (_ for _ in ()).throw(PermissionError)
    )
    assert session_worker._pid_is_running(pid=1) is True

    socket_path = tmp_path / "s.sock"
    socket_path.write_text("x", encoding="utf-8")

    class _ProbeSocket:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
            _ = (exc_type, exc, tb)
            return False

        def settimeout(self, timeout: float) -> None:
            _ = timeout

        def connect(self, path: str) -> None:
            _ = path
            raise OSError("unreachable")

    monkeypatch.setattr(session_worker.socket, "socket", lambda *args, **kwargs: _ProbeSocket())
    assert session_worker._socket_reachable(path=socket_path) is False


def test_terminate_pid_branch_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_worker, "_pid_is_running", lambda **kwargs: False)
    session_worker._terminate_pid(pid=1, timeout_seconds=0.1)

    monkeypatch.setattr(session_worker, "_pid_is_running", lambda **kwargs: True)
    monkeypatch.setattr(
        session_worker.os,
        "kill",
        lambda pid, sig: (
            (_ for _ in ()).throw(ProcessLookupError)
            if sig == session_worker.signal.SIGTERM
            else None
        ),
    )
    session_worker._terminate_pid(pid=1, timeout_seconds=0.1)

    run_states = iter([True, False])
    monkeypatch.setattr(session_worker, "_pid_is_running", lambda **kwargs: next(run_states))
    monkeypatch.setattr(session_worker.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(session_worker.time, "time", lambda: 0.0)
    monkeypatch.setattr(session_worker.time, "sleep", lambda _delay: None)
    session_worker._terminate_pid(pid=1, timeout_seconds=1.0)

    monkeypatch.setattr(session_worker, "_pid_is_running", lambda **kwargs: True)
    time_values = iter([0.0, 0.1, 2.0])
    monkeypatch.setattr(session_worker.time, "time", lambda: next(time_values))
    monkeypatch.setattr(session_worker.time, "sleep", lambda _delay: None)

    def _kill_with_sigkill_lookup(pid: int, sig: int) -> None:
        _ = pid
        if sig == session_worker.signal.SIGKILL:
            raise ProcessLookupError

    monkeypatch.setattr(session_worker.os, "kill", _kill_with_sigkill_lookup)
    session_worker._terminate_pid(pid=1, timeout_seconds=1.0)


def test_safe_unlink_and_safe_remove_state_if_owned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self: (_ for _ in ()).throw(OSError("cannot unlink")),
    )
    session_worker._safe_unlink(path=tmp_path / "missing")

    state_path = tmp_path / "state.json"
    removed: dict[str, int] = {"count": 0}
    monkeypatch.setattr(session_worker, "_read_state", lambda **kwargs: None)
    monkeypatch.setattr(
        session_worker,
        "_safe_unlink",
        lambda **kwargs: removed.__setitem__("count", removed["count"] + 1),
    )
    session_worker._safe_remove_state_if_owned(path=state_path, pid=7)
    assert removed["count"] == 0

    monkeypatch.setattr(
        session_worker,
        "_read_state",
        lambda **kwargs: _state(socket_path=tmp_path / "sock", pid=7),
    )
    session_worker._safe_remove_state_if_owned(path=state_path, pid=7)
    assert removed["count"] == 1


def test_serve_connection_and_update_last_used_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader = _ReaderStub(lines=["   ", '{"id":"x","op":"stats"}\n'])
    writer = _WriterStub()

    class _Connection:
        def makefile(self, mode: str, encoding: str):  # noqa: ANN001, ANN201
            _ = encoding
            return reader if mode == "r" else writer

    responses = iter([None, {"id": "x", "ok": True, "result": {}}])
    monkeypatch.setattr(
        session_worker,
        "run_session_request_line",
        lambda **kwargs: next(responses),
    )

    used = session_worker._serve_connection(
        connection=_Connection(),
        runtime=object(),
        verbose=False,
    )
    assert used is True
    assert writer.closed is True
    assert reader.closed is True
    assert any('"ok":true' in part for part in writer.buffer)

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(session_worker, "_read_state", lambda **kwargs: None)
    session_worker._update_last_used_state(
        state_path=state_path,
        pid=1,
        idle_ttl_seconds=10,
        last_used=0.0,
    )

    writes: dict[str, Any] = {}
    monkeypatch.setattr(
        session_worker,
        "_read_state",
        lambda **kwargs: _state(socket_path=tmp_path / "sock", pid=2),
    )
    monkeypatch.setattr(
        session_worker,
        "_write_state",
        lambda **kwargs: writes.update(kwargs),
    )
    monkeypatch.setattr(
        session_worker, "_datetime_to_iso", lambda **kwargs: "2026-01-01T00:00:01+00:00"
    )
    monkeypatch.setattr(session_worker, "_expires_at", lambda **kwargs: "2026-01-01T00:00:11+00:00")

    session_worker._update_last_used_state(
        state_path=state_path,
        pid=2,
        idle_ttl_seconds=10,
        last_used=1.0,
    )
    assert "state" in writes
    assert writes["state"].last_used_at == "2026-01-01T00:00:01+00:00"


def test_run_worker_process_setsid_and_delegates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, int] = {"setsid": 0, "serve": 0}

    monkeypatch.setattr(session_worker.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        session_worker.os,
        "setsid",
        lambda: calls.__setitem__("setsid", calls["setsid"] + 1),
    )
    monkeypatch.setattr(
        session_worker,
        "serve_session_worker",
        lambda **kwargs: calls.__setitem__("serve", calls["serve"] + 1),
    )

    session_worker._run_worker_process(
        config=_config(tmp_path),
        socket_path=tmp_path / "sock",
        state_path=tmp_path / "state.json",
        idle_ttl_seconds=5,
        allow_model_download=False,
        deps=_deps(),
    )

    assert calls == {"setsid": 1, "serve": 1}
