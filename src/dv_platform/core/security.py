"""Compatibility facade for infrastructure security policy."""

import sys

from dv_platform.infrastructure import security as _implementation
from dv_platform.infrastructure.security import *  # noqa: F403

sys.modules[__name__] = _implementation
