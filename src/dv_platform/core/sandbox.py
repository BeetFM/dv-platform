"""Compatibility facade for infrastructure sandbox policy."""

import sys

from dv_platform.infrastructure import sandbox as _implementation
from dv_platform.infrastructure.sandbox import *  # noqa: F403

sys.modules[__name__] = _implementation
