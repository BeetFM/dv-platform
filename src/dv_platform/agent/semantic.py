"""Compatibility facade for deterministic semantic mappings."""

import sys

from dv_platform.verification import semantic as _implementation
from dv_platform.verification.semantic import *  # noqa: F403

sys.modules[__name__] = _implementation
