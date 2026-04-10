"""Type conversion between proto TypedValue strings and Python native types."""

from __future__ import annotations

from datetime import timedelta

from opendecree.errors import TypeMismatchError

# Map of supported Python types to their conversion functions.
_CONVERTERS: dict[type, tuple[str, object]] = {}


def _parse_timedelta(s: str) -> timedelta:
    """Parse a Go-style duration string (e.g., '24h', '30m', '500ms') to timedelta."""
    if not s:
        return timedelta()

    total_seconds = 0.0
    i = 0
    while i < len(s):
        # Parse number.
        start = i
        while i < len(s) and (s[i].isdigit() or s[i] == "."):
            i += 1
        if start == i:
            raise ValueError(f"invalid duration: {s!r}")
        num = float(s[start:i])

        # Parse unit.
        unit_start = i
        while i < len(s) and s[i].isalpha():
            i += 1
        unit = s[unit_start:i]

        if unit == "h":
            total_seconds += num * 3600
        elif unit == "m":
            total_seconds += num * 60
        elif unit == "s":
            total_seconds += num
        elif unit == "ms":
            total_seconds += num / 1000
        elif unit == "us" or unit == "\u00b5s":
            total_seconds += num / 1_000_000
        elif unit == "ns":
            total_seconds += num / 1_000_000_000
        else:
            raise ValueError(f"unknown duration unit: {unit!r} in {s!r}")

    return timedelta(seconds=total_seconds)


def convert_value(raw: str, target_type: type) -> object:
    """Convert a raw string value to the target Python type.

    Raises TypeMismatchError if conversion fails.
    """
    if target_type is str:
        return raw
    try:
        if target_type is int:
            return int(raw)
        if target_type is float:
            return float(raw)
        if target_type is bool:
            if raw.lower() in ("true", "1"):
                return True
            if raw.lower() in ("false", "0"):
                return False
            raise ValueError(f"cannot convert {raw!r} to bool")
        if target_type is timedelta:
            return _parse_timedelta(raw)
    except (ValueError, OverflowError) as e:
        raise TypeMismatchError(f"cannot convert {raw!r} to {target_type.__name__}: {e}") from e

    raise TypeMismatchError(f"unsupported type: {target_type.__name__}")


def typed_value_to_string(tv: object) -> str:
    """Extract the string representation from a proto TypedValue.

    The TypedValue is a oneof with fields like integer_value, string_value, etc.
    We find whichever field is set and convert it to string.
    """
    # Import here to avoid circular dependency with generated code.
    from opendecree._generated.centralconfig.v1 import types_pb2

    if not isinstance(tv, types_pb2.TypedValue):
        return str(tv)

    kind = tv.WhichOneof("kind")
    if kind is None:
        return ""

    val = getattr(tv, kind)

    # Handle special protobuf types.
    if kind == "time_value":
        return val.ToJsonString()
    if kind == "duration_value":
        # Convert protobuf Duration to Go-style string.
        total = val.seconds + val.nanos / 1e9
        if total >= 3600 and total % 3600 == 0:
            return f"{int(total // 3600)}h"
        if total >= 60 and total % 60 == 0:
            return f"{int(total // 60)}m"
        if total == int(total):
            return f"{int(total)}s"
        return f"{total}s"

    return str(val)
