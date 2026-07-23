"""Compatibility facade for governed infrastructure operations."""

import sys

from dv_platform.infrastructure import operations as _implementation
from dv_platform.infrastructure.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
