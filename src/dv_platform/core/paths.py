"""Compatibility facade for infrastructure path policy."""

import sys

from dv_platform.infrastructure import paths as _implementation
from dv_platform.infrastructure.paths import *  # noqa: F403

sys.modules[__name__] = _implementation
