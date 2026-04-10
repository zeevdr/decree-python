"""Tests for type conversion."""

from datetime import timedelta

import pytest

from opendecree._convert import _parse_timedelta, convert_value
from opendecree.errors import TypeMismatchError


def test_convert_str():
    assert convert_value("hello", str) == "hello"


def test_convert_int():
    assert convert_value("42", int) == 42


def test_convert_int_negative():
    assert convert_value("-1", int) == -1


def test_convert_int_invalid():
    with pytest.raises(TypeMismatchError, match="cannot convert"):
        convert_value("not-a-number", int)


def test_convert_float():
    assert convert_value("3.14", float) == pytest.approx(3.14)


def test_convert_float_invalid():
    with pytest.raises(TypeMismatchError, match="cannot convert"):
        convert_value("abc", float)


def test_convert_bool_true():
    assert convert_value("true", bool) is True
    assert convert_value("True", bool) is True
    assert convert_value("1", bool) is True


def test_convert_bool_false():
    assert convert_value("false", bool) is False
    assert convert_value("False", bool) is False
    assert convert_value("0", bool) is False


def test_convert_bool_invalid():
    with pytest.raises(TypeMismatchError, match="cannot convert"):
        convert_value("maybe", bool)


def test_convert_timedelta_hours():
    assert convert_value("24h", timedelta) == timedelta(hours=24)


def test_convert_timedelta_minutes():
    assert convert_value("30m", timedelta) == timedelta(minutes=30)


def test_convert_timedelta_seconds():
    assert convert_value("500s", timedelta) == timedelta(seconds=500)


def test_convert_timedelta_milliseconds():
    assert convert_value("100ms", timedelta) == timedelta(milliseconds=100)


def test_convert_timedelta_compound():
    assert convert_value("1h30m", timedelta) == timedelta(hours=1, minutes=30)


def test_convert_timedelta_invalid():
    with pytest.raises(TypeMismatchError, match="cannot convert"):
        convert_value("not-a-duration", timedelta)


def test_convert_unsupported_type():
    with pytest.raises(TypeMismatchError, match="unsupported type"):
        convert_value("hello", list)  # type: ignore[arg-type]


def test_parse_timedelta_empty():
    assert _parse_timedelta("") == timedelta()


def test_parse_timedelta_microseconds():
    assert _parse_timedelta("500us") == timedelta(microseconds=500)


def test_parse_timedelta_nanoseconds():
    td = _parse_timedelta("1000ns")
    assert td == timedelta(microseconds=1)
