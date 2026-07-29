"""Fail-closed verification for checksums, SPDX SBOM, and SLSA provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


class ReleaseVerificationError(ValueError):
    """Raised when release material is incomplete, ambiguous, or inconsistent."""


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseVerificationError(f"cannot read valid JSON from {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseVerificationError(f"{path.name} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_checksums(root: Path, checksum_path: Path) -> None:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 2 or len(fields[0]) != 64:
            raise ReleaseVerificationError(f"invalid SHA256SUMS record at line {line_number}")
        digest, name = fields
        candidate = Path(name)
        if candidate.name != name or candidate.is_absolute() or name in checksums:
            raise ReleaseVerificationError(f"unsafe or duplicate checksum subject: {name}")
        if any(character not in "0123456789abcdef" for character in digest):
            raise ReleaseVerificationError(f"invalid checksum for {name}")
        checksums[name] = digest
    if not checksums:
        raise ReleaseVerificationError("SHA256SUMS contains no subjects")
    for name, expected in checksums.items():
        subject = root / name
        if not subject.is_file() or subject.is_symlink() or subject.parent != root:
            raise ReleaseVerificationError(f"missing or unsafe checksum subject: {name}")
        if _digest(subject) != expected:
            raise ReleaseVerificationError(f"checksum mismatch: {name}")


def _verify_sbom(sbom_path: Path) -> None:
    sbom = _object(sbom_path)
    if sbom.get("spdxVersion") != "SPDX-2.3" or sbom.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise ReleaseVerificationError("SBOM is not an SPDX 2.3 document")
    packages = sbom.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ReleaseVerificationError("SBOM contains no packages")
    package_ids = [item.get("SPDXID") for item in packages if isinstance(item, dict)]
    if len(package_ids) != len(packages) or len(set(package_ids)) != len(package_ids):
        raise ReleaseVerificationError("SBOM package identities are missing or duplicated")
    for item in packages:
        if not isinstance(item, dict):
            raise ReleaseVerificationError("SBOM package record is invalid")
        if item.get("licenseDeclared") in {None, "", "NOASSERTION"} or item.get("licenseConcluded") in {
            None,
            "",
            "NOASSERTION",
        }:
            raise ReleaseVerificationError(f"SBOM package license is incomplete: {item.get('name', 'unknown')}")
        if not str(item.get("comment", "")).startswith("dependency-scopes="):
            raise ReleaseVerificationError(f"SBOM package scope is missing: {item.get('name', 'unknown')}")


def _provenance_definition(provenance: dict[str, Any]) -> dict[str, Any]:
    if provenance.get("_type") != "https://in-toto.io/Statement/v1":
        raise ReleaseVerificationError("provenance is not an in-toto v1 statement")
    if provenance.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise ReleaseVerificationError("provenance is not a SLSA v1 statement")
    predicate = provenance.get("predicate")
    if not isinstance(predicate, dict) or not isinstance(predicate.get("buildDefinition"), dict):
        raise ReleaseVerificationError("provenance build definition is missing")
    return predicate["buildDefinition"]


def _verify_provenance_identity(provenance: dict[str, Any]) -> None:
    definition = _provenance_definition(provenance)
    if definition.get("buildType") != "https://veriforge.dev/build-types/python-wheel/v1":
        raise ReleaseVerificationError("provenance build type is unsupported")
    dependencies = definition.get("resolvedDependencies")
    valid_dependency = (
        isinstance(dependencies, list)
        and len(dependencies) == 1
        and isinstance(dependencies[0], dict)
        and isinstance(dependencies[0].get("digest"), dict)
        and re.fullmatch(r"[0-9a-f]{40}", str(dependencies[0]["digest"].get("gitCommit", ""))) is not None
    )
    if not valid_dependency:
        raise ReleaseVerificationError("provenance source commit is missing or invalid")
    internal = definition.get("internalParameters")
    if not isinstance(internal, dict) or re.fullmatch(r"[0-9a-f]{64}", str(internal.get("lockfileSha256", ""))) is None:
        raise ReleaseVerificationError("provenance lockfile identity is missing or invalid")


def _provenance_subjects(provenance: dict[str, Any]) -> dict[str, str]:
    raw_subjects = provenance.get("subject")
    if not isinstance(raw_subjects, list):
        raise ReleaseVerificationError("provenance subjects must be an array")
    subjects: dict[str, str] = {}
    for item in raw_subjects:
        if not isinstance(item, dict) or not isinstance(item.get("digest"), dict):
            raise ReleaseVerificationError("invalid provenance subject")
        subject_name = item.get("name")
        digest = item["digest"].get("sha256")
        if not isinstance(subject_name, str) or Path(subject_name).name != subject_name or subject_name in subjects:
            raise ReleaseVerificationError("unsafe or duplicate provenance subject")
        if not isinstance(digest, str):
            raise ReleaseVerificationError(f"missing provenance digest: {subject_name}")
        subjects[subject_name] = digest
    return subjects


def _expected_subjects(root: Path, provenance_path: Path) -> dict[str, str]:
    return {
        path.name: _digest(path)
        for path in root.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and not path.name.startswith(".")
        and path.name != provenance_path.name
        and path.name != "release-manifest.json"
        and not path.name.endswith(".sigstore.json")
    }


def _verify_provenance(root: Path, provenance_path: Path) -> tuple[str, ...]:
    provenance = _object(provenance_path)
    _verify_provenance_identity(provenance)
    subjects = _provenance_subjects(provenance)
    expected_subjects = _expected_subjects(root, provenance_path)
    if subjects != expected_subjects:
        missing = sorted(expected_subjects.keys() - subjects.keys())
        extra = sorted(subjects.keys() - expected_subjects.keys())
        mismatched = sorted(
            name for name in subjects.keys() & expected_subjects.keys() if subjects[name] != expected_subjects[name]
        )
        raise ReleaseVerificationError(
            f"provenance subject mismatch; missing={missing}, extra={extra}, digest_mismatch={mismatched}"
        )
    if not any(name.endswith(".whl") for name in subjects) or not any(name.endswith(".tar.gz") for name in subjects):
        raise ReleaseVerificationError("provenance must cover a wheel and source distribution")
    return tuple(sorted(subjects))


def verify_release_materials(directory: Path) -> tuple[str, ...]:
    """Verify all unsigned release subjects and return their sorted names."""

    root = directory.resolve(strict=True)
    checksum_path = root / "SHA256SUMS"
    sbom_path = root / "sbom.spdx.json"
    provenance_path = root / "provenance.intoto.json"
    for required in (checksum_path, sbom_path, provenance_path):
        if not required.is_file() or required.is_symlink():
            raise ReleaseVerificationError(f"missing or unsafe release material: {required.name}")
    _verify_checksums(root, checksum_path)
    _verify_sbom(sbom_path)
    return _verify_provenance(root, provenance_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    try:
        subjects = verify_release_materials(args.artifact_dir)
    except (OSError, ReleaseVerificationError) as error:
        print(error)
        return 1
    print(f"release materials verified ({len(subjects)} subjects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
