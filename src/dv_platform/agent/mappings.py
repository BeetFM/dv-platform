"""Compatibility facade for deterministic check mappings."""

import sys

from dv_platform.verification.protocols import mappings as _implementation
from dv_platform.verification.protocols.mappings import *  # noqa: F403

sys.modules[__name__] = _implementation
