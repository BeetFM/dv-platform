"""Compatibility facade for peripheral domain contracts."""

import sys

from dv_platform.domain import peripherals as _implementation
from dv_platform.domain.peripherals import *  # noqa: F403

sys.modules[__name__] = _implementation
