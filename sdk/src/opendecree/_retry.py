"""Retry logic with exponential backoff and jitter."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

import grpc

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_backoff: float = 0.1  # seconds
    max_backoff: float = 5.0  # seconds
    multiplier: float = 2.0
    retryable_codes: tuple[grpc.StatusCode, ...] = field(
        default=(
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        )
    )


def with_retry(config: RetryConfig | None, fn: Callable[[], T]) -> T:
    """Execute fn with retry on transient gRPC errors."""
    if config is None:
        return fn()

    last_err: Exception | None = None
    backoff = config.initial_backoff

    for attempt in range(config.max_attempts):
        try:
            return fn()
        except grpc.RpcError as e:
            code = e.code()  # type: ignore[union-attr]
            if code not in config.retryable_codes or attempt == config.max_attempts - 1:
                raise
            last_err = e
            jitter = random.uniform(0.5, 1.5)
            time.sleep(backoff * jitter)
            backoff = min(backoff * config.multiplier, config.max_backoff)

    # Should not reach here, but satisfy type checker.
    raise last_err  # type: ignore[misc]
