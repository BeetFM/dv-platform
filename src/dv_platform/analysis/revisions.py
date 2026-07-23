"""Compatibility facade for verification plan revisions."""

import sys
from typing import Any

from dv_platform.verification.planning import revisions as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
