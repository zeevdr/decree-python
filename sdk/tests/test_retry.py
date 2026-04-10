"""Tests for retry logic."""

from unittest.mock import MagicMock, patch

import grpc
import pytest

from opendecree._retry import RetryConfig, with_retry
from tests.conftest import FakeRpcError


def test_no_retry_config():
    """When config is None, just call the function once."""
    fn = MagicMock(return_value=42)
    assert with_retry(None, fn) == 42
    fn.assert_called_once()


def test_success_first_try():
    fn = MagicMock(return_value="ok")
    result = with_retry(RetryConfig(max_attempts=3), fn)
    assert result == "ok"
    fn.assert_called_once()


def test_retry_on_unavailable():
    err = FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    fn = MagicMock(side_effect=[err, err, "ok"])

    with patch("opendecree._retry.time.sleep"):
        result = with_retry(RetryConfig(max_attempts=3), fn)

    assert result == "ok"
    assert fn.call_count == 3


def test_no_retry_on_not_found():
    err = FakeRpcError(grpc.StatusCode.NOT_FOUND)
    fn = MagicMock(side_effect=err)

    with pytest.raises(grpc.RpcError):
        with_retry(RetryConfig(max_attempts=3), fn)

    fn.assert_called_once()


def test_exhausted_retries():
    err = FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    fn = MagicMock(side_effect=err)

    with patch("opendecree._retry.time.sleep"):
        with pytest.raises(grpc.RpcError):
            with_retry(RetryConfig(max_attempts=2), fn)

    assert fn.call_count == 2


def test_retry_config_defaults():
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert cfg.initial_backoff == 0.1
    assert cfg.max_backoff == 5.0
    assert cfg.multiplier == 2.0
    assert grpc.StatusCode.UNAVAILABLE in cfg.retryable_codes
    assert grpc.StatusCode.DEADLINE_EXCEEDED in cfg.retryable_codes
