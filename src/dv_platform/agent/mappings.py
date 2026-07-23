"""Compatibility facade for deterministic check mappings."""

import sys

from dv_platform.verification import mappings as _implementation
from dv_platform.verification.mappings import *  # noqa: F403

sys.modules[__name__] = _implementation
