# ruff: noqa: E402,F401,I001
"""Composition root for focused verification depth policy."""

from __future__ import annotations

import math

from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    Severity,
    VerificationClaim,
    VerificationDepthPolicy,
)
from dv_platform.core.peripherals import PERIPHERAL_CONTRACTS

from dv_platform.verification.depth import checks as _part_0
from dv_platform.verification.depth import peripheral as _part_1
from dv_platform.verification.depth.checks import (
    build_depth_checks,
    validate_depth_policies,
    _validate_peripheral_policy,
    _peripheral_signal_width,
    _validate_formal_policy,
    _validate_memory_policy,
    _cyclic_reset_subjects,
)
from dv_platform.verification.depth.peripheral import (
    _validate_reset_policy,
    _validate_cdc_policy,
    _validate_async_fifo_policy,
)

_parts = (
    _part_0,
    _part_1,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
del _part_0, _part_1, _namespace, _part, _parts
__name__ = "dv_platform.analysis.depth"
