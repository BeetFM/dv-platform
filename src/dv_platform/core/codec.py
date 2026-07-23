"""Compatibility facade for canonical infrastructure codecs."""

import sys

from dv_platform.infrastructure import codec as _implementation
from dv_platform.infrastructure.codec import *  # noqa: F403

sys.modules[__name__] = _implementation
