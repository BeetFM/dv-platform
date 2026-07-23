"""Compatibility facade for protocol transaction models."""

import sys

from dv_platform.verification import transactions as _implementation
from dv_platform.verification.transactions import *  # noqa: F403

sys.modules[__name__] = _implementation
