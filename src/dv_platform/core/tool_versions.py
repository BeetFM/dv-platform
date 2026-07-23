"""Compatibility facade for infrastructure tool-version policy."""

import sys

from dv_platform.infrastructure import tool_versions as _implementation
from dv_platform.infrastructure.tool_versions import *  # noqa: F403

sys.modules[__name__] = _implementation
