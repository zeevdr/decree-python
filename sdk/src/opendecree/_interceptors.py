"""gRPC metadata interceptors for authentication."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import grpc
import grpc.aio


def _build_metadata(
    *,
    subject: str | None,
    role: str,
    tenant_id: str | None,
    token: str | None,
) -> list[tuple[str, str]]:
    """Build auth metadata pairs."""
    if token:
        return [("authorization", f"Bearer {token}")]
    pairs: list[tuple[str, str]] = []
    if subject:
        pairs.append(("x-subject", subject))
    if role:
        pairs.append(("x-role", role))
    if tenant_id:
        pairs.append(("x-tenant-id", tenant_id))
    return pairs


class AuthInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
):
    """Sync interceptor that injects auth metadata into every call."""

    def __init__(self, metadata: list[tuple[str, str]]) -> None:
        self._metadata = metadata

    def intercept_unary_unary(
        self,
        continuation: Callable[..., Any],
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ) -> Any:
        new_details = _inject_metadata(client_call_details, self._metadata)
        return continuation(new_details, request)

    def intercept_unary_stream(
        self,
        continuation: Callable[..., Any],
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ) -> Any:
        new_details = _inject_metadata(client_call_details, self._metadata)
        return continuation(new_details, request)


class AsyncAuthInterceptor(
    grpc.aio.UnaryUnaryClientInterceptor,
    grpc.aio.UnaryStreamClientInterceptor,
):
    """Async interceptor that injects auth metadata into every call."""

    def __init__(self, metadata: list[tuple[str, str]]) -> None:
        self._metadata = metadata

    async def intercept_unary_unary(
        self,
        continuation: Callable[..., Any],
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        new_details = _inject_aio_metadata(client_call_details, self._metadata)
        return await continuation(new_details, request)

    async def intercept_unary_stream(
        self,
        continuation: Callable[..., Any],
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        new_details = _inject_aio_metadata(client_call_details, self._metadata)
        return await continuation(new_details, request)


def _inject_metadata(
    details: grpc.ClientCallDetails,
    extra: list[tuple[str, str]],
) -> grpc.ClientCallDetails:
    """Return a new ClientCallDetails with extra metadata appended."""
    metadata: list[tuple[str, str]] = list(details.metadata or [])
    metadata.extend(extra)
    return _ClientCallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=metadata,
        credentials=details.credentials,
    )


def _inject_aio_metadata(
    details: grpc.aio.ClientCallDetails,
    extra: list[tuple[str, str]],
) -> grpc.aio.ClientCallDetails:
    """Return a new aio ClientCallDetails with extra metadata appended."""
    metadata = grpc.aio.Metadata()
    if details.metadata:
        for key, value in details.metadata:
            metadata.add(key, value)
    for key, value in extra:
        metadata.add(key, value)
    return grpc.aio.ClientCallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=metadata,
        credentials=details.credentials,
        wait_for_ready=details.wait_for_ready,
    )


class _ClientCallDetails(grpc.ClientCallDetails):
    """Concrete implementation of ClientCallDetails for sync interceptors."""

    def __init__(
        self,
        method: str,
        timeout: float | None,
        metadata: Sequence[tuple[str, str]] | None,
        credentials: grpc.CallCredentials | None,
    ) -> None:
        self.method = method  # type: ignore[assignment]
        self.timeout = timeout  # type: ignore[assignment]
        self.metadata = metadata  # type: ignore[assignment]
        self.credentials = credentials  # type: ignore[assignment]
