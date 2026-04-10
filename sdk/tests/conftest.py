"""Shared test fixtures and helpers."""

from __future__ import annotations

import grpc


class FakeRpcError(grpc.RpcError):
    """A concrete RpcError for testing."""

    def __init__(self, code: grpc.StatusCode, details: str = "test") -> None:
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details
