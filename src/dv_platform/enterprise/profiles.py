"""Named enterprise EDA capability profiles.

Profiles identify connection requirements and evidence formats. Commands remain
deployment configuration because flow scripts vary by release and site policy.
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
        "openroad",
        "OpenROAD",
        ("analyzer",),
        ("openroad",),
        ("verilog", "systemverilog"),
        ("physical_design", "timing", "power", "memory"),
        ("enterprise_result_json", "physical_evidence_json"),
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
