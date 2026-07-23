# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Versioned, fail-closed semantic facts interchange."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    RTLModule,
)

SEMANTIC_MANIFEST_SCHEMA_VERSION = 2
MIN_READABLE_SEMANTIC_MANIFEST_SCHEMA_VERSION = 0
MAX_SEMANTIC_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_EXPRESSION_DEPTH = 64
SUPPORTED_LANGUAGES = frozenset({"systemverilog", "verilog", "vhdl"})
SUPPORTED_STANDARDS = {
    "systemverilog": frozenset({"1800-2005", "1800-2009", "1800-2012", "1800-2017", "1800-2023"}),
    "verilog": frozenset({"1364-1995", "1364-2001", "1364-2005"}),
    "vhdl": frozenset({"1076-1987", "1076-1993", "1076-2000", "1076-2002", "1076-2008", "1076-2019"}),
}
DESIGN_UNIT_KINDS = {
    "systemverilog": frozenset({"module", "interface", "program", "package", "checker"}),
    "verilog": frozenset({"module", "primitive", "configuration"}),
    "vhdl": frozenset({"entity", "architecture", "package", "configuration", "context"}),
}
COMPLETENESS_STATES = frozenset({"complete", "partial", "unsupported", "not_applicable"})
SEMANTIC_CATEGORIES = (
    "lexical_preprocessing",
    "libraries_compilation_units",
    "design_units",
    "declarations",
    "types",
    "expressions",
    "statements",
    "subprograms",
    "hierarchy",
    "elaboration",
    "parameters_generics",
    "ports",
    "packages_imports",
    "interfaces_modports",
    "classes_randomization",
    "assignments",
    "processes",
    "assertions",
    "functional_coverage",
    "generates",
    "memories",
    "timing_specify",
    "foreign_interfaces",
    "attributes_pragmas",
    "file_io",
    "clocks_resets",
    "cdc",
    "protocols",
)


class SemanticImportError(ValueError):
    """Raised when semantic evidence cannot be normalized soundly."""


@dataclass(frozen=True)
class SemanticDiagnostic:
    severity: str
    code: str
    message: str
    source_location: str | None = None


@dataclass(frozen=True)
class SemanticCompleteness:
    module: str
    language: str
    standard: str
    categories: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        return all(state in {"complete", "not_applicable"} for _, state in self.categories)


@dataclass(frozen=True)
class SemanticImportResult:
    schema_version: int
    producer_name: str
    producer_version: str
    modules: tuple[RTLModule, ...]
    completeness: tuple[SemanticCompleteness, ...]
    diagnostics: tuple[SemanticDiagnostic, ...]

    @property
    def complete(self) -> bool:
        return bool(self.modules) and all(item.complete for item in self.completeness)


class SemanticManifestImporter:
    """Import `.dvsem.json` manifests through the plugin boundary."""

    kind = "semantic_importer"
    api_version = 1

    def supports(self, path: Path) -> bool:
        lowered = path.name.lower()
        return lowered.endswith((".dvsem.json", ".semantic.json"))

    def import_semantics(self, path: Path, repo_root: Path, *, strict: bool = False) -> SemanticImportResult:
        raw = path.read_bytes()
        if len(raw) > MAX_SEMANTIC_MANIFEST_BYTES:
            raise SemanticImportError(f"semantic manifest exceeds {MAX_SEMANTIC_MANIFEST_BYTES} byte limit: {path}")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SemanticImportError(f"invalid semantic manifest JSON in {path}: {exc}") from exc
        root = _migrate_manifest(_mapping(document, "semantic manifest"))
        _known_keys(root, {"schema_version", "producer", "modules", "diagnostics"}, "manifest")
        producer = _mapping(root.get("producer"), "producer")
        _known_keys(producer, {"name", "version"}, "producer")
        producer_name = _required_string(producer, "name", "producer")
        producer_version = _required_string(producer, "version", "producer")
        source_id = f"{producer_name}@{producer_version}"

        records = _record_list(root.get("modules"), "modules")
        if not records:
            raise SemanticImportError("semantic manifest contains no modules")
        modules: list[RTLModule] = []
        completeness: list[SemanticCompleteness] = []
        identities: set[tuple[str, str | None]] = set()
        for index, record in enumerate(records):
            module, ledger = _module(record, repo_root.resolve(), path, source_id, index)
            identity = (module.name, module.specialization_id)
            if identity in identities:
                raise SemanticImportError(
                    f"duplicate semantic design unit identity: {module.name}/{module.specialization_id}"
                )
            identities.add(identity)
            modules.append(module)
            completeness.append(ledger)
        diagnostics = tuple(
            _diagnostic(item, index)
            for index, item in enumerate(_record_list(root.get("diagnostics", []), "diagnostics"))
        )
        result = SemanticImportResult(
            SEMANTIC_MANIFEST_SCHEMA_VERSION,
            producer_name,
            producer_version,
            tuple(modules),
            tuple(completeness),
            diagnostics,
        )
        if strict and not result.complete:
            incomplete = [item.module for item in result.completeness if not item.complete]
            raise SemanticImportError(
                "strict semantic import requires complete capability ledgers: " + ", ".join(incomplete)
            )
        if strict and any(item.severity == "error" for item in diagnostics):
            raise SemanticImportError("strict semantic import contains error diagnostics")
        return result


def _migrate_manifest(root: Mapping[str, Any]) -> Mapping[str, Any]:
    version = root.get("schema_version", 0)
    if not isinstance(version, int):
        raise SemanticImportError("semantic manifest schema_version must be an integer")
    if version > SEMANTIC_MANIFEST_SCHEMA_VERSION:
        raise SemanticImportError(
            f"semantic manifest schema {version} is newer than supported {SEMANTIC_MANIFEST_SCHEMA_VERSION}"
        )
    if version < MIN_READABLE_SEMANTIC_MANIFEST_SCHEMA_VERSION:
        raise SemanticImportError(f"semantic manifest schema {version} is no longer readable")
    if version == SEMANTIC_MANIFEST_SCHEMA_VERSION:
        return root
    migrated = dict(root)
    migrated["schema_version"] = SEMANTIC_MANIFEST_SCHEMA_VERSION
    migrated["modules"] = migrated.pop("design_units", migrated.get("modules", []))
    migrated.setdefault("diagnostics", [])
    for module in migrated["modules"]:
        if isinstance(module, dict):
            ledger = module.setdefault("completeness", {})
            if isinstance(ledger, dict):
                for category in SEMANTIC_CATEGORIES:
                    ledger.setdefault(category, "partial")
    return migrated


for _legacy_class in (
    SemanticImportError,
    SemanticDiagnostic,
    SemanticCompleteness,
    SemanticImportResult,
    SemanticManifestImporter,
):
    _legacy_class.__module__ = "dv_platform.enterprise.semantics"
del _legacy_class
