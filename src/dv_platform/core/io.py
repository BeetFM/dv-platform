"""Compatibility facade for infrastructure I/O."""

import sys

from dv_platform.infrastructure import io as _implementation
from dv_platform.infrastructure.io import *  # noqa: F403

sys.modules[__name__] = _implementation
