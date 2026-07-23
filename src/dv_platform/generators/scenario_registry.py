"""Compatibility facade for scenario target-support contracts."""

import sys
from typing import Any

from dv_platform.verification import target_support as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
