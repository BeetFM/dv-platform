"""Compatibility facade for configuration parameter matrices."""

import sys

from dv_platform.configuration import parameters as _implementation
from dv_platform.configuration.parameters import *  # noqa: F403

for _name, _value in vars(_implementation).items():
    if not _name.startswith("__"):
        globals()[_name] = _value
del _implementation, _name, _value, sys
