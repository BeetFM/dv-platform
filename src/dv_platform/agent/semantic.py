"""Compatibility facade for deterministic semantic mappings."""

import sys

from dv_platform.verification.protocols import semantic as _implementation
from dv_platform.verification.protocols.semantic import *  # noqa: F403

sys.modules[__name__] = _implementation
