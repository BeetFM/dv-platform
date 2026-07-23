"""Validate the ordered broad-GA ledger and optionally enforce stage completion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "qualification" / "policies" / "ga-gates-v1.json"
ALLOWED_STATUS = {"pending", "in_progress", "blocked", "complete"}
ALLOWED_PROFILE_STATE = {"pending", "contract_verified", "vendor_verified", "independently_signed", "qualified"}


def _validate_stages(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    stages = document.get("stages")
    if not isinstance(stages, list) or [item.get("stage") for item in stages if isinstance(item, dict)] != list(
        range(6, 14)
    ):
        errors.append("GA stages must be unique and ordered from 6 through 12")
        stages = []
    seen_open = False
    for item in stages:
        if not isinstance(item, dict):
            errors.append("GA stage must be an object")
            continue
        status = item.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"Stage {item.get('stage')} has invalid status: {status}")
        if status != "complete":
            seen_open = True
        elif seen_open:
            errors.append(f"Stage {item.get('stage')} is complete before an earlier stage")
        evidence = item.get("evidence")
        if status == "complete" and (not isinstance(evidence, list) or not evidence):
            errors.append(f"Stage {item.get('stage')} is complete without evidence")
        for relative in evidence if isinstance(evidence, list) else ():
            if not isinstance(relative, str) or not (ROOT / relative).is_file():
                errors.append(f"Stage {item.get('stage')} evidence is missing: {relative}")
    return errors


def _validate_profile_evidence(profile: dict[str, object], identity: object) -> list[str]:
    errors: list[str] = []
    evidence = profile.get("evidence")
    if not isinstance(evidence, list):
        return [f"GA profile {identity} evidence must be an array"]
    if profile.get("state") in {"qualified", "vendor_verified", "independently_signed"} and not evidence:
        errors.append(f"GA profile {identity} is accepted without evidence")
    for relative in evidence:
        if not isinstance(relative, str) or not (ROOT / relative).is_file():
            errors.append(f"GA profile {identity} evidence is missing: {relative}")
            continue
        if relative.startswith("qualification/external-designs/") and relative.endswith(".json"):
            errors.extend(_validate_external_evidence(relative, identity))
    return errors


def _validate_external_evidence(relative: str, identity: object) -> list[str]:
    try:
        from dv_platform.enterprise.external_design import verify_external_design_evidence

        verify_external_design_evidence(ROOT / relative)
    except (OSError, ValueError) as error:
        return [f"GA profile {identity} external evidence is invalid: {error}"]
    return []


def _validate_independent_signature(profile: dict[str, object], identity: object) -> list[str]:
    if profile.get("state") != "independently_signed":
        return []
    signed_fields = ("qualification_profile", "attestation", "signature_manifest", "trust_policy")
    if not all(isinstance(profile.get(field), str) and profile.get(field) for field in signed_fields):
        return [f"GA profile {identity} has incomplete independent-signature evidence"]
    try:
        from dv_platform.core.config import default_config
        from dv_platform.enterprise.qualification import import_vendor_attestation

        with TemporaryDirectory() as directory:
            record = import_vendor_attestation(
                default_config(Path(directory)),
                str(profile["qualification_profile"]),
                ROOT / str(profile["attestation"]),
                signature_manifest=ROOT / str(profile["signature_manifest"]),
                trust_policy=ROOT / str(profile["trust_policy"]),
            )
        if record.get("level") != "independently_signed":
            return [f"GA profile {identity} did not reach independently_signed"]
    except (OSError, ValueError) as error:
        return [f"GA profile {identity} independent signature is invalid: {error}"]
    return []


def _validate_profiles(document: dict[str, object]) -> list[str]:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        return ["GA profiles must be an array"]
    errors: list[str] = []
    identities: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            errors.append("GA profile must be an object")
            continue
        identity = profile.get("profile_id")
        if not isinstance(identity, str) or not identity or identity in identities:
            errors.append(f"GA profile identity is invalid or duplicated: {identity}")
        identities.add(str(identity))
        if profile.get("state") not in ALLOWED_PROFILE_STATE:
            errors.append(f"GA profile {identity} has invalid state: {profile.get('state')}")
        if profile.get("stage") not in range(6, 14):
            errors.append(f"GA profile {identity} has invalid stage")
        if not profile.get("required_targets") or not profile.get("required_evidence"):
            errors.append(f"GA profile {identity} has incomplete requirements")
        errors.extend(_validate_profile_evidence(profile, identity))
        errors.extend(_validate_independent_signature(profile, identity))
    return errors


def validate_ledger(document: object) -> list[str]:
    if not isinstance(document, dict):
        return ["GA ledger root must be an object"]
    errors = []
    if document.get("schema_version") != 1 or document.get("product") != "Veriforge":
        errors.append("GA ledger identity/version is invalid")
    return [*errors, *_validate_stages(document), *_validate_profiles(document)]


def enforce_through(document: dict[str, object], stage: int) -> list[str]:
    errors: list[str] = []
    stages = document.get("stages")
    if not isinstance(stages, list):
        return ["GA stages must be an array"]
    for item in stages:
        if isinstance(item, dict) and int(item.get("stage", 0)) <= stage and item.get("status") != "complete":
            errors.append(f"Stage {item.get('stage')} is not complete: {item.get('status')}")
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        return [*errors, "GA profiles must be an array"]
    for profile in profiles:
        if not isinstance(profile, dict) or int(profile.get("stage", 0)) > stage:
            continue
        expected = "independently_signed" if int(profile["stage"]) == 11 else "qualified"
        if profile.get("state") != expected:
            errors.append(f"Profile {profile.get('profile_id')} is {profile.get('state')}, expected {expected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through-stage", type=int, choices=range(6, 14))
    args = parser.parse_args()
    document = json.loads(LEDGER.read_text(encoding="utf-8"))
    errors = validate_ledger(document)
    if args.through_stage is not None and not errors:
        errors.extend(enforce_through(document, args.through_stage))
    for error in errors:
        print(error)
    if errors:
        return 1
    print("GA gate ledger is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
