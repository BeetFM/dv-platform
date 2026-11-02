"""Freeze the supported physical-design APIs, CLIs, schemas, and native driver."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import inspect
import json
import pkgutil
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "qualification/policies/compatibility-baseline-v1.json"
COMPATIBILITY_ROOTS = {
    "dv_platform.cli",
    "dv_platform.configuration",
    "dv_platform.core",
    "dv_platform.physical",
    "dv_platform.physical_design",
    "dv_platform.sky130",
    "dv_platform.signoff",
    "dv_platform.release",
    "dv_platform.signing",
    "dv_platform.enterprise",
}


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_text(value: str) -> str:
    normalized = value.replace(str(ROOT), "<REPO>")
    normalized = re.sub(r"/tmp/[A-Za-z0-9_.-]+", "<TMP>", normalized)
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<UUID>", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\brev-[0-9a-f]{8,}\b", "rev-<ID>", normalized)
    normalized = re.sub(
        r"\(choose from ([^)]*)\)", lambda match: "(choose from " + match[1].replace("'", "") + ")", normalized
    )
    return re.sub(
        r"\b20\d\d-\d\d-\d\d[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?\b",
        "<TIMESTAMP>",
        normalized,
    )


def _module_names() -> tuple[str, ...]:
    import dv_platform

    discovered = {dv_platform.__name__}
    discovered.update(item.name for item in pkgutil.walk_packages(dv_platform.__path__, "dv_platform."))
    return tuple(
        sorted(
            name
            for name in discovered
            if name == "dv_platform" or any(name == root or name.startswith(root + ".") for root in COMPATIBILITY_ROOTS)
        )
    )


def _signature(value: object) -> str | None:
    if not callable(value):
        return None
    if inspect.isclass(value) and issubclass(value, Enum):
        return "(value)"
    try:
        return re.sub(r"0x[0-9a-fA-F]+", "0x<ADDRESS>", str(inspect.signature(value)))
    except (TypeError, ValueError):
        return None


def _symbol_kind(value: object) -> str:
    if inspect.isclass(value):
        return "class"
    if inspect.isfunction(value):
        return "function"
    if inspect.ismodule(value):
        return "module"
    return type(value).__name__


def capture_module_contracts() -> dict[str, object]:
    contracts: dict[str, object] = {}
    for module_name in _module_names():
        module = importlib.import_module(module_name)
        symbols = {}
        for name, value in sorted(vars(module).items()):
            if name.startswith("__"):
                continue
            if inspect.ismodule(value) and value.__name__.startswith(module.__name__ + "."):
                continue
            if (inspect.isclass(value) or inspect.isfunction(value)) and not getattr(
                value, "__module__", ""
            ).startswith("dv_platform"):
                continue
            symbols[name] = {
                "kind": _symbol_kind(value),
                "signature": _signature(value),
            }
            if inspect.isclass(value) and issubclass(value, Enum):
                symbols[name]["members"] = {member.name: member.value for member in value}
        contracts[module_name] = symbols
    return contracts


def capture_dataclass_contracts() -> dict[str, object]:
    from dv_platform.domain import models

    result = {}
    for name, value in sorted(vars(models).items()):
        if not inspect.isclass(value) or not dataclasses.is_dataclass(value):
            continue
        result[name] = {
            "lookup_module": value.__module__,
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "has_default": field.default is not dataclasses.MISSING
                    or field.default_factory is not dataclasses.MISSING,
                }
                for field in dataclasses.fields(value)
            ],
        }
    return result


def _cli_case(arguments: Sequence[str], *, enterprise: bool = False) -> dict[str, object]:
    if enterprise:
        expression = "from dv_platform.enterprise.cli import main; raise SystemExit(main())"
        command = [sys.executable, "-c", expression, *arguments]
    else:
        command = [sys.executable, "-m", "dv_platform", *arguments]
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    return {
        "arguments": list(arguments),
        "exit_code": completed.returncode,
        "stdout": _normalized_text(completed.stdout),
        "stderr": _normalized_text(completed.stderr),
    }


def capture_cli_contracts() -> dict[str, object]:
    return {
        "main_help": _cli_case(("--help",)),
        "main_invalid": _cli_case(("not-a-command",)),
        "enterprise_help": _cli_case(("--help",), enterprise=True),
    }


def capture_entry_points() -> dict[str, object]:
    result = {}
    for name in ("pyproject.toml", "enterprise/pyproject.toml"):
        project = tomllib.loads((ROOT / name).read_text(encoding="utf-8"))["project"]
        result[name] = {"scripts": project.get("scripts", {}), "entry-points": project.get("entry-points", {})}
    return result


def capture_schema_versions() -> dict[str, object]:
    result = {}
    for module_name in _module_names():
        module = importlib.import_module(module_name)
        versions = {
            name: value
            for name, value in vars(module).items()
            if name.isupper()
            and ("SCHEMA_VERSION" in name or name.endswith("_API_VERSION"))
            and isinstance(value, str | int)
        }
        if versions:
            result[module_name] = dict(sorted(versions.items()))
    return result


def capture_runtime_assets() -> list[dict[str, object]]:
    paths = [
        *(ROOT / "src/dv_platform" / name for name in ("physical_design.tcl", "sky130_flow.tcl", "sky130-pin.json")),
        *sorted((ROOT / "schemas").rglob("*.json")),
    ]
    return [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in paths
    ]


def capture_manifest() -> dict[str, object]:
    return {
        "format": "dv-platform-compatibility-contract-v1",
        "modules": capture_module_contracts(),
        "dataclasses": capture_dataclass_contracts(),
        "cli": capture_cli_contracts(),
        "entry_points": capture_entry_points(),
        "schemas": capture_schema_versions(),
        "artifacts": capture_runtime_assets(),
    }


def fingerprints(manifest: Mapping[str, object]) -> dict[str, object]:
    sections = ("modules", "dataclasses", "cli", "entry_points", "schemas", "artifacts")
    return {
        "format": manifest["format"],
        "sections": {name: _digest(manifest[name]) for name in sections},
        "counts": {
            "modules": len(manifest["modules"]) if isinstance(manifest["modules"], Mapping) else 0,
            "dataclasses": len(manifest["dataclasses"]) if isinstance(manifest["dataclasses"], Mapping) else 0,
            "artifacts": len(manifest["artifacts"]) if isinstance(manifest["artifacts"], Sequence) else 0,
        },
        "overall": _digest(manifest),
    }


def compare(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> tuple[str, ...]:
    errors = []
    if expected.get("format") != actual.get("format"):
        errors.append(f"format changed: {expected.get('format')!r} -> {actual.get('format')!r}")
    expected_sections = expected.get("sections", {})
    actual_sections = actual.get("sections", {})
    if isinstance(expected_sections, Mapping) and isinstance(actual_sections, Mapping):
        for name in sorted(set(expected_sections) | set(actual_sections)):
            if expected_sections.get(name) != actual_sections.get(name):
                errors.append(f"{name} compatibility fingerprint changed")
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--manifest", action="store_true", help="print the full normalized manifest")
    args = parser.parse_args()
    manifest = capture_manifest()
    actual = fingerprints(manifest)
    if args.manifest:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.check:
        print(json.dumps(actual, indent=2, sort_keys=True))
        return 0
    expected = json.loads(args.baseline.read_text(encoding="utf-8"))
    errors = compare(expected, actual)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"compatibility contract passed ({actual['overall']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
