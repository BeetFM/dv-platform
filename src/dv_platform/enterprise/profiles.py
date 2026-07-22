"""Named enterprise EDA capability profiles.

Profiles identify connection requirements and evidence formats. Commands remain
deployment configuration because vendor switches vary by release and site policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from shutil import which


@dataclass(frozen=True)
class EnterpriseToolProfile:
    name: str
    display_name: str
    families: tuple[str, ...]
    executables: tuple[str, ...]
    languages: tuple[str, ...]
    capabilities: tuple[str, ...]
    interchange_formats: tuple[str, ...]
    license_environment: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnterpriseToolAvailability:
    profile: EnterpriseToolProfile
    executable: str | None
    license_environment_present: bool

    @property
    def available(self) -> bool:
        return self.executable is not None and self.license_environment_present


ENTERPRISE_TOOL_PROFILES = (
    EnterpriseToolProfile(
        "questa",
        "Siemens Questa",
        ("simulator", "coverage"),
        ("vsim", "qrun"),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("simulation", "uvm", "assertions", "code_coverage", "functional_coverage"),
        ("ucis_xml", "junit_xml", "semantic_manifest"),
        ("MGLS_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "vcs",
        "Synopsys VCS",
        ("simulator", "coverage"),
        ("vcs", "simv"),
        ("systemverilog", "verilog"),
        ("simulation", "uvm", "assertions", "code_coverage", "functional_coverage"),
        ("ucis_xml", "junit_xml", "semantic_manifest"),
        ("SNPSLMD_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "xcelium",
        "Cadence Xcelium",
        ("simulator", "coverage"),
        ("xrun",),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("simulation", "uvm", "assertions", "code_coverage", "functional_coverage"),
        ("ucis_xml", "junit_xml", "semantic_manifest"),
        ("CDS_LIC_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "riviera_pro",
        "Aldec Riviera-PRO",
        ("simulator", "coverage"),
        ("vsimsa",),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("simulation", "uvm", "assertions", "code_coverage", "functional_coverage"),
        ("ucis_xml", "junit_xml", "semantic_manifest"),
        ("ALDEC_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "vivado_xsim",
        "AMD Vivado Simulator",
        ("simulator", "coverage"),
        ("xsim", "vivado"),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("simulation", "uvm", "assertions", "code_coverage", "functional_coverage"),
        ("coverage_database", "semantic_manifest"),
    ),
    EnterpriseToolProfile(
        "jaspergold",
        "Cadence JasperGold",
        ("formal",),
        ("jg", "jaspergold"),
        ("systemverilog", "verilog"),
        ("property_proving", "cover", "formal_coverage", "apps"),
        ("enterprise_result_json", "semantic_manifest"),
        ("CDS_LIC_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "vc_formal",
        "Synopsys VC Formal",
        ("formal",),
        ("vcf", "vc_formal"),
        ("systemverilog", "verilog"),
        ("property_proving", "cover", "formal_coverage", "apps"),
        ("enterprise_result_json", "semantic_manifest"),
        ("SNPSLMD_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "questa_formal",
        "Siemens Questa Formal",
        ("formal",),
        ("qverify",),
        ("systemverilog", "verilog", "vhdl"),
        ("property_proving", "cover", "formal_coverage", "apps"),
        ("enterprise_result_json", "semantic_manifest"),
        ("MGLS_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "spyglass",
        "Synopsys VC SpyGlass",
        ("analyzer", "cdc", "rdc"),
        ("spyglass",),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("lint", "semantic_analysis", "cdc", "rdc", "constraints"),
        ("semantic_manifest", "sarif"),
        ("SNPSLMD_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
    EnterpriseToolProfile(
        "alint_pro",
        "Aldec ALINT-PRO",
        ("analyzer", "cdc", "rdc"),
        ("alint",),
        ("systemverilog", "verilog", "vhdl", "mixed"),
        ("lint", "semantic_analysis", "cdc", "rdc", "constraints"),
        ("semantic_manifest", "sarif"),
        ("ALDEC_LICENSE_FILE", "LM_LICENSE_FILE"),
    ),
)


def enterprise_profile(name: str) -> EnterpriseToolProfile:
    normalized = name.strip().lower()
    for profile in ENTERPRISE_TOOL_PROFILES:
        if profile.name == normalized:
            return profile
    raise LookupError(f"unknown enterprise tool profile: {name}")


def detect_enterprise_tools() -> tuple[EnterpriseToolAvailability, ...]:
    detected: list[EnterpriseToolAvailability] = []
    for profile in ENTERPRISE_TOOL_PROFILES:
        executable = next((path for command in profile.executables if (path := which(command))), None)
        license_present = not profile.license_environment or any(
            os.environ.get(name, "").strip() for name in profile.license_environment
        )
        detected.append(EnterpriseToolAvailability(profile, executable, license_present))
    return tuple(detected)
