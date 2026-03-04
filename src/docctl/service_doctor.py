"""Doctor command orchestration and health-check helpers."""

from __future__ import annotations

import os

from chromadb.api.types import Documents, EmbeddingFunction

from .models import DoctorCheck, DoctorReport
from .service_types import DoctorRequest, ServiceDependencies, Store


def _check_index_path_access(*, request: DoctorRequest) -> tuple[DoctorCheck, list[str]]:
    """Check writability of the index path target.

    Args:
        request: Doctor request payload.

    Returns:
        Tuple containing check result and generated error messages.
    """
    path_target = (
        request.config.index_path
        if request.config.index_path.exists()
        else request.config.index_path.parent
    )
    path_ok = os.access(path_target, os.W_OK)
    check = DoctorCheck(
        name="index_path_access",
        ok=path_ok,
        message=f"write access {'available' if path_ok else 'missing'} for {path_target}",
    )
    errors = [] if path_ok else ["index path is not writable"]
    return check, errors


def _check_embedding_configuration(
    *, request: DoctorRequest, deps: ServiceDependencies
) -> tuple[DoctorCheck, EmbeddingFunction[Documents] | None, bool, list[str]]:
    """Check whether embedding configuration is usable.

    Args:
        request: Doctor request payload.
        deps: Injected dependency factories.

    Returns:
        Tuple of check, embedding function, success flag, and errors.
    """
    try:
        embedding_fn = deps.embedding_factory(
            model_name=request.config.embedding_model,
            allow_download=request.allow_model_download,
            verbose=request.config.verbose,
        )
        check = DoctorCheck(
            name="embedding_configuration",
            ok=True,
            message=f"embedding model ready: {request.config.embedding_model}",
        )
        return check, embedding_fn, True, []
    except Exception as error:  # noqa: BLE001
        check = DoctorCheck(
            name="embedding_configuration",
            ok=False,
            message=str(error),
        )
        return check, None, False, [str(error)]


def _check_collection_availability(
    *,
    request: DoctorRequest,
    deps: ServiceDependencies,
    embedding_fn: EmbeddingFunction[Documents] | None,
    embedding_ok: bool,
) -> tuple[DoctorCheck, Store | None, bool, int, list[str]]:
    """Check collection availability and chunk count.

    Args:
        request: Doctor request payload.
        deps: Injected dependency factories.
        embedding_fn: Ready embedding function when available.
        embedding_ok: Whether embedding initialization succeeded.

    Returns:
        Tuple of check, store instance, success flag, chunk count, and warnings.
    """
    try:
        store = deps.store_factory(
            index_path=request.config.index_path,
            collection_name=request.config.collection,
            embedding_function=embedding_fn if embedding_ok else None,
            create_collection=False,
            embedding_model=request.config.embedding_model,
        )
        chunk_count = store.count()
        check = DoctorCheck(
            name="collection_availability",
            ok=True,
            message=(
                f"collection '{request.config.collection}' available with {chunk_count} chunks"
            ),
        )
        return check, store, True, chunk_count, []
    except Exception as error:  # noqa: BLE001
        check = DoctorCheck(name="collection_availability", ok=False, message=str(error))
        return check, None, False, 0, [str(error)]


def _check_test_query(
    *,
    collection_ok: bool,
    embedding_ok: bool,
    chunk_count: int,
    store: Store | None,
) -> tuple[DoctorCheck, list[str], list[str]]:
    """Run a one-shot test query when prerequisites are met.

    Args:
        collection_ok: Whether collection lookup succeeded.
        embedding_ok: Whether embedding initialization succeeded.
        chunk_count: Number of chunks in collection.
        store: Store adapter instance, when available.

    Returns:
        Tuple of check, warnings, and errors.
    """
    if not (collection_ok and embedding_ok and chunk_count > 0 and store is not None):
        check = DoctorCheck(
            name="test_query",
            ok=False,
            message="test query skipped because collection is unavailable or empty",
        )
        return check, ["test query skipped"], []

    try:
        query_result = store.query(query="health check", top_k=1)
        query_ok = bool((query_result.get("ids") or [[]])[0])
        check = DoctorCheck(
            name="test_query",
            ok=query_ok,
            message=(
                "test query returned at least one hit"
                if query_ok
                else "test query returned no hits"
            ),
        )
        warnings = [] if query_ok else ["test query returned no hits"]
        return check, warnings, []
    except Exception as error:  # noqa: BLE001
        check = DoctorCheck(name="test_query", ok=False, message=str(error))
        return check, [], [str(error)]


def run_doctor(*, request: DoctorRequest, deps: ServiceDependencies) -> DoctorReport:
    """Run repository-local health checks for index and embedding readiness.

    Args:
        request: Doctor request payload.
        deps: Injected dependency factories.

    Returns:
        Structured doctor report with checks, warnings, and errors.
    """
    checks: list[DoctorCheck] = []
    warnings: list[str] = []
    errors: list[str] = []

    path_check, path_errors = _check_index_path_access(request=request)
    checks.append(path_check)
    errors.extend(path_errors)

    embedding_check, embedding_fn, embedding_ok, embedding_errors = _check_embedding_configuration(
        request=request,
        deps=deps,
    )
    checks.append(embedding_check)
    errors.extend(embedding_errors)

    (
        collection_check,
        store,
        collection_ok,
        chunk_count,
        collection_warnings,
    ) = _check_collection_availability(
        request=request,
        deps=deps,
        embedding_fn=embedding_fn,
        embedding_ok=embedding_ok,
    )
    checks.append(collection_check)
    warnings.extend(collection_warnings)

    query_check, query_warnings, query_errors = _check_test_query(
        collection_ok=collection_ok,
        embedding_ok=embedding_ok,
        chunk_count=chunk_count,
        store=store,
    )
    checks.append(query_check)
    warnings.extend(query_warnings)
    errors.extend(query_errors)

    ok = all(check.ok for check in checks)
    return DoctorReport(ok=ok, checks=checks, warnings=warnings, errors=errors)
