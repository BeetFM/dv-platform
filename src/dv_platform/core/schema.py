"""Compatibility facade for domain schema versions."""

import sys

from dv_platform.domain import schema as _implementation
from dv_platform.domain.schema import *  # noqa: F403

sys.modules[__name__] = _implementation
