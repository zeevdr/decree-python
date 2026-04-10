"""Asynchronous ConfigClient for OpenDecree.

Mirrors the sync ConfigClient API with async/await. Uses grpc.aio for
non-blocking I/O. Metadata is injected directly on each call since
grpc.aio does not support intercept_channel.
"""

from __future__ import annotations

from datetime import timedelta
from typing import overload

import grpc
import grpc.aio

from opendecree._channel import create_aio_channel
from opendecree._interceptors import _build_metadata
from opendecree._retry import RetryConfig, async_with_retry
from opendecree._stubs import (
    ensure_stubs,
    make_string_typed_value,
    process_get_all_response,
    process_get_response,
)
from opendecree.errors import map_grpc_error


class AsyncConfigClient:
    """Asynchronous client for reading and writing OpenDecree configuration values.

    Use as an async context manager::

        async with AsyncConfigClient("localhost:9090", subject="myapp") as client:
            val = await client.get("tenant-id", "payments.fee")
            retries = await client.get("tenant-id", "payments.retries", int)
    """

    def __init__(
        self,
        target: str,
        *,
        subject: str | None = None,
        role: str = "superadmin",
        tenant_id: str | None = None,
        token: str | None = None,
        insecure: bool = True,
        credentials: grpc.ChannelCredentials | None = None,
        timeout: float = 10.0,
        retry: RetryConfig | None = None,
    ) -> None:
        self._timeout = timeout
        self._retry = retry if retry is not None else RetryConfig()

        # grpc.aio doesn't support intercept_channel, so we inject metadata
        # directly on each call via self._metadata().
        self._auth_metadata = _build_metadata(
            subject=subject, role=role, tenant_id=tenant_id, token=token
        )
        self._channel = create_aio_channel(target, insecure=insecure, credentials=credentials)

        cs_pb2, cs_grpc = ensure_stubs()
        self._stub = cs_grpc.ConfigServiceStub(self._channel)
        self._pb2 = cs_pb2

    async def close(self) -> None:
        """Close the underlying gRPC channel."""
        await self._channel.close()

    async def __aenter__(self) -> AsyncConfigClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def _metadata(self) -> list[tuple[str, str]]:
        """Return auth metadata for each call."""
        return list(self._auth_metadata)

    # --- get() with @overload for type safety ---

    @overload
    async def get(self, tenant_id: str, field_path: str) -> str: ...

    @overload
    async def get(self, tenant_id: str, field_path: str, type: type[int]) -> int: ...

    @overload
    async def get(self, tenant_id: str, field_path: str, type: type[float]) -> float: ...

    @overload
    async def get(self, tenant_id: str, field_path: str, type: type[bool]) -> bool: ...

    @overload
    async def get(self, tenant_id: str, field_path: str, type: type[timedelta]) -> timedelta: ...

    @overload
    async def get(
        self,
        tenant_id: str,
        field_path: str,
        type: type[str],
        *,
        nullable: bool,
    ) -> str | None: ...

    async def get(
        self,
        tenant_id: str,
        field_path: str,
        type: type | None = None,
        *,
        nullable: bool = False,
    ) -> object:
        """Get a config value, optionally converting to a specific type.

        Without a type argument, returns the raw string value.
        With a type argument, converts and returns the typed value.

        Args:
            tenant_id: Tenant UUID.
            field_path: Dot-separated field path (e.g., "payments.fee").
            type: Target type (str, int, float, bool, timedelta). Defaults to str.
            nullable: If True, return None for null/unset values instead of raising.

        Returns:
            The config value, converted to the requested type.

        Raises:
            NotFoundError: If the field has no value (and nullable is False).
            TypeMismatchError: If the value cannot be converted to the requested type.
        """
        target_type = type or str

        async def _call() -> object:
            resp = await self._stub.GetField(
                self._pb2.GetFieldRequest(tenant_id=tenant_id, field_path=field_path),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
            return process_get_response(resp, target_type, field_path, tenant_id, nullable)

        try:
            return await async_with_retry(self._retry, _call)
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    async def get_all(self, tenant_id: str) -> dict[str, str]:
        """Get all config values for a tenant as a string dict."""

        async def _call() -> dict[str, str]:
            resp = await self._stub.GetConfig(
                self._pb2.GetConfigRequest(tenant_id=tenant_id),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
            return process_get_all_response(resp)

        try:
            return await async_with_retry(self._retry, _call)
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    async def set(self, tenant_id: str, field_path: str, value: str) -> None:
        """Set a config value.

        The value is sent as a string — the server coerces it to the
        schema-defined type (integer, bool, etc.).
        """

        async def _call() -> None:
            await self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                    value=make_string_typed_value(value),
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )

        try:
            await async_with_retry(self._retry, _call)
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    async def set_many(
        self,
        tenant_id: str,
        values: dict[str, str],
        *,
        description: str = "",
    ) -> None:
        """Atomically set multiple config values."""

        async def _call() -> None:
            updates = [
                self._pb2.FieldUpdate(
                    field_path=fp,
                    value=make_string_typed_value(v),
                )
                for fp, v in values.items()
            ]
            await self._stub.SetFields(
                self._pb2.SetFieldsRequest(
                    tenant_id=tenant_id,
                    updates=updates,
                    description=description,
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )

        try:
            await async_with_retry(self._retry, _call)
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    async def set_null(self, tenant_id: str, field_path: str) -> None:
        """Set a config field to null."""

        async def _call() -> None:
            await self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                    # No value field → server interprets as null.
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )

        try:
            await async_with_retry(self._retry, _call)
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    def watch(self, tenant_id: str) -> _AsyncWatcherContext:
        """Create an async config watcher for a tenant.

        Use as an async context manager::

            async with client.watch("tenant-id") as watcher:
                fee = watcher.field("payments.fee", float, default=0.01)
                print(fee.value)

        Auto-starts on enter, auto-stops on exit.
        """
        return _AsyncWatcherContext(self, tenant_id)


class _AsyncWatcherContext:
    """Async watcher context manager — placeholder for Phase 5."""

    def __init__(self, client: AsyncConfigClient, tenant_id: str) -> None:
        self._client = client
        self._tenant_id = tenant_id

    async def __aenter__(self) -> _AsyncWatcherContext:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass
