"""OpenDecree Python SDK — schema-driven configuration management."""

__version__ = "0.1.0"

SUPPORTED_SERVER_VERSION = ">=0.3.0,<1.0.0"
PROTO_VERSION = "v1"

from opendecree.async_client import AsyncConfigClient
from opendecree.client import ConfigClient
from opendecree.errors import (
    AlreadyExistsError,
    ChecksumMismatchError,
    DecreeError,
    IncompatibleServerError,
    InvalidArgumentError,
    LockedError,
    NotFoundError,
    PermissionDeniedError,
    TypeMismatchError,
    UnavailableError,
)
from opendecree.types import Change, ConfigValue, ServerVersion

__all__ = [
    "PROTO_VERSION",
    "SUPPORTED_SERVER_VERSION",
    "AlreadyExistsError",
    "AsyncConfigClient",
    "Change",
    "ChecksumMismatchError",
    "ConfigClient",
    "ConfigValue",
    "DecreeError",
    "IncompatibleServerError",
    "InvalidArgumentError",
    "LockedError",
    "NotFoundError",
    "PermissionDeniedError",
    "ServerVersion",
    "TypeMismatchError",
    "UnavailableError",
    "__version__",
]
