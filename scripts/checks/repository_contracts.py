"""Check documentation links, CLI examples, schemas, and capability vocabulary."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shlex
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from dv_platform.cli import build_parser
from dv_platform.core.schema import PLAN_REVISION_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
MARKDOWN = tuple(sorted((*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md"))))
LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")
FENCE = re.compile(r"```(?:bash|console|shell)\n(.*?)```", re.DOTALL)
CAPABILITY_STATES = {"supported", "partial", "scaffold", "unsupported"}
CONSOLIDATED_GUIDES = {
    "agents.md": (
        "docs/README.md",
        "docs/agent-execution-guide.md",
        "docs/documentation-contract.md",
    ),
    "architecture.md": (
        "docs/architecture/architecture.md",
        "docs/architecture/backends-and-output.md",
        "docs/architecture/evidence-model.md",
        "docs/architecture/verilator-ast.md",
        "docs/architecture/semantic-cross-check.md",
        "docs/architecture/slang-compatibility-matrix.md",
        "docs/architecture/language-semantic-completeness.md",
        "docs/architecture/verification-depth.md",
        "docs/architecture/protocol-profiles.md",
        "docs/architecture/enterprise-adapters.md",
        "docs/compatibility/contract.md",
        "docs/adr/README.md",
        "docs/adr/0001-local-project-configuration.md",
        "docs/adr/0002-verilator-xml-evidence.md",
        "docs/adr/0003-local-first-documentation-retrieval.md",
        "docs/adr/0004-claim-validation-gating.md",
        "docs/adr/0005-sqlite-canonical-stores.md",
        "docs/adr/0006-requirements-driven-generation-targets.md",
        "docs/adr/0007-formal-uvm-backend-boundaries.md",
        "docs/adr/0008-enterprise-plugins-platforms-distribution.md",
    ),
    "operations.md": (
        "docs/operations/operator-guide.md",
        "docs/operations/production-closure-runbook.md",
        "docs/operations/coverage-closure.md",
        "docs/operations/rag-operations.md",
        "docs/operations/security-and-privacy.md",
        "docs/operations/support-policy.md",
        "docs/operations/upgrade-and-rollback.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md",
    ),
    "product-and-interface.md": (
        "README.md",
        "docs/config/installation.md",
        "docs/config/configuration.md",
        "docs/config/cli-contract.md",
    ),
    "roadmap.md": (
        "docs/planning/README.md",
        "docs/planning/missing-work.md",
        "docs/planning/implementation-plan.md",
        "progress.md",
    ),
    "verification.md": (
        "docs/qualification/capability-matrix.md",
        "docs/qualification/verification-production-readiness.md",
        "docs/qualification/testing-and-qualification.md",
        "docs/qualification/enterprise-qualification.md",
        "docs/qualification/ga-contract.md",
        "docs/qualification/ga-stages.md",
        "qualification/README.md",
        "qualification/profiles/ahb-lite-single-beat.md",
        "qualification/stages/stage6-foundation.md",
        "qualification/stages/stage7-on-chip-protocols.md",
        "qualification/stages/stage8-board-peripherals.md",
        "qualification/stages/stage9-vhdl-uvm.md",
        "qualification/stages/stage10-semantic-designs.md",
        "qualification/stages/stage10-scale-platform.md",
        "docs/acceptance/README.md",
        "docs/acceptance/pilot-acceptance.md",
        "docs/acceptance/p1-acceptance.md",
        "docs/acceptance/apb4-acceptance.md",
        "docs/acceptance/axi4-lite-acceptance.md",
        "docs/acceptance/feedback-revision-acceptance.md",
        "docs/acceptance/cdc-synchronizer-acceptance.md",
        "docs/acceptance/async-fifo-acceptance.md",
        "docs/acceptance/reset-rdc-acceptance.md",
        "docs/acceptance/memory-depth-acceptance.md",
        "docs/acceptance/formal-depth-acceptance.md",
        "docs/acceptance/parameter-sweep-acceptance.md",
        "docs/acceptance/vhdl-normalization-acceptance.md",
        "docs/acceptance/stage4-acceptance.md",
        "docs/acceptance/stage5-acceptance.md",
    ),
}
ROADMAP_CARDS = (
    "FREE-DIGITAL-01",
    "FREE-FORMAL-01",
    "PLAN-GATE-01",
    "ENT-EDA-01",
    "ENT-BOARD-01",
    "QUAL-01",
    "RELEASE-01",
    "SCALE-02",
    "AI-03",
    "BUG-CDC-01",
    "QUALITY-01",
    "DOC-00",
    "DOC-02",
    "DOC-03",
    "TIER-01",
    "BOARD-01",
    "SEM-01",
    "SEM-02",
    "SEM-03",
    "VHDL-01",
    "FORM-01",
    "CDC-01",
    "RDC-01",
    "MEM-01",
    "PROTO-01",
    "PROTO-02",
    "PERIPH-01",
    "UVM-01",
    "TOOL-01",
    "COV-01",
    "COV-02",
    "DOC-01",
    "SCALE-01",
    "PLAT-01",
    "AI-01",
    "AI-02",
    "PHYS-01",
)


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[`*_~]", "", value).strip().lower()
    value = re.sub(r"[^a-z0-9 _-]", "", value)
    value = re.sub(r"[ _]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def _source_anchor(source: str) -> str:
    return f"source-{_slug(source)}"


def _has_anchor(document: Path, fragment: str) -> bool:
    text = document.read_text(encoding="utf-8")
    if f'id="{fragment}"' in text:
        return True
    return any(_slug(match.group(1)) == fragment for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.MULTILINE))


def _source_section(document: Path, anchor: str) -> str:
    text = document.read_text(encoding="utf-8")
    marker = f'<a id="{anchor}"></a>'
    start = text.find(marker)
    if start < 0:
        return ""
    remainder = text[start:]
    next_source = re.search(r'\n<a id="source-[^"]+"></a>\n## ', remainder[len(marker) :])
    if next_source is None:
        return remainder
    return remainder[: len(marker) + next_source.start()]


def check_internal_links() -> list[str]:
    errors: list[str] = []
    for document in MARKDOWN:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            target = target.split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_text = target.split("#", 1)[0]
            target_path = (document.parent / path_text).resolve(strict=False) if path_text else document
            if path_text and not target_path.exists():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")
                continue
            fragment = unquote(target.partition("#")[2])
            if fragment and target_path.is_file() and not _has_anchor(target_path, fragment):
                errors.append(f"{document.relative_to(ROOT)}: broken anchor {target}")
    return errors


def _check_consolidated_guide(guide_name: str, sources: tuple[str, ...]) -> list[str]:
    guide = ROOT / "docs" / guide_name
    if not guide.is_file():
        return []
    errors: list[str] = []
    text = guide.read_text(encoding="utf-8")
    anchors = re.findall(r'<a id="([^"]+)"></a>', text)
    duplicated = sorted({anchor for anchor in anchors if anchors.count(anchor) > 1})
    if duplicated:
        errors.append(f"docs/{guide_name}: duplicate explicit anchors: {duplicated}")
    for source in sources:
        anchor = _source_anchor(source)
        if f'<a id="{anchor}"></a>' not in text:
            errors.append(f"docs/{guide_name}: missing consolidated source anchor for {source}")
        if f"Consolidated from `{source}`." not in text:
            errors.append(f"docs/{guide_name}: missing source provenance for {source}")
    return errors


def _check_roadmap_cards() -> list[str]:
    roadmap = ROOT / "docs" / "roadmap.md"
    if not roadmap.is_file():
        return []
    errors: list[str] = []
    text = roadmap.read_text(encoding="utf-8")
    for card_id in ROADMAP_CARDS:
        start_match = re.search(rf"^##### `{re.escape(card_id)}` .+ card\s*$", text, re.MULTILINE)
        if start_match is None:
            errors.append(f"docs/roadmap.md: missing execution/validation card for {card_id}")
            continue
        next_match = re.search(r"^##### `[^`]+` .+ card\s*$", text[start_match.end() :], re.MULTILINE)
        end = start_match.end() + next_match.start() if next_match else len(text)
        card = text[start_match.start() : end]
        if "**Validation:**" not in card or "**Stop condition:**" not in card:
            errors.append(f"docs/roadmap.md: incomplete validation/stop contract for {card_id}")
        has_implementation = "**Implementation:**" in card or "**Post-approval implementation:**" in card
        if card_id not in {"BUG-CDC-01", "QUALITY-01"} and not has_implementation:
            errors.append(f"docs/roadmap.md: incomplete implementation contract for {card_id}")
    return errors


def check_document_consolidation() -> list[str]:
    errors: list[str] = []
    docs_root = ROOT / "docs"
    expected = {"README.md", *CONSOLIDATED_GUIDES}
    actual = {path.name for path in docs_root.glob("*.md")}
    if actual != expected:
        errors.append(
            f"docs: flat guide set mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    nested = sorted(path.relative_to(ROOT).as_posix() for path in docs_root.glob("*/*.md"))
    if nested:
        errors.append(f"docs: nested Markdown is not allowed after consolidation: {nested}")

    for guide_name, sources in CONSOLIDATED_GUIDES.items():
        errors.extend(_check_consolidated_guide(guide_name, sources))
    return [*errors, *_check_roadmap_cards()]


def _logical_commands(block: str) -> tuple[str, ...]:
    lines: list[str] = []
    current = ""
    for raw in block.splitlines():
        line = raw.removeprefix("$ ").strip()
        if not line or line.startswith("#"):
            continue
        current += (" " if current else "") + line.removesuffix("\\").strip()
        if not line.endswith("\\"):
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return tuple(lines)


def check_cli_examples() -> list[str]:
    errors: list[str] = []
    parser = build_parser()
    for document in MARKDOWN:
        for block in FENCE.findall(document.read_text(encoding="utf-8")):
            for command in _logical_commands(block):
                try:
                    tokens = shlex.split(command)
                except ValueError as error:
                    errors.append(f"{document.relative_to(ROOT)}: invalid shell example: {error}")
                    continue
                if tokens[:3] == ["uv", "run", "dv-platform"]:
                    tokens = tokens[2:]
                if not tokens or tokens[0] != "dv-platform":
                    continue
                if any(token in {"|", "&&", ";"} for token in tokens):
                    continue
                try:
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        parser.parse_args(tokens[1:])
                except SystemExit as exit_error:
                    if exit_error.code != 0:
                        errors.append(f"{document.relative_to(ROOT)}: invalid CLI example: {command}")
    return errors


def check_schema_versions() -> list[str]:
    errors: list[str] = []
    matrix_path = ROOT / "docs" / "verification.md"
    matrix = _source_section(matrix_path, "source-docsqualificationcapability-matrixmd")
    expected = (
        (f"Plan schema v{PLAN_SCHEMA_VERSION}", "plan"),
        (f"Immutable revisions v{PLAN_REVISION_SCHEMA_VERSION}", "revision"),
        (f"RTL facts v{RTL_FACTS_SCHEMA_VERSION}", "RTL facts"),
    )
    for text, label in expected:
        if text not in matrix:
            errors.append(f"docs/verification.md: stale {label} schema version; expected {text!r}")
    for schema in sorted((ROOT / "schemas").glob("*/*.schema.json")):
        payload = json.loads(schema.read_text(encoding="utf-8"))
        version = payload.get("properties", {}).get("schema_version", {}).get("const")
        match = re.search(r"-v(\d+)\.schema\.json$", schema.name)
        if match and version != int(match.group(1)):
            errors.append(f"{schema.relative_to(ROOT)}: filename version and schema_version const disagree")
    return errors


def check_capability_matrix() -> list[str]:
    matrix_path = ROOT / "docs" / "verification.md"
    text = _source_section(matrix_path, "source-docsqualificationcapability-matrixmd")
    errors: list[str] = []
    if "status --check" in text or "status --check" in (ROOT / "docs" / "operations.md").read_text():
        errors.append("documentation references nonexistent status --check")
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if cells and cells[0] in {"Target", "Profile", "Capability"}:
            continue
        state_cells = [cell for cell in cells if any(cell.startswith(state) for state in CAPABILITY_STATES)]
        if len(cells) >= 3 and not state_cells:
            errors.append(f"docs/verification.md: capability row has no recognized state: {cells[0]}")
    return errors


def check_capability_ledger(root: Path = ROOT) -> list[str]:  # noqa: C901
    """Validate the current capability authority and its documented state."""

    path = root / "qualification" / "policies" / "capability-ledger-v1.json"
    errors: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path.relative_to(root)}: capability ledger is unreadable: {error}"]
    if value.get("schema_version") != 1 or value.get("authority") != "current":
        errors.append("qualification/policies/capability-ledger-v1.json: unsupported authority/schema")
    entries = value.get("cells")
    if not isinstance(entries, list) or not entries:
        return [*errors, "qualification/policies/capability-ledger-v1.json: cells must be non-empty"]
    expected_profiles = {
        "axi4-1.0": (("subordinate", "manager"), 256, 16, 32),
        "axi4-stream-1.0": (("source", "sink"), 65536, 1, 32),
        "wishbone-b4-1.0": (("device", "host"), 256, 16, 32),
        "avalon-mm-1.0": (("agent", "host"), 256, 16, 32),
        "avalon-st-1.0": (("sink", "source"), 65536, 1, 32),
        "ahb-1.0": (("subordinate", "manager"), 256, 1, 32),
        "tilelink-ul-uh-1.0": (("subordinate", "manager"), 256, 16, 32),
    }
    targets = {"cocotb", "formal", "systemverilog", "verilog", "vhdl", "uvm"}
    cells: set[tuple[str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("capability ledger: cell entry is not an object")
            continue
        identifier = str(entry.get("profile_id"))
        role = str(entry.get("role"))
        target = str(entry.get("target"))
        cell = (identifier, role, target)
        if cell in cells:
            errors.append(f"capability ledger: duplicate profile/role/target cell: {cell!r}")
        cells.add(cell)
        expected = expected_profiles.get(identifier)
        if expected is None:
            errors.append(f"capability ledger: unknown profile cell: {cell!r}")
        elif role not in expected[0] or target not in targets:
            errors.append(f"capability ledger: unknown role or target cell: {cell!r}")
        bound = entry.get("bound")
        expected_bound = (
            {
                "maximum_burst_length": expected[1],
                "maximum_outstanding": expected[2],
                "timeout_cycles": expected[3],
            }
            if expected is not None
            else None
        )
        if bound != expected_bound:
            errors.append(f"capability ledger: role/bound/version mismatch: {cell!r}")
        if entry.get("profile_version") != "1.0":
            errors.append(f"capability ledger: role/bound/version mismatch: {cell!r}")
        state = entry.get("state")
        if state not in CAPABILITY_STATES | {"contract_verified", "regressed"}:
            errors.append(f"capability ledger: invalid state for {cell!r}")
        source = entry.get("source")
        if not isinstance(source, str) or "#" not in source:
            errors.append(f"capability ledger: {cell!r} lacks an evidence-addressed source")
        elif not _has_anchor(root / source.split("#", 1)[0], source.split("#", 1)[1]):
            errors.append(f"capability ledger: {cell!r} source anchor is missing: {source}")
        digest = entry.get("evidence_digest")
        source_identity = entry.get("last_passing_source")
        if state == "supported" and (not isinstance(digest, str) or not isinstance(source_identity, str)):
            errors.append(f"capability ledger: supported cell lacks passing evidence identity: {cell!r}")
        if state in {"unsupported", "scaffold"} and (digest is not None or source_identity is not None):
            errors.append(f"capability ledger: non-executable cell must not cite passing evidence: {cell!r}")
    expected_cells = {
        (profile_id, role, target)
        for profile_id, details in expected_profiles.items()
        for role in details[0]
        for target in targets
    }
    for missing in sorted(expected_cells - cells):
        errors.append(f"capability ledger: missing declared runtime cell: {missing!r}")
    matrix = _source_section(root / "docs" / "verification.md", "source-docsqualificationcapability-matrixmd")
    broad_row = next((line for line in matrix.splitlines() if "Broad protocol profiles v1" in line), "")
    if "`partial`" not in broad_row:
        errors.append("docs/verification.md: broad protocol row contradicts the capability ledger")
    return errors


def check_document_catalog(root: Path = ROOT) -> list[str]:
    """Validate document authority, consolidated-source identity, and progress ordering."""

    errors: list[str] = []
    path = root / "qualification" / "policies" / "document-catalog-v1.json"
    progress_path = root / "qualification" / "policies" / "progress-ledger-v1.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"documentation governance data is unreadable: {error}"]
    documents = catalog.get("documents")
    expected_paths = {item.relative_to(root).as_posix() for item in MARKDOWN}
    actual_paths = (
        {str(item.get("path")) for item in documents if isinstance(item, dict)}
        if isinstance(documents, list)
        else set()
    )
    if actual_paths != expected_paths or len(actual_paths) != 12:
        errors.append("document catalog must classify exactly the 12 maintained Markdown files")
    ledger = json.loads((root / "qualification" / "policies" / "capability-ledger-v1.json").read_text(encoding="utf-8"))
    capability_ids = {str(item) for item in ROADMAP_CARDS}
    capability_ids.update(str(cell.get("profile_id")) for cell in ledger.get("cells", ()) if isinstance(cell, dict))
    for item in documents if isinstance(documents, list) else ():
        if not isinstance(item, dict):
            errors.append("document catalog entry is not an object")
            continue
        document = root / str(item.get("path"))
        anchor = str(item.get("stable_anchor", "")).removeprefix("#")
        if not document.is_file() or not anchor or not _has_anchor(document, anchor):
            errors.append(f"document catalog has missing path/anchor: {item.get('path')}#{anchor}")
        if any(str(identifier) not in capability_ids for identifier in item.get("capability_ids", ())):
            errors.append(f"document catalog cites an unknown capability: {item.get('path')}")
        successor = item.get("successor")
        if successor:
            successor_path, _, successor_anchor = str(successor).partition("#")
            if not (root / successor_path).is_file() or (
                successor_anchor and not _has_anchor(root / successor_path, successor_anchor)
            ):
                errors.append(f"document catalog successor is missing: {successor}")
    sources = [(guide, source) for guide, items in CONSOLIDATED_GUIDES.items() for source in items]
    digest = hashlib.sha256(json.dumps(sources, separators=(",", ":")).encode("utf-8")).hexdigest()
    inventory = catalog.get("source_inventory", {})
    if inventory.get("count") != 70 or inventory.get("sha256") != digest:
        errors.append("document catalog consolidated-source inventory is stale")
    errors.extend(_progress_transition_errors(progress, root))
    return errors


def _progress_transition_errors(progress: object, root: Path) -> list[str]:
    if not isinstance(progress, dict) or progress.get("schema_version") != 1:
        return ["progress ledger schema version is unsupported"]
    allowed = {
        ("open", "in_progress"),
        ("in_progress", "closed"),
        ("closed", "regressed"),
        ("regressed", "open"),
    }
    errors: list[str] = []
    latest: dict[str, tuple[int, str]] = {}
    for transition in progress.get("transitions", ()):
        if not isinstance(transition, dict):
            errors.append("progress transition is not an object")
            continue
        ticket = str(transition.get("ticket"))
        sequence = transition.get("sequence")
        edge = (transition.get("from"), transition.get("to"))
        previous = latest.get(ticket)
        if edge not in allowed or not isinstance(sequence, int):
            errors.append(f"progress transition is invalid: {ticket}")
        elif previous is not None and (sequence != previous[0] + 1 or edge[0] != previous[1]):
            errors.append(f"progress transition ordering is invalid: {ticket}")
        latest[ticket] = (sequence if isinstance(sequence, int) else 0, str(edge[1]))
        evidence = transition.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not (root / str(item)).exists() for item in evidence):
            errors.append(f"progress transition evidence is missing: {ticket}")
    return errors


def main() -> int:
    errors = [
        *check_internal_links(),
        *check_document_consolidation(),
        *check_cli_examples(),
        *check_schema_versions(),
        *check_capability_matrix(),
        *check_capability_ledger(),
        *check_document_catalog(),
    ]
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"repository contracts passed ({len(MARKDOWN)} Markdown files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
