"""Helpers for validating verification-depth policy scalar parameters."""

from __future__ import annotations

import re

from dv_platform.configuration.shared import ConfigDiagnostic
from dv_platform.domain.models import VerificationDepthPolicy


def validate_cdc_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    structures = {
        None,
        "two_flop",
        "pulse",
        "toggle",
        "gray",
        "handshake",
        "multi_bit_handshake",
        "async_fifo",
        "two_branch_reconvergent",
    }
    if parameters.get("structure") not in structures:
        diagnostics.append(ConfigDiagnostic("error", f"Invalid CDC structure for {policy.module}/{policy.subject}."))
    for name, minimum, maximum in (
        ("min_stages", 2, 16),
        ("max_latency_cycles", 1, 1024),
        ("pulse_stretch_cycles", 1, 1024),
        ("max_source_steps_per_destination", 1, 1),
        ("branch0_stages", 1, 16),
        ("branch1_stages", 1, 16),
        ("source_stability_cycles", 1, 1024),
        ("source_rate_bound", 1, 1024),
        ("coherent_arrival_bound", 1, 1024),
    ):
        validate_bounded_integer(parameters, name, minimum, maximum, policy, diagnostics)
    validate_boolean(parameters, "reset_compatible", policy, diagnostics)
    validate_boolean(parameters, "first_word_fall_through", policy, diagnostics)


def validate_formal_assumption_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    if parameters.get("assumption") not in {"stability", "range"}:
        diagnostics.append(
            ConfigDiagnostic("error", f"Invalid formal assumption for {policy.module}/{policy.subject}.")
        )
    if parameters.get("engine") != "sby":
        diagnostics.append(
            ConfigDiagnostic("error", f"Invalid formal assumption engine for {policy.module}/{policy.subject}.")
        )
    if parameters.get("reset_active") not in {"high", "low"}:
        diagnostics.append(
            ConfigDiagnostic(
                "error", f"Invalid formal assumption reset activation for {policy.module}/{policy.subject}."
            )
        )
    validate_bounded_integer(parameters, "bound_cycles", 1, 64, policy, diagnostics)
    for name in ("signal", "clock", "reset"):
        if not parameters.get(name, "").strip():
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"Formal assumption {name} must be mapped for {policy.module}/{policy.subject}."
                )
            )
    assumption = parameters.get("assumption")
    if assumption == "range":
        minimum = parameters.get("minimum")
        maximum = parameters.get("maximum")
        if (
            minimum is None
            or maximum is None
            or not minimum.lstrip("-").isdecimal()
            or not maximum.lstrip("-").isdecimal()
            or int(minimum) > int(maximum)
        ):
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid formal assumption range for {policy.module}/{policy.subject}.")
            )
    elif "minimum" in parameters or "maximum" in parameters:
        diagnostics.append(
            ConfigDiagnostic(
                "error", f"Range limits are only valid for range assumptions on {policy.module}/{policy.subject}."
            )
        )


def validate_memory_initialization_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    profile = parameters.get("profile")
    initialization_fields = {"path", "sha256", "default_policy"}
    if profile == "bounded_sram_init_hex":
        path = parameters.get("path", "")
        if not path or path.startswith("/") or "\\" in path or ".." in path.split("/"):
            diagnostics.append(
                ConfigDiagnostic(
                    "error",
                    f"Memory initialization path must be safe and repository-relative for {policy.module}/{policy.subject}.",
                )
            )
        if parameters.get("default_policy") not in {"explicit_zero", "file_complete"}:
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"Invalid memory initialization default policy for {policy.module}/{policy.subject}."
                )
            )
        digest = parameters.get("sha256")
        if digest is not None and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"Invalid memory initialization SHA-256 for {policy.module}/{policy.subject}."
                )
            )
    elif initialization_fields.intersection(parameters):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                f"Memory initialization metadata requires bounded_sram_init_hex for {policy.module}/{policy.subject}.",
            )
        )


def validate_bounded_integer(
    parameters: dict[str, str],
    name: str,
    minimum: int,
    maximum: int,
    policy: VerificationDepthPolicy,
    diagnostics: list[ConfigDiagnostic],
) -> None:
    value = parameters.get(name)
    if value is None:
        return
    if not value.isdecimal() or not minimum <= int(value) <= maximum:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                f"Verification depth {name} must be between {minimum} and {maximum} for {policy.module}/{policy.subject}.",
            )
        )


def validate_boolean(
    parameters: dict[str, str],
    name: str,
    policy: VerificationDepthPolicy,
    diagnostics: list[ConfigDiagnostic],
) -> None:
    if parameters.get(name) not in {None, "true", "false"}:
        diagnostics.append(
            ConfigDiagnostic(
                "error", f"Verification depth {name} must be true or false for {policy.module}/{policy.subject}."
            )
        )
