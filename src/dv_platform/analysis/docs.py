"""Compatibility facade for document indexing and retrieval."""

import sys

from dv_platform.documentation import indexing as _implementation
from dv_platform.documentation.indexing import *  # noqa: F403

sys.modules[__name__] = _implementation
