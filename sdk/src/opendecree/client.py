"""Synchronous ConfigClient for OpenDecree."""

from __future__ import annotations

from datetime import timedelta
from typing import overload

import grpc

from opendecree._channel import create_channel
from opendecree._convert import convert_value, typed_value_to_string
from opendecree._interceptors import AuthInterceptor, _build_metadata
from opendecree._retry import RetryConfig, with_retry
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


class ConfigClient:
    """Synchronous client for reading and writing OpenDecree configuration values.

    Use as a context manager for clean channel lifecycle::

        with ConfigClient("localhost:9090", subject="myapp") as client:
            val = client.get("tenant-id", "payments.fee")
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

        metadata = _build_metadata(subject=subject, role=role, tenant_id=tenant_id, token=token)
        interceptors: list[grpc.UnaryUnaryClientInterceptor] = []
        if metadata:
            interceptors.append(AuthInterceptor(metadata))

        channel = create_channel(target, insecure=insecure, credentials=credentials)
        if interceptors:
            self._channel = grpc.intercept_channel(channel, *interceptors)
        else:
            self._channel = channel
        self._raw_channel = channel  # keep ref for close()

        cs_pb2, cs_grpc = _ensure_stubs()
        self._stub = cs_grpc.ConfigServiceStub(self._channel)
        self._pb2 = cs_pb2

    def close(self) -> None:
        """Close the underlying gRPC channel."""
        self._raw_channel.close()

    def __enter__(self) -> ConfigClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- get() with @overload for type safety ---

    @overload
    def get(self, tenant_id: str, field_path: str) -> str: ...

    @overload
    def get(self, tenant_id: str, field_path: str, type: type[int]) -> int: ...

    @overload
    def get(self, tenant_id: str, field_path: str, type: type[float]) -> float: ...

    @overload
    def get(self, tenant_id: str, field_path: str, type: type[bool]) -> bool: ...

    @overload
    def get(self, tenant_id: str, field_path: str, type: type[timedelta]) -> timedelta: ...

    @overload
    def get(
        self,
        tenant_id: str,
        field_path: str,
        type: type[str],
        *,
        nullable: bool,
    ) -> str | None: ...

    def get(
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
            NotFoundError: If the field does not exist (and nullable is False).
            TypeMismatchError: If the value cannot be converted to the requested type.
        """
        target_type = type or str

        def _call() -> object:
            resp = self._stub.GetField(
                self._pb2.GetFieldRequest(tenant_id=tenant_id, field_path=field_path),
                timeout=self._timeout,
            )
            if not resp.value.HasField("value"):
                if nullable:
                    return None
                raise NotFoundError(f"field {field_path!r} has no value for tenant {tenant_id!r}")
            raw = typed_value_to_string(resp.value.value)
            return convert_value(raw, target_type)

        try:
            return with_retry(self._retry, _call)
        except grpc.RpcError as e:
            raise map_grpc_error(e) from e

    def get_all(self, tenant_id: str) -> dict[str, str]:
        """Get all config values for a tenant as a string dict."""

        def _call() -> dict[str, str]:
            resp = self._stub.GetConfig(
                self._pb2.GetConfigRequest(tenant_id=tenant_id),
                timeout=self._timeout,
            )
            result: dict[str, str] = {}
            for cv in resp.config.values:
                if cv.HasField("value"):
                    result[cv.field_path] = typed_value_to_string(cv.value)
            return result

        try:
            return with_retry(self._retry, _call)
        except grpc.RpcError as e:
            raise map_grpc_error(e) from e

    def set(self, tenant_id: str, field_path: str, value: str) -> None:
        """Set a config value (as string)."""

        def _call() -> None:
            self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                    value=self._make_string_value(value),
                ),
                timeout=self._timeout,
            )

        try:
            with_retry(self._retry, _call)
        except grpc.RpcError as e:
            raise map_grpc_error(e) from e

    def set_many(
        self,
        tenant_id: str,
        values: dict[str, str],
        *,
        description: str = "",
    ) -> None:
        """Atomically set multiple config values."""

        def _call() -> None:
            updates = [
                self._pb2.FieldUpdate(
                    field_path=fp,
                    value=self._make_string_value(v),
                )
                for fp, v in values.items()
            ]
            self._stub.SetFields(
                self._pb2.SetFieldsRequest(
                    tenant_id=tenant_id,
                    updates=updates,
                    description=description or None,
                ),
                timeout=self._timeout,
            )

        try:
            with_retry(self._retry, _call)
        except grpc.RpcError as e:
            raise map_grpc_error(e) from e

    def set_null(self, tenant_id: str, field_path: str) -> None:
        """Set a config field to null."""

        def _call() -> None:
            # Send SetField with no value (null).
            self._stub.SetField(
                self._pb2.SetFieldRequest(
                    tenant_id=tenant_id,
                    field_path=field_path,
                ),
                timeout=self._timeout,
            )

        try:
            with_retry(self._retry, _call)
        except grpc.RpcError as e:
            raise map_grpc_error(e) from e

    def _make_string_value(self, value: str) -> object:
        """Create a TypedValue with string_value set."""
        from opendecree._generated.centralconfig.v1 import types_pb2

        return types_pb2.TypedValue(string_value=value)

    def watch(self, tenant_id: str) -> _WatcherContext:
        """Create a config watcher for a tenant.

        Use as a context manager::

            with client.watch("tenant-id") as watcher:
                fee = watcher.field("payments.fee", float, default=0.01)
                print(fee.value)

        The watcher inherits the client's connection and auth settings.
        """
        return _WatcherContext(self, tenant_id)


class _WatcherContext:
    """Placeholder for the watcher context manager (Phase 4)."""

    def __init__(self, client: ConfigClient, tenant_id: str) -> None:
        self._client = client
        self._tenant_id = tenant_id

    def __enter__(self) -> _WatcherContext:
        # Phase 4: start watcher
        return self

    def __exit__(self, *exc: object) -> None:
        # Phase 4: stop watcher
        pass
