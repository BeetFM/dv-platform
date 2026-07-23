"""Compatibility facade for AI agent contracts."""

import sys
from typing import Any

from dv_platform.ai import contracts as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
