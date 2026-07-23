"""Compatibility facade for domain validation records."""

import sys

from dv_platform.domain import validation as _implementation
from dv_platform.domain.validation import *  # noqa: F403

sys.modules[__name__] = _implementation
