"""Asynchronous ConfigClient for OpenDecree."""

from __future__ import annotations

from datetime import timedelta
from typing import overload

import grpc
import grpc.aio

from opendecree._channel import create_aio_channel
from opendecree._convert import convert_value, typed_value_to_string
from opendecree._interceptors import _build_metadata
from opendecree._retry import RetryConfig
from opendecree.errors import NotFoundError, map_grpc_error


def _ensure_stubs() -> tuple:  # type: ignore[type-arg]
    """Lazy-load generated stubs on first use."""
    from opendecree._generated.centralconfig.v1 import (
        config_service_pb2 as cs_pb2,
    )
    from opendecree._generated.centralconfig.v1 import (
        config_service_pb2_grpc as cs_grpc,
    )

    return cs_pb2, cs_grpc


class AsyncConfigClient:
    """Asynchronous client for reading and writing OpenDecree configuration values.

    Use as an async context manager::

        async with AsyncConfigClient("localhost:9090", subject="myapp") as client:
            val = await client.get("tenant-id", "payments.fee")
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

        cs_pb2, cs_grpc = _ensure_stubs()
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
        """Get a config value, optionally converting to a specific type."""
        target_type = type or str
        try:
            resp = await self._stub.GetField(
                self._pb2.GetFieldRequest(tenant_id=tenant_id, field_path=field_path),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

        if not resp.value.HasField("value"):
            if nullable:
                return None
            raise NotFoundError(f"field {field_path!r} has no value for tenant {tenant_id!r}")
        raw = typed_value_to_string(resp.value.value)
        return convert_value(raw, target_type)

    async def get_all(self, tenant_id: str) -> dict[str, str]:
        """Get all config values for a tenant as a string dict."""
        try:
            resp = await self._stub.GetConfig(
                self._pb2.GetConfigRequest(tenant_id=tenant_id),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

        result: dict[str, str] = {}
        for cv in resp.config.values:
            if cv.HasField("value"):
                result[cv.field_path] = typed_value_to_string(cv.value)
        return result

    async def set(self, tenant_id: str, field_path: str, value: str) -> None:
        """Set a config value (as string)."""
        try:
            await self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                    value=self._make_string_value(value),
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
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
        updates = [
            self._pb2.FieldUpdate(
                field_path=fp,
                value=self._make_string_value(v),
            )
            for fp, v in values.items()
        ]
        try:
            await self._stub.SetFields(
                self._pb2.SetFieldsRequest(
                    tenant_id=tenant_id,
                    updates=updates,
                    description=description or None,
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    async def set_null(self, tenant_id: str, field_path: str) -> None:
        """Set a config field to null."""
        try:
            await self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                ),
                timeout=self._timeout,
                metadata=self._metadata(),
            )
        except grpc.aio.AioRpcError as e:
            raise map_grpc_error(e) from e

    def _make_string_value(self, value: str) -> object:
        """Create a TypedValue with string_value set."""
        from opendecree._generated.centralconfig.v1 import types_pb2

        return types_pb2.TypedValue(string_value=value)

    def watch(self, tenant_id: str) -> _AsyncWatcherContext:
        """Create an async config watcher for a tenant.

        Use as an async context manager::

            async with client.watch("tenant-id") as watcher:
                fee = watcher.field("payments.fee", float, default=0.01)
                print(fee.value)
        """
        return _AsyncWatcherContext(self, tenant_id)


class _AsyncWatcherContext:
    """Placeholder for the async watcher context manager (Phase 5)."""

    def __init__(self, client: AsyncConfigClient, tenant_id: str) -> None:
        self._client = client
        self._tenant_id = tenant_id

    async def __aenter__(self) -> _AsyncWatcherContext:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass
