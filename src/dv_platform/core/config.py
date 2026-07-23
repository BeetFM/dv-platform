"""Compatibility facade for configuration behavior."""

import sys

from dv_platform.configuration import config as _implementation
from dv_platform.configuration.config import *  # noqa: F403

sys.modules[__name__] = _implementation
