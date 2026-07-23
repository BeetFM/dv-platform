"""Conservative UCIS XML functional-coverage importer.

The importer intentionally implements the portable UCIS XML boundary rather than
loading a vendor database library into the dv-platform process. Vendor tools can
export UCIS XML and configure :class:`UCISXMLCoverageImporter` as the project's
``coverage_importer`` adapter.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring


class UCISImportError(ValueError):
    """Raised when a UCIS document cannot be imported without ambiguity."""


class UCISXMLCoverageImporter:
    """Translate UCIS XML coverpoint and cross bins into closure points."""

    kind = "coverage_importer"
    api_version = 1
    MAX_INPUT_BYTES = 64 * 1024 * 1024
    _BIN_TAGS = {"coverpointBin", "crossBin"}
    _CONTAINER_TAGS = {"coverpoint", "cross"}

    def supports(self, path: Path) -> bool:
        """Return whether *path* has an unambiguous UCIS-oriented suffix."""

        lowered = path.name.lower()
        return lowered.endswith((".ucis", ".ucis.xml", ".ucis-xml"))

    def import_coverage(self, path: Path) -> dict[str, Any]:
        """Import functional bins while preserving failure and exclusion meaning."""

        raw = path.read_bytes()
        if len(raw) > self.MAX_INPUT_BYTES:
            raise UCISImportError(f"UCIS input exceeds {self.MAX_INPUT_BYTES} byte safety limit: {path}")
        upper = raw.upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise UCISImportError("UCIS input must not contain DTD or entity declarations")

        try:
            root = fromstring(raw)
        except ParseError as exc:
            raise UCISImportError(f"invalid UCIS XML in {path}: {exc}") from exc
        if _local_name(root.tag).lower() != "ucis":
            raise UCISImportError(f"expected a UCIS root element in {path}")

        module = _module_name(root, path)
        points: list[dict[str, Any]] = []
        self._walk(root, (), module, points)
        if not points:
            raise UCISImportError(f"UCIS input contains no functional coverage bins: {path}")
        return {
            "schema_version": 2,
            "source_format": "ucis-xml",
            "coverage_points": points,
            "formal_points": [],
        }

    def _walk(
        self,
        element: Element,
        scope: tuple[str, ...],
        module: str,
        points: list[dict[str, Any]],
    ) -> None:
        tag = _local_name(element.tag)
        name = element.attrib.get("name", "").strip()
        current_scope = (*scope, name) if name and tag not in self._BIN_TAGS else scope

        if tag in self._CONTAINER_TAGS:
            at_least = _at_least(element)
            for child in element:
                if _local_name(child.tag) in self._BIN_TAGS:
                    points.append(self._point(child, current_scope, module, tag, at_least))

        for child in element:
            self._walk(child, current_scope, module, points)

    def _point(
        self,
        element: Element,
        scope: tuple[str, ...],
        module: str,
        container_tag: str,
        at_least: int,
    ) -> dict[str, Any]:
        bin_name = element.attrib.get("name", "").strip()
        if not bin_name:
            raise UCISImportError(f"{_local_name(element.tag)} is missing its name")
        qualified_name = "/".join((*scope, bin_name))
        hits = _coverage_count(element)
        bin_type = element.attrib.get("type", "bins").strip().lower()

        if bin_type == "ignore":
            status = "excluded"
        elif bin_type == "illegal":
            status = "failed" if hits else "covered"
        elif bin_type in {"bins", "default", ""}:
            status = "covered" if hits >= at_least else "uncovered"
        else:
            raise UCISImportError(f"unsupported UCIS bin type {bin_type!r} at {qualified_name}")

        kind = "cross" if container_tag == "cross" else "coverpoint"
        digest = sha256(f"{module}\0{kind}\0{qualified_name}".encode()).hexdigest()[:24]
        point: dict[str, Any] = {
            "id": f"ucis:{kind}:{digest}",
            "module": module,
            "name": qualified_name,
            "kind": kind,
            "hits": hits,
            "status": status,
            "vendor_provenance": {"format": "ucis-xml", "scope": "/".join(scope)},
            "cross_members": list(scope) if kind == "cross" else [],
        }
        check_id = element.attrib.get("dvCheckId") or element.attrib.get("checkId") or element.attrib.get("check_id")
        if check_id:
            point["check_id"] = check_id.strip()
        requirement_ids = _extension_ids(
            element,
            ("dvRequirementId", "requirementId", "requirement_id"),
        )
        if requirement_ids:
            point["requirement_ids"] = requirement_ids
        behavior_ids = _extension_ids(
            element,
            ("dvBehaviorId", "behaviorId", "behavior_id"),
        )
        if behavior_ids:
            point["behavior_ids"] = behavior_ids
        return point


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _module_name(root: Element, path: Path) -> str:
    for attribute in ("module", "designUnit", "design_unit", "duName"):
        value = root.attrib.get(attribute, "").strip()
        if value:
            return value
    for element in root.iter():
        if _local_name(element.tag) in {"instanceCoverage", "designUnit", "module"}:
            value = element.attrib.get("name", "").strip()
            if value:
                return value
    lowered = path.name.lower()
    for suffix in (".ucis.xml", ".ucis-xml", ".ucis"):
        if lowered.endswith(suffix):
            fallback = path.name[: -len(suffix)].strip()
            if fallback:
                return fallback
    raise UCISImportError(f"cannot derive a module name from UCIS input: {path}")


def _at_least(element: Element) -> int:
    raw: str | None = element.attrib.get("at_least") or element.attrib.get("atLeast")
    for child in element:
        if _local_name(child.tag) == "options":
            raw = child.attrib.get("at_least") or child.attrib.get("atLeast") or raw
            break
    if raw is None:
        return 1
    try:
        value = int(raw)
    except ValueError as exc:
        raise UCISImportError(f"invalid UCIS at_least value: {raw!r}") from exc
    if value < 1:
        raise UCISImportError(f"UCIS at_least must be positive, got {value}")
    return value


def _coverage_count(element: Element) -> int:
    counts: list[int] = []
    direct = element.attrib.get("coverageCount")
    if direct is not None:
        counts.append(_nonnegative_int(direct, "coverageCount"))
    for descendant in element.iter():
        if descendant is element or _local_name(descendant.tag) != "contents":
            continue
        raw = descendant.attrib.get("coverageCount")
        if raw is not None:
            counts.append(_nonnegative_int(raw, "coverageCount"))
    if not counts:
        raise UCISImportError(f"{_local_name(element.tag)} {element.attrib.get('name', '')!r} has no coverageCount")
    return sum(counts)


def _nonnegative_int(raw: str, field: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise UCISImportError(f"invalid UCIS {field} value: {raw!r}") from exc
    if value < 0:
        raise UCISImportError(f"UCIS {field} must be non-negative, got {value}")
    return value


def _extension_ids(element: Element, names: tuple[str, ...]) -> list[str]:
    raw = next((element.attrib[name] for name in names if element.attrib.get(name)), "")
    return list(dict.fromkeys(value.strip() for value in raw.split(",") if value.strip()))


for _legacy_class in (UCISImportError, UCISXMLCoverageImporter):
    _legacy_class.__module__ = "dv_platform.analysis.ucis"
del _legacy_class
__name__ = "dv_platform.analysis.ucis"
