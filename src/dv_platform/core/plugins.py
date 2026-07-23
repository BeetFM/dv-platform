"""Compatibility facade for infrastructure plugin loading."""

import sys

from dv_platform.infrastructure import plugins as _implementation
from dv_platform.infrastructure.plugins import *  # noqa: F403

sys.modules[__name__] = _implementation
