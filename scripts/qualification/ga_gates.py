"""Validate the ordered broad-GA ledger and optionally enforce stage completion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "qualification" / "policies" / "ga-gates-v1.json"
ALLOWED_STATUS = {"pending", "in_progress", "blocked", "complete"}
ALLOWED_PROFILE_STATE = {"pending", "contract_verified", "vendor_verified", "independently_signed", "qualified"}


def _evidence_reference(relative: str) -> tuple[Path, str]:
    path_text, _, anchor = relative.partition("#")
    return ROOT / path_text, anchor


def _validate_evidence_path(relative: object, owner: str) -> tuple[list[str], str | None]:
    if not isinstance(relative, str):
        return [f"{owner} evidence is missing: {relative}"], None
    path, anchor = _evidence_reference(relative)
    if not path.is_file():
        return [f"{owner} evidence is missing: {relative}"], None
    if anchor:
        if path.suffix.lower() != ".md":
            return [f"{owner} evidence anchor requires Markdown: {relative}"], None
        marker = f'<a id="{anchor}"></a>'
        if marker not in path.read_text(encoding="utf-8"):
            return [f"{owner} evidence anchor is missing: {relative}"], None
    return [], path.relative_to(ROOT).as_posix()


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
            path_errors, _ = _validate_evidence_path(relative, f"Stage {item.get('stage')}")
            errors.extend(path_errors)
    return errors


def _validate_profile_evidence(profile: dict[str, object], identity: object) -> list[str]:
    errors: list[str] = []
    evidence = profile.get("evidence")
    if not isinstance(evidence, list):
        return [f"GA profile {identity} evidence must be an array"]
    if profile.get("state") in {"qualified", "vendor_verified", "independently_signed"} and not evidence:
        errors.append(f"GA profile {identity} is accepted without evidence")
    for relative in evidence:
        path_errors, normalized_path = _validate_evidence_path(relative, f"GA profile {identity}")
        errors.extend(path_errors)
        if path_errors:
            continue
        if normalized_path and normalized_path.startswith("qualification/external-designs/"):
            errors.extend(_validate_external_evidence(normalized_path, identity))
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


def validate_candidate_bundle(  # noqa: C901
    bundle_path: Path,
    *,
    root: Path,
    artifacts: Path,
    expected_stage: int,
    expected_commit: str | None = None,
) -> list[str]:
    """Validate a candidate evidence bundle, including contextual subjects."""
    errors: list[str] = []
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"candidate evidence bundle is unreadable: {error}"]
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        return ["candidate evidence bundle schema_version is unsupported"]
    supplied_digest = bundle.get("bundle_sha256")
    unsigned = dict(bundle)
    unsigned.pop("bundle_sha256", None)
    actual_digest = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if supplied_digest != actual_digest:
        errors.append("candidate evidence bundle digest mismatch")
    if bundle.get("status") != "passed":
        errors.append("candidate evidence bundle is not passed")
    commit = bundle.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        errors.append("candidate evidence bundle commit is invalid")
    elif expected_commit is not None and commit != expected_commit:
        errors.append("candidate evidence bundle commit does not match expected commit")
    evidence = bundle.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return [*errors, "candidate evidence bundle has no evidence components"]
    try:
        from scripts.qualification.ga_evidence import verify_context
        from scripts.qualification.performance import compare_results, validate_result
    except ModuleNotFoundError as error:
        if error.name != "scripts":
            raise
        from ga_evidence import verify_context
        from performance import compare_results, validate_result

    baseline_relative = bundle.get("baseline")
    baseline_result: dict[str, object] | None = None
    if baseline_relative is not None:
        if not isinstance(baseline_relative, str):
            errors.append("candidate evidence baseline reference is invalid")
        else:
            baseline_path = (bundle_path.parent / baseline_relative).resolve()
            try:
                baseline_result = json.loads(baseline_path.read_text(encoding="utf-8"))
                errors.extend(validate_result(baseline_result, require_ga_scale=True))
                if isinstance(baseline_result, dict) and baseline_result.get("role") != "baseline":
                    errors.append("candidate evidence baseline must have baseline role")
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"candidate evidence baseline is unreadable: {error}")
    else:
        errors.append("candidate evidence bundle is missing an independent baseline")

    for relative in evidence:
        if not isinstance(relative, str):
            errors.append(f"candidate evidence component is invalid: {relative}")
            continue
        path = (bundle_path.parent / relative).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("schema_version") == 3:
                errors.extend(validate_result(payload, require_ga_scale=True))
                if payload.get("role") != "candidate":
                    errors.append(f"candidate evidence {relative} must have candidate role")
                identity = payload.get("identity")
                if not isinstance(identity, dict) or identity.get("commit") != commit:
                    errors.append(f"candidate evidence {relative} commit does not match bundle")
                if baseline_result is not None:
                    errors.extend(compare_results(baseline_result, payload))
            else:
                verify_context(
                    path, root=root, artifacts=artifacts, expected_stage=expected_stage, expected_commit=commit
                )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"candidate evidence {relative} is invalid: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through-stage", type=int, choices=range(6, 14))
    parser.add_argument("--mode", choices=("ledger", "candidate"), default="ledger")
    parser.add_argument("--candidate-bundle", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    document = json.loads(LEDGER.read_text(encoding="utf-8"))
    errors = validate_ledger(document)
    if args.through_stage is not None and not errors:
        errors.extend(enforce_through(document, args.through_stage))
    if args.mode == "candidate":
        if args.candidate_bundle is None or args.artifacts is None or args.through_stage is None:
            errors.append("candidate mode requires --candidate-bundle, --artifacts, and --through-stage")
        elif not errors:
            errors.extend(
                validate_candidate_bundle(
                    args.candidate_bundle,
                    root=args.root,
                    artifacts=args.artifacts,
                    expected_stage=args.through_stage,
                    expected_commit=args.expected_commit,
                )
            )
    for error in errors:
        print(error)
    if errors:
        return 1
    print("GA gate ledger is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
