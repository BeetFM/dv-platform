"""Helpers for validating verification-depth policy scalar parameters."""

from __future__ import annotations

from dv_platform.configuration.shared import ConfigDiagnostic
from dv_platform.domain.models import VerificationDepthPolicy


def validate_cdc_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    structures = {None, "two_flop", "pulse", "toggle", "gray", "handshake", "multi_bit_handshake", "async_fifo"}
    if parameters.get("structure") not in structures:
        diagnostics.append(ConfigDiagnostic("error", f"Invalid CDC structure for {policy.module}/{policy.subject}."))
    for name, minimum, maximum in (
        ("min_stages", 2, 16),
        ("max_latency_cycles", 1, 1024),
        ("pulse_stretch_cycles", 1, 1024),
        ("max_source_steps_per_destination", 1, 1),
    ):
        validate_bounded_integer(parameters, name, minimum, maximum, policy, diagnostics)
    validate_boolean(parameters, "reset_compatible", policy, diagnostics)
    validate_boolean(parameters, "first_word_fall_through", policy, diagnostics)


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
