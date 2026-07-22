"""Generate a deterministic SPDX 2.3 JSON SBOM from the locked environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked_packages = tuple(lock.get("package", ()))
    scopes = _dependency_scopes(locked_packages, "dv-platform")
    packages = []
    relationships = []
    identifiers = {
        str(item["name"]): "SPDXRef-Package-"
        + "".join(character if character.isalnum() else "-" for character in str(item["name"]))
        for item in locked_packages
    }
    for item in sorted(locked_packages, key=lambda package: (package["name"], package["version"])):
        name = str(item["name"])
        version = str(item["version"])
        spdx_id = identifiers[name]
        license_declared = _license_for(name)
        packages.append(
            {
                "SPDXID": spdx_id,
                "name": name,
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": license_declared,
                "licenseDeclared": license_declared,
                "copyrightText": "NOASSERTION",
                "comment": "dependency-scopes=" + ",".join(sorted(scopes.get(name, {"locked"}))),
            }
        )
        relationships.append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": spdx_id}
        )
        for dependency in item.get("dependencies", ()):
            dependency_name = str(dependency["name"])
            if dependency_name in identifiers:
                relationships.append(
                    {
                        "spdxElementId": spdx_id,
                        "relationshipType": "DEPENDS_ON",
                        "relatedSpdxElement": identifiers[dependency_name],
                    }
                )
    lock_digest = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "veriforge-dv-platform-lock",
        "documentNamespace": f"https://veriforge.dev/spdx/uv-lock-{lock_digest}",
        "creationInfo": {"created": "1970-01-01T00:00:00Z", "creators": ["Tool: veriforge-generate-sbom"]},
        "packages": packages,
        "relationships": relationships,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _license_for(name: str) -> str:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return "LicenseRef-NotInstalled"
    expression = _metadata_value(distribution.metadata, "License-Expression")
    if expression and len(expression) <= 200 and "\n" not in expression:
        return str(expression).strip()
    legacy = _metadata_value(distribution.metadata, "License")
    if legacy and len(legacy) <= 200 and "\n" not in legacy:
        return _license_expression(str(legacy))
    classifiers = distribution.metadata.get_all("Classifier") or ()
    license_classifiers = [item.rsplit("::", 1)[-1].strip() for item in classifiers if item.startswith("License ::")]
    return _license_expression(license_classifiers[0]) if license_classifiers else "LicenseRef-Unreported"


def _license_expression(value: str) -> str:
    normalized = " ".join(value.strip().split())
    aliases = {
        "mit": "MIT",
        "mit license": "MIT",
        "apache 2.0": "Apache-2.0",
        "apache license 2.0": "Apache-2.0",
        "apache software license": "Apache-2.0",
        "bsd license": "BSD-3-Clause",
        "bsd-3-clause": "BSD-3-Clause",
        "isc license": "ISC",
        "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
        "python software foundation license": "PSF-2.0",
    }
    if normalized.lower() in aliases:
        return aliases[normalized.lower()]
    slug = "-".join(
        part for part in ("".join(character if character.isalnum() else " " for character in normalized)).split()
    )
    return "LicenseRef-" + (slug or "Unreported")


def _metadata_value(metadata: object, key: str) -> str | None:
    try:
        value = metadata[key]  # type: ignore[index]
    except KeyError:
        return None
    return str(value) if value is not None else None


def _dependency_scopes(packages: tuple[dict[str, object], ...], root_name: str) -> dict[str, set[str]]:
    by_name = {str(item["name"]): item for item in packages}
    root = by_name.get(root_name)
    if root is None:
        raise ValueError(f"locked root package is missing: {root_name}")
    seeds: dict[str, set[str]] = {
        "runtime": _dependency_names(root.get("dependencies", ())),
    }
    for extra, dependencies in _string_map(root.get("optional-dependencies", {})).items():
        seeds[f"optional:{extra}"] = _dependency_names(dependencies)
    for group, dependencies in _string_map(root.get("dev-dependencies", {})).items():
        seeds[f"development:{group}"] = _dependency_names(dependencies)
    scopes: dict[str, set[str]] = {root_name: {"root"}}
    for scope, initial in seeds.items():
        pending = list(initial)
        visited: set[str] = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            scopes.setdefault(name, set()).add(scope)
            item = by_name.get(name)
            if item is not None:
                pending.extend(_dependency_names(item.get("dependencies", ())))
    return scopes


def _dependency_names(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item["name"]) for item in value if isinstance(item, dict) and "name" in item}


def _string_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


if __name__ == "__main__":
    raise SystemExit(main())
