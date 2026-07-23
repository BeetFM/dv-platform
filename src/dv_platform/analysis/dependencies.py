"""Compatibility facade for verification dependency selection."""

import sys
from typing import Any

from dv_platform.verification.protocols import dependencies as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
