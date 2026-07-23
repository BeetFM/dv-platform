"""Compatibility facade for formal collateral generation."""

import sys
from typing import Any

from dv_platform.formal import generation as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
