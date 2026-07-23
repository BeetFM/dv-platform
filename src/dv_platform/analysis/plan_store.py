"""Compatibility facade for verification plan persistence and codecs."""

import sys
from typing import Any

from dv_platform.verification import storage as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
