# ruff: noqa: E402,F401,I001
"""Composition root for focused enterprise qualification subsystems."""

from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from importlib import resources
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RTLClock,
    RTLPort,
    RTLProtocol,
    RTLReset,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.enterprise.adapters import EnterpriseAdapterError, _load_result
from dv_platform.enterprise.profiles import EnterpriseToolProfile, enterprise_profile
from dv_platform.generators.uvm import UvmGenerator

QUALIFICATION_SCHEMA_VERSION = 1
QUALIFICATION_POLICY_SCHEMA_VERSION = 1
QUALIFICATION_ATTESTATION_SCHEMA_VERSION = 1
QUALIFICATION_REQUEST_SCHEMA_VERSION = 1
MAX_QUALIFICATION_BYTES = 32 * 1024 * 1024
MAX_PROBE_OUTPUT_BYTES = 1024 * 1024
MAX_PROBE_TIMEOUT_SECONDS = 1800.0
QUALIFICATION_LEVELS = (
    "unverified",
    "contract_verified",
    "surrogate_verified",
    "vendor_verified",
    "independently_signed",
)
_LEVEL_RANK = {level: index for index, level in enumerate(QUALIFICATION_LEVELS)}
_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_FAMILY_FIXTURES = {
    "simulator": "contract-simulator.json",
    "formal": "contract-formal.json",
    "analyzer": "contract-analyzer.json",
}
_FAMILY_CHECKS = {
    "simulator": "QUAL-SIM-001",
    "formal": "QUAL-FORMAL-001",
    "analyzer": "QUAL-ANALYZER-001",
}
_GENERATED_UVM_CHECK = "QUAL-UVM-001"
_FAMILY_SOURCE_FIXTURES = {
    "simulator": ("surrogate.sv", "surrogate.vhd"),
    "formal": ("formal.sv", "surrogate.sby"),
    "analyzer": ("surrogate.sv", "surrogate.vhd"),
}

from dv_platform.enterprise.qualification import runs as _part_0
from dv_platform.enterprise.qualification import bundles as _part_1
from dv_platform.enterprise.qualification import policy as _part_2
from dv_platform.enterprise.qualification import records as _part_3
from dv_platform.enterprise.qualification import assets as _part_4
from dv_platform.enterprise.qualification.runs import (
    QualificationError,
    QualificationCheck,
    QualifiedTool,
    QualificationRecord,
    SurrogateProbe,
    qualify_contract,
    qualify_surrogate,
)
from dv_platform.enterprise.qualification.bundles import (
    create_vendor_qualification_bundle,
    import_vendor_attestation,
    set_qualification_policy,
)
from dv_platform.enterprise.qualification.policy import qualification_status, _execute_probe
from dv_platform.enterprise.qualification.records import (
    _persist_record,
    _validate_record,
    _validate_policy,
    _validate_request,
)
from dv_platform.enterprise.qualification.assets import (
    _required_families,
    _asset_bytes,
    _generated_uvm_fixture_bytes,
    _schema_bytes,
    _bundle_readme,
    _record_path,
    _policy_path,
    _default_policy,
    _read_json,
    _profile_name,
    _validate_level,
    _timezone_timestamp,
    _object,
    _string,
    _string_list,
    _string_mapping,
    _canonical_json,
    _payload_sha256,
    _utc_now,
)

SURROGATE_PROBES = (
    SurrogateProbe(
        "verilator_lint",
        "analyzer",
        ("systemverilog", "verilog"),
        ("verilator",),
        ("--version",),
        (("verilator", "--lint-only", "-Wall", "-Wno-fatal", "--top-module", "dv_qualification", "surrogate.sv"),),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "verilator_simulator",
        "simulator",
        ("systemverilog", "verilog"),
        ("verilator",),
        ("--version",),
        (
            (
                "verilator",
                "--binary",
                "--timing",
                "-Wno-fatal",
                "--top-module",
                "dv_qualification",
                "--Mdir",
                "obj_dir",
                "surrogate.sv",
            ),
            ("{work}/obj_dir/Vdv_qualification",),
        ),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "iverilog",
        "simulator",
        ("systemverilog", "verilog"),
        ("iverilog", "vvp"),
        ("-V",),
        (
            ("iverilog", "-g2012", "-s", "dv_qualification", "-o", "{work}/qualification.vvp", "surrogate.sv"),
            ("vvp", "{work}/qualification.vvp"),
        ),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "ghdl",
        "simulator",
        ("vhdl",),
        ("ghdl",),
        ("--version",),
        (
            ("ghdl", "-a", "--std=08", "surrogate.vhd"),
            ("ghdl", "-e", "--std=08", "dv_qualification"),
            ("ghdl", "-r", "--std=08", "dv_qualification", "--assert-level=error"),
        ),
        ("surrogate.vhd",),
    ),
    SurrogateProbe(
        "yosys",
        "formal",
        ("systemverilog", "verilog"),
        ("yosys",),
        ("-V",),
        (
            (
                "yosys",
                "-p",
                "read_verilog -formal -sv formal.sv; prep -top dv_formal; sat -verify -prove-asserts -seq 4",
            ),
        ),
        ("formal.sv",),
    ),
    SurrogateProbe(
        "symbiyosys",
        "formal",
        ("systemverilog", "verilog"),
        ("sby",),
        ("--version",),
        (("sby", "-f", "surrogate.sby"),),
        ("formal.sv", "surrogate.sby"),
    ),
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _legacy_class in (
    QualificationError,
    QualificationCheck,
    QualifiedTool,
    QualificationRecord,
    SurrogateProbe,
):
    _legacy_class.__module__ = "dv_platform.enterprise.qualification"
del _part_0, _part_1, _part_2, _part_3, _part_4, _legacy_class, _namespace, _part, _parts
