"""Singleton session-worker lifecycle and local IPC transport helpers."""

from __future__ import annotations

import json
import multiprocessing
import os
import socket
import tempfile
import time
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .config import CliConfig
from .errors import DocctlError, InternalDocctlError
from .service_session import SessionRuntime, run_session_request_line
from .service_types import ServiceDependencies, SessionStreamRequest

ENV_SESSION_DIR = "DOCCTL_SESSION_DIR"
DEFAULT_SESSION_IDLE_TTL_SECONDS = 900
SESSION_PROTOCOL_VERSION = 1
SESSION_SCHEMA_VERSION = 1
SESSION_START_TIMEOUT_SECONDS = 10.0
SESSION_STOP_TIMEOUT_SECONDS = 5.0
SESSION_CONNECT_TIMEOUT_SECONDS = 5.0
SESSION_CONTROL_STOP_ID = "__session_worker_stop__"
SESSION_CONTROL_STOP_OP = "__control_stop__"
SESSION_STATE_FILENAME = "session-state.json"
SESSION_LOCK_FILENAME = "session.lock"
SESSION_SOCKET_FILENAME = "session.sock"


@dataclass(slots=True, frozen=True)
class SessionArtifacts:
    """Filesystem paths used by the singleton session worker."""

    runtime_dir: Path
    state_path: Path
    lock_path: Path
    socket_path: Path


@dataclass(slots=True, frozen=True)
class SessionBinding:
    """Configuration fields that define whether a running session can be reused."""

    index_path: str
    collection: str
    embedding_model: str
    rerank_model: str
    allow_model_download: bool


@dataclass(slots=True, frozen=True)
class SessionState:
    """Serialized singleton session state stored on disk."""

    schema_version: int
    protocol_version: int
    status: str
    pid: int
    socket_path: str
    index_path: str
    collection: str
    embedding_model: str
    rerank_model: str
    allow_model_download: bool
    idle_ttl_seconds: int
    started_at: str
    last_used_at: str
    expires_at: str


def start_session_worker(
    *,
    config: CliConfig,
    allow_model_download: bool,
    idle_ttl_seconds: int,
    deps: ServiceDependencies,
) -> dict[str, object]:
    """Start the singleton session worker.

    Args:
        config: Resolved CLI configuration.
        allow_model_download: Whether model downloads are allowed in this worker.
        idle_ttl_seconds: Idle timeout before worker self-termination.
        deps: Session runtime dependency bundle.

    Returns:
        Session status payload for the started worker.

    Raises:
        DocctlError: If a worker is already running or runtime validation fails.
    """
    _require_posix()
    _validate_idle_ttl(idle_ttl_seconds)
    artifacts = _session_artifacts()
    binding = _binding_from_config(config=config, allow_model_download=allow_model_download)
    _ensure_runtime_dir(artifacts.runtime_dir)
    with _session_lock(artifacts.lock_path):
        running_state = _load_running_state_locked(artifacts=artifacts)
        if running_state is not None:
            raise DocctlError(
                message="session already running; run `docctl session stop` first",
                exit_code=50,
            )
        started_state = _start_worker_locked(
            config=config,
            artifacts=artifacts,
            binding=binding,
            idle_ttl_seconds=idle_ttl_seconds,
            allow_model_download=allow_model_download,
            deps=deps,
        )
    return _running_payload(state=started_state)


def session_worker_status(
    *,
    config: CliConfig,
    allow_model_download: bool,
) -> dict[str, object]:
    """Return singleton session worker status.

    Args:
        config: Resolved CLI configuration.
        allow_model_download: Current command download flag for config-match checks.

    Returns:
        Running or stopped status payload.
    """
    _require_posix()
    artifacts = _session_artifacts()
    binding = _binding_from_config(config=config, allow_model_download=allow_model_download)
    _ensure_runtime_dir(artifacts.runtime_dir)
    with _session_lock(artifacts.lock_path):
        state = _load_running_state_locked(artifacts=artifacts)
        if state is None:
            return _stopped_payload()
        payload = _running_payload(state=state)
        payload["config_match"] = _state_matches_binding(state=state, binding=binding)
        return payload


def stop_session_worker() -> dict[str, object]:
    """Stop the singleton session worker when it is running.

    Returns:
        Status payload after stop handling.
    """
    _require_posix()
    artifacts = _session_artifacts()
    _ensure_runtime_dir(artifacts.runtime_dir)
    with _session_lock(artifacts.lock_path):
        state = _read_state(path=artifacts.state_path)
        if state is None:
            _clear_artifacts_locked(artifacts=artifacts)
            return _stopped_payload()
        _request_worker_shutdown(socket_path=Path(state.socket_path))
        _wait_for_socket_shutdown(
            socket_path=Path(state.socket_path),
            timeout_seconds=SESSION_STOP_TIMEOUT_SECONDS,
        )
        _clear_artifacts_locked(artifacts=artifacts)
    return _stopped_payload()


def exec_session_requests(  # noqa: PLR0913
    *,
    config: CliConfig,
    request_lines: list[str],
    allow_model_download: bool,
    idle_ttl_seconds: int,
    deps: ServiceDependencies,
) -> list[dict[str, Any]]:
    """Execute NDJSON requests through the singleton worker socket.

    Args:
        config: Resolved CLI configuration.
        request_lines: Raw NDJSON request lines.
        allow_model_download: Whether model downloads are allowed.
        idle_ttl_seconds: Idle timeout for auto-started workers.
        deps: Session runtime dependency bundle.

    Returns:
        Response payload dictionaries for non-empty request lines.

    Raises:
        DocctlError: If session reuse is invalid or socket exchange fails.
    """
    _require_posix()
    _validate_idle_ttl(idle_ttl_seconds)
    artifacts = _session_artifacts()
    binding = _binding_from_config(config=config, allow_model_download=allow_model_download)
    _ensure_runtime_dir(artifacts.runtime_dir)
    with _session_lock(artifacts.lock_path):
        state = _load_running_state_locked(artifacts=artifacts)
        if state is None:
            state = _start_worker_locked(
                config=config,
                artifacts=artifacts,
                binding=binding,
                idle_ttl_seconds=idle_ttl_seconds,
                allow_model_download=allow_model_download,
                deps=deps,
            )
        elif not _state_matches_binding(state=state, binding=binding):
            raise DocctlError(
                message=(
                    "running session configuration does not match current options; "
                    "run `docctl session stop` first"
                ),
                exit_code=50,
            )
    return _send_requests_over_socket(
        socket_path=Path(state.socket_path), request_lines=request_lines
    )


def serve_session_worker(  # noqa: PLR0913
    *,
    config: CliConfig,
    socket_path: Path,
    state_path: Path,
    idle_ttl_seconds: int,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> None:
    """Run the singleton worker server loop until idle timeout or termination.

    Args:
        config: Resolved CLI configuration used by session runtime.
        socket_path: Unix socket path used for request transport.
        state_path: Session state file path.
        idle_ttl_seconds: Idle timeout before automatic shutdown.
        allow_model_download: Whether model downloads are allowed.
        deps: Session runtime dependencies.
    """
    _require_posix()
    _validate_idle_ttl(idle_ttl_seconds)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    _safe_unlink(path=socket_path)
    session_request = SessionStreamRequest(
        config=config,
        request_lines=[],
        allow_model_download=allow_model_download,
    )
    runtime = SessionRuntime(request=session_request, deps=deps)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        server.listen()
        server.settimeout(1.0)
        _serve_worker_loop(
            server=server,
            runtime=runtime,
            verbose=config.verbose,
            state_path=state_path,
            idle_ttl_seconds=idle_ttl_seconds,
        )
    finally:
        server.close()
        _safe_unlink(path=socket_path)
        _safe_remove_state_if_owned(path=state_path, pid=os.getpid())


def _serve_worker_loop(  # noqa: PLR0913
    *,
    server: socket.socket,
    runtime: SessionRuntime,
    verbose: bool,
    state_path: Path,
    idle_ttl_seconds: int,
) -> None:
    last_used = time.time()
    while True:
        if time.time() - last_used >= idle_ttl_seconds:
            break
        try:
            connection, _ = server.accept()
        except TimeoutError:
            continue
        except OSError:
            break
        with connection:
            used_connection, stop_requested = _serve_connection(
                connection=connection,
                runtime=runtime,
                verbose=verbose,
            )
        if used_connection:
            last_used = time.time()
            _update_last_used_state(
                state_path=state_path,
                pid=os.getpid(),
                idle_ttl_seconds=idle_ttl_seconds,
                last_used=last_used,
            )
        if stop_requested:
            break


def _require_posix() -> None:
    if os.name == "posix" and hasattr(socket, "AF_UNIX"):
        return
    raise DocctlError(
        message="session worker mode is supported on POSIX systems only",
        exit_code=50,
    )


def _validate_idle_ttl(idle_ttl_seconds: int) -> None:
    if idle_ttl_seconds >= 1:
        return
    raise DocctlError(
        message="invalid idle ttl: --idle-ttl must be >= 1",
        exit_code=50,
    )


def _session_artifacts() -> SessionArtifacts:
    root_override = os.getenv(ENV_SESSION_DIR)
    if root_override:
        runtime_dir = Path(root_override).expanduser()
    else:
        runtime_dir = Path(tempfile.gettempdir()) / f"docctl-session-{os.getuid()}"
    return SessionArtifacts(
        runtime_dir=runtime_dir,
        state_path=runtime_dir / SESSION_STATE_FILENAME,
        lock_path=runtime_dir / SESSION_LOCK_FILENAME,
        socket_path=runtime_dir / SESSION_SOCKET_FILENAME,
    )


def _ensure_runtime_dir(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)


@contextmanager
def _session_lock(lock_path: Path):
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _binding_from_config(*, config: CliConfig, allow_model_download: bool) -> SessionBinding:
    return SessionBinding(
        index_path=str(config.index_path.resolve(strict=False)),
        collection=config.collection,
        embedding_model=config.embedding_model,
        rerank_model=config.rerank_model,
        allow_model_download=allow_model_download,
    )


def _load_running_state_locked(*, artifacts: SessionArtifacts) -> SessionState | None:
    state = _read_state(path=artifacts.state_path)
    if state is None:
        _safe_unlink(path=artifacts.socket_path)
        return None
    if _socket_reachable(path=Path(state.socket_path)):
        return state
    _clear_artifacts_locked(artifacts=artifacts)
    return None


def _read_state(*, path: Path) -> SessionState | None:
    if not path.exists():
        return None
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    return _state_from_payload(payload=raw_payload)


def _state_from_payload(*, payload: dict[str, object]) -> SessionState | None:
    try:
        typed_payload = cast(dict[str, Any], payload)
        return SessionState(
            schema_version=int(typed_payload["schema_version"]),
            protocol_version=int(typed_payload["protocol_version"]),
            status=str(typed_payload["status"]),
            pid=int(typed_payload["pid"]),
            socket_path=str(typed_payload["socket_path"]),
            index_path=str(typed_payload["index_path"]),
            collection=str(typed_payload["collection"]),
            embedding_model=str(typed_payload["embedding_model"]),
            rerank_model=str(typed_payload["rerank_model"]),
            allow_model_download=bool(typed_payload["allow_model_download"]),
            idle_ttl_seconds=int(typed_payload["idle_ttl_seconds"]),
            started_at=str(typed_payload["started_at"]),
            last_used_at=str(typed_payload["last_used_at"]),
            expires_at=str(typed_payload["expires_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _write_state(*, path: Path, state: SessionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(state), sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def _start_worker_locked(  # noqa: PLR0913
    *,
    config: CliConfig,
    artifacts: SessionArtifacts,
    binding: SessionBinding,
    idle_ttl_seconds: int,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> SessionState:
    process = _start_worker_process(
        config=config,
        socket_path=artifacts.socket_path,
        state_path=artifacts.state_path,
        idle_ttl_seconds=idle_ttl_seconds,
        allow_model_download=allow_model_download,
        deps=deps,
    )
    if process.pid is None:
        raise InternalDocctlError("session worker failed to start")
    started_at = _now_utc_iso()
    state = SessionState(
        schema_version=SESSION_SCHEMA_VERSION,
        protocol_version=SESSION_PROTOCOL_VERSION,
        status="running",
        pid=process.pid,
        socket_path=str(artifacts.socket_path),
        index_path=binding.index_path,
        collection=binding.collection,
        embedding_model=binding.embedding_model,
        rerank_model=binding.rerank_model,
        allow_model_download=binding.allow_model_download,
        idle_ttl_seconds=idle_ttl_seconds,
        started_at=started_at,
        last_used_at=started_at,
        expires_at=_expires_at(last_used_at=started_at, idle_ttl_seconds=idle_ttl_seconds),
    )
    _write_state(path=artifacts.state_path, state=state)
    if _wait_for_socket_ready(process=process, socket_path=artifacts.socket_path):
        return state
    _request_worker_shutdown(socket_path=artifacts.socket_path)
    _wait_for_socket_shutdown(
        socket_path=artifacts.socket_path,
        timeout_seconds=SESSION_STOP_TIMEOUT_SECONDS,
    )
    _clear_artifacts_locked(artifacts=artifacts)
    raise InternalDocctlError("session worker failed to start")


def _start_worker_process(  # noqa: PLR0913
    *,
    config: CliConfig,
    socket_path: Path,
    state_path: Path,
    idle_ttl_seconds: int,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> multiprocessing.process.BaseProcess:
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_run_worker_process,
        kwargs={
            "config": config,
            "socket_path": socket_path,
            "state_path": state_path,
            "idle_ttl_seconds": idle_ttl_seconds,
            "allow_model_download": allow_model_download,
            "deps": deps,
        },
        daemon=False,
    )
    process.start()
    _detach_child_process(process=process)
    return process


def _detach_child_process(*, process: multiprocessing.process.BaseProcess) -> None:
    import multiprocessing.process as multiprocessing_process

    children = getattr(multiprocessing_process, "_children", None)
    if isinstance(children, set):
        children.discard(process)


def _run_worker_process(  # noqa: PLR0913
    *,
    config: CliConfig,
    socket_path: Path,
    state_path: Path,
    idle_ttl_seconds: int,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> None:
    if os.name == "posix":
        with suppress(OSError):
            os.setsid()
    serve_session_worker(
        config=config,
        socket_path=socket_path,
        state_path=state_path,
        idle_ttl_seconds=idle_ttl_seconds,
        allow_model_download=allow_model_download,
        deps=deps,
    )


def _wait_for_socket_ready(
    *, process: multiprocessing.process.BaseProcess, socket_path: Path
) -> bool:
    deadline = time.time() + SESSION_START_TIMEOUT_SECONDS
    while time.time() < deadline:
        if not process.is_alive() and process.exitcode is not None:
            return False
        if _socket_reachable(path=socket_path):
            return True
        time.sleep(0.05)
    return False


def _request_worker_shutdown(*, socket_path: Path) -> None:
    if not _socket_reachable(path=socket_path):
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(SESSION_CONNECT_TIMEOUT_SECONDS)
            client.connect(str(socket_path))
            reader = client.makefile("r", encoding="utf-8")
            writer = client.makefile("w", encoding="utf-8")
            try:
                payload = {"id": SESSION_CONTROL_STOP_ID, "op": SESSION_CONTROL_STOP_OP}
                writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
                writer.write("\n")
                writer.flush()
                _ = reader.readline()
            finally:
                reader.close()
                writer.close()
    except OSError:
        return


def _wait_for_socket_shutdown(*, socket_path: Path, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _socket_reachable(path=socket_path):
            return
        time.sleep(0.05)


def _send_requests_over_socket(
    *,
    socket_path: Path,
    request_lines: list[str],
) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(SESSION_CONNECT_TIMEOUT_SECONDS)
        client.connect(str(socket_path))
        reader = client.makefile("r", encoding="utf-8")
        writer = client.makefile("w", encoding="utf-8")
        try:
            for raw_line in request_lines:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                writer.write(stripped)
                writer.write("\n")
                writer.flush()
                response_line = reader.readline()
                if not response_line:
                    raise InternalDocctlError("session worker connection closed unexpectedly")
                responses.append(_parse_worker_response(line=response_line))
        finally:
            reader.close()
            writer.close()
    return responses


def _parse_worker_response(*, line: str) -> dict[str, Any]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as error:
        raise InternalDocctlError("session worker returned invalid JSON") from error
    if isinstance(payload, dict):
        return payload
    raise InternalDocctlError("session worker returned invalid response payload")


def _state_matches_binding(*, state: SessionState, binding: SessionBinding) -> bool:
    return (
        state.index_path == binding.index_path
        and state.collection == binding.collection
        and state.embedding_model == binding.embedding_model
        and state.rerank_model == binding.rerank_model
        and state.allow_model_download == binding.allow_model_download
    )


def _running_payload(*, state: SessionState) -> dict[str, object]:
    return {
        "status": "running",
        "pid": state.pid,
        "socket_path": state.socket_path,
        "protocol_version": state.protocol_version,
        "index_path": state.index_path,
        "collection": state.collection,
        "embedding_model": state.embedding_model,
        "rerank_model": state.rerank_model,
        "allow_model_download": state.allow_model_download,
        "idle_ttl_seconds": state.idle_ttl_seconds,
        "started_at": state.started_at,
        "last_used_at": state.last_used_at,
        "expires_at": state.expires_at,
    }


def _stopped_payload() -> dict[str, object]:
    return {"status": "stopped"}


def _socket_reachable(*, path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            probe.connect(str(path))
        return True
    except OSError:
        return False


def _clear_artifacts_locked(*, artifacts: SessionArtifacts) -> None:
    _safe_unlink(path=artifacts.socket_path)
    _safe_unlink(path=artifacts.state_path)


def _safe_unlink(*, path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _safe_remove_state_if_owned(*, path: Path, pid: int) -> None:
    state = _read_state(path=path)
    if state is None or state.pid != pid:
        return
    _safe_unlink(path=path)


def _serve_connection(
    *,
    connection: socket.socket,
    runtime: SessionRuntime,
    verbose: bool,
) -> tuple[bool, bool]:
    used_connection = False
    stop_requested = False
    reader = connection.makefile("r", encoding="utf-8")
    writer = connection.makefile("w", encoding="utf-8")
    try:
        for raw_line in reader:
            if _is_control_stop_request(raw_line=raw_line):
                writer.write(
                    json.dumps(
                        {
                            "id": SESSION_CONTROL_STOP_ID,
                            "ok": True,
                            "result": {"status": "stopping"},
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                writer.write("\n")
                writer.flush()
                used_connection = True
                stop_requested = True
                break
            response = run_session_request_line(runtime=runtime, raw_line=raw_line, verbose=verbose)
            if response is None:
                continue
            writer.write(json.dumps(response, sort_keys=True, separators=(",", ":")))
            writer.write("\n")
            writer.flush()
            used_connection = True
    finally:
        reader.close()
        writer.close()
    return used_connection, stop_requested


def _is_control_stop_request(*, raw_line: str) -> bool:
    line = raw_line.strip()
    if not line:
        return False
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("id") == SESSION_CONTROL_STOP_ID
        and payload.get("op") == SESSION_CONTROL_STOP_OP
    )


def _update_last_used_state(
    *,
    state_path: Path,
    pid: int,
    idle_ttl_seconds: int,
    last_used: float,
) -> None:
    state = _read_state(path=state_path)
    if state is None or state.pid != pid:
        return
    last_used_at = _datetime_to_iso(timestamp=last_used)
    updated_state = SessionState(
        schema_version=state.schema_version,
        protocol_version=state.protocol_version,
        status=state.status,
        pid=state.pid,
        socket_path=state.socket_path,
        index_path=state.index_path,
        collection=state.collection,
        embedding_model=state.embedding_model,
        rerank_model=state.rerank_model,
        allow_model_download=state.allow_model_download,
        idle_ttl_seconds=state.idle_ttl_seconds,
        started_at=state.started_at,
        last_used_at=last_used_at,
        expires_at=_expires_at(last_used_at=last_used_at, idle_ttl_seconds=idle_ttl_seconds),
    )
    _write_state(path=state_path, state=updated_state)


def _now_utc_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _datetime_to_iso(*, timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _expires_at(*, last_used_at: str, idle_ttl_seconds: int) -> str:
    last_used = datetime.fromisoformat(last_used_at)
    expires = last_used.timestamp() + idle_ttl_seconds
    return _datetime_to_iso(timestamp=expires)
