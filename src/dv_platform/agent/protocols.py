"""Compatibility facade for deterministic protocol profiles."""

import sys

from dv_platform.verification import profiles as _implementation
from dv_platform.verification.profiles import *  # noqa: F403

sys.modules[__name__] = _implementation
