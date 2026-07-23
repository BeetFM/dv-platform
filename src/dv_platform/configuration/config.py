"""Compatibility-complete configuration composition surface."""

from __future__ import annotations

from dv_platform.configuration import loading as _loading
from dv_platform.configuration import serialization as _serialization
from dv_platform.configuration import shared as _shared
from dv_platform.configuration import validation as _validation
from dv_platform.configuration.loading import *  # noqa: F403
from dv_platform.configuration.serialization import *  # noqa: F403
from dv_platform.configuration.shared import *  # noqa: F403
from dv_platform.configuration.validation import *  # noqa: F403

for _module in (_shared, _loading, _validation, _serialization):
    for _name, _value in vars(_module).items():
        if not _name.startswith("__"):
            globals().setdefault(_name, _value)
del _loading, _module, _name, _serialization, _shared, _validation, _value
