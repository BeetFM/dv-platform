"""One-major lazy compatibility namespace for the private Enterprise package."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from dv_platform.product import CapabilityDeniedError, active_product_plan, require_capability

_plan = active_product_plan()
if _plan is None:
    raise CapabilityDeniedError("cli.enterprise", "Enterprise product plan has not been activated")
require_capability(_plan, "cli.enterprise")
_implementation = find_spec("dv_platform_enterprise_impl")
if _implementation is None or not _implementation.submodule_search_locations:
    raise CapabilityDeniedError("cli.enterprise", "dv-platform-enterprise is not installed")
__path__ = list(_implementation.submodule_search_locations)


def __getattr__(name: str) -> Any:
    raise AttributeError(name)
