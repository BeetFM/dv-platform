"""Compatibility facade for verification claim policy."""

import sys
from typing import Any

from dv_platform.verification.planning import claims as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
