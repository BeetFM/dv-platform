"""Compatibility facade for domain literal parsing."""

import sys

from dv_platform.domain import literals as _implementation
from dv_platform.domain.literals import *  # noqa: F403

sys.modules[__name__] = _implementation
