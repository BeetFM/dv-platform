"""Check documentation links, CLI examples, schemas, and capability vocabulary."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shlex
import sys
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from dv_platform.cli import build_parser
from dv_platform.core.schema import PLAN_REVISION_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.enterprise.cli import build_parser as build_enterprise_parser

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
    value = unicodedata.normalize("NFKC", re.sub(r"[`*_~]", "", value).strip().lower())
    value = "".join(character for character in value if character.isalnum() or character in " _-")
    value = re.sub(r"[ _]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def _source_anchor(source: str) -> str:
    return f"source-{_slug(source)}"


def _has_anchor(document: Path, fragment: str) -> bool:
    text = document.read_text(encoding="utf-8")
    if f'id="{fragment}"' in text:
        return True
    counts: dict[str, int] = {}
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.MULTILINE):
        base = _slug(match.group(1))
        count = counts.get(base, 0)
        counts[base] = count + 1
        if fragment == (base if count == 0 else f"{base}-{count}"):
            return True
    return False


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


def _safe_repo_path(root: Path, value: object) -> Path | None:
    """Resolve an evidence/document path without accepting escapes or symlinks."""

    if not isinstance(value, str) or not value or "#" in value:
        return None
    candidate = root / value
    resolved_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    if resolved_root not in (resolved, *resolved.parents):
        return None
    relative = candidate.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            return None
    return candidate if candidate.exists() else None


def check_internal_links(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    markdown = tuple(sorted((*root.glob("*.md"), *root.glob("docs/**/*.md"))))
    for document in markdown:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            target = target.split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            path_text = target.split("#", 1)[0]
            target_path = (document.parent / path_text).resolve(strict=False) if path_text else document
            if path_text and not target_path.exists():
                errors.append(f"{document.relative_to(root)}: broken link {target}")
                continue
            fragment = unquote(target.partition("#")[2])
            if fragment and target_path.is_file() and not _has_anchor(target_path, fragment):
                errors.append(f"{document.relative_to(root)}: broken anchor {target}")
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
    source_list = text.partition("## Source coverage\n")[2].partition('\n<a id="source-')[0]
    if source_list.strip() + "\n" != render_source_coverage(sources):
        errors.append(f"docs/{guide_name}: generated source-coverage list is stale")
    return errors


def render_source_coverage(sources: tuple[str, ...]) -> str:
    """Render one deterministic consolidated-guide source list."""

    lines = (
        "Every source below is included in full under a stable migration anchor:",
        "",
        *(f"- [`{source}`](#{_source_anchor(source)})" for source in sources),
    )
    return "\n".join(lines) + "\n"


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


def _logical_commands(block: str) -> tuple[tuple[str, bool], ...]:
    lines: list[tuple[str, bool]] = []
    current = ""
    expected_invalid = False
    for raw in block.splitlines():
        line = raw.removeprefix("$ ").strip()
        if line == "# expected-invalid":
            expected_invalid = True
            continue
        if not line or line.startswith("#"):
            continue
        current += (" " if current else "") + line.removesuffix("\\").strip()
        if not line.endswith("\\"):
            lines.append((current, expected_invalid))
            current = ""
            expected_invalid = False
    if current:
        lines.append((current, expected_invalid))
    return tuple(lines)


def _command_segments(tokens: list[str]) -> tuple[list[str], ...]:
    segments: list[list[str]] = [[]]
    skip_redirect_target = False
    for token in tokens:
        if skip_redirect_target:
            skip_redirect_target = False
            continue
        if token in {"|", "||", "&&", ";"}:
            if segments[-1]:
                segments.append([])
            continue
        if token in {">", ">>", "<", "1>", "1>>", "2>", "2>>"}:
            skip_redirect_target = True
            continue
        if token.startswith((">", "1>", "2>")):
            continue
        segments[-1].append(token)
    return tuple(segment for segment in segments if segment)


def _public_command_error(tokens: list[str], root: Path) -> str | None:
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return None
    for command, parser in (("dv-platform", build_parser()), ("dv-enterprise", build_enterprise_parser())):
        if command not in tokens:
            continue
        command_tokens = tokens[tokens.index(command) :]
        if any("<" in token or ">" in token for token in command_tokens):
            return None
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                parser.parse_args(command_tokens[1:])
        except SystemExit as exit_error:
            if exit_error.code != 0:
                return f"invalid {command} arguments"
        return None
    script = next((token for token in tokens if token.startswith("scripts/") and token.endswith(".py")), None)
    if script is not None:
        path = (root / script).resolve(strict=False)
        if root.resolve(strict=False) not in (path, *path.parents) or not path.is_file():
            return f"missing public script {script}"
    return None


def check_cli_examples(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    markdown = tuple(sorted((*root.glob("*.md"), *root.glob("docs/**/*.md"))))
    for document in markdown:
        for block in FENCE.findall(document.read_text(encoding="utf-8")):
            for command, expected_invalid in _logical_commands(block):
                try:
                    tokens = shlex.split(command)
                except ValueError as error:
                    if not expected_invalid:
                        errors.append(f"{document.relative_to(root)}: invalid shell example: {error}")
                    continue
                command_errors = [
                    error for segment in _command_segments(tokens) if (error := _public_command_error(segment, root))
                ]
                if expected_invalid:
                    if not command_errors:
                        errors.append(f"{document.relative_to(root)}: expected-invalid command parses: {command}")
                elif command_errors:
                    errors.append(f"{document.relative_to(root)}: {command_errors[0]}: {command}")
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


def _catalog_document_entry_errors(root: Path, item: dict[str, object], capability_ids: set[str]) -> list[str]:
    errors: list[str] = []
    document = _safe_repo_path(root, item.get("path"))
    anchor = str(item.get("stable_anchor", "")).removeprefix("#")
    if document is None or not document.is_file() or not anchor or not _has_anchor(document, anchor):
        errors.append(f"document catalog has missing path/anchor: {item.get('path')}#{anchor}")
    if any(str(identifier) not in capability_ids for identifier in item.get("capability_ids", ())):
        errors.append(f"document catalog cites an unknown capability: {item.get('path')}")
    required_metadata = {
        "path",
        "class",
        "authority",
        "scope",
        "status",
        "effective_date",
        "supersedes",
        "successor",
        "known_issues",
        "capability_ids",
        "schema_ids",
        "command_families",
        "evidence",
        "stable_anchor",
    }
    if set(item) != required_metadata:
        errors.append(f"document catalog metadata is not closed: {item.get('path')}")
    expected_status = {
        "current_authority": "current",
        "historical_log": "historical",
        "legal_notice": "legal",
    }.get(item.get("class"))
    if (
        item.get("status") != expected_status
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item.get("effective_date"))) is None
    ):
        errors.append(f"document catalog class/status/date is invalid: {item.get('path')}")
    for field in ("supersedes", "known_issues", "capability_ids", "schema_ids", "command_families", "evidence"):
        values = item.get(field)
        if not isinstance(values, list) or len(values) != len(set(map(str, values))):
            errors.append(f"document catalog {field} metadata is invalid: {item.get('path')}")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or any(_safe_repo_path(root, reference) is None for reference in evidence):
        errors.append(f"document catalog evidence is missing: {item.get('path')}")
    successor = item.get("successor")
    if successor:
        successor_path, _, successor_anchor = str(successor).partition("#")
        resolved_successor = _safe_repo_path(root, successor_path)
        if (
            resolved_successor is None
            or not resolved_successor.is_file()
            or (successor_anchor and not _has_anchor(resolved_successor, successor_anchor))
        ):
            errors.append(f"document catalog successor is missing: {successor}")
    return errors


def _catalog_document_errors(root: Path, catalog: dict[str, object]) -> list[str]:
    errors: list[str] = []
    documents = catalog.get("documents")
    markdown = tuple(sorted((*root.glob("*.md"), *root.glob("docs/**/*.md"))))
    expected_paths = {item.relative_to(root).as_posix() for item in markdown}
    actual_paths = (
        {str(item.get("path")) for item in documents if isinstance(item, dict)}
        if isinstance(documents, list)
        else set()
    )
    if actual_paths != expected_paths or len(actual_paths) != 12:
        errors.append("document catalog must classify exactly the 12 maintained Markdown files")
    if len({path.casefold() for path in actual_paths}) != len(actual_paths):
        errors.append("document catalog has case-colliding document paths")
    ledger = json.loads((root / "qualification" / "policies" / "capability-ledger-v1.json").read_text(encoding="utf-8"))
    capability_ids = {str(item) for item in ROADMAP_CARDS}
    capability_ids.update(str(cell.get("profile_id")) for cell in ledger.get("cells", ()) if isinstance(cell, dict))
    for item in documents if isinstance(documents, list) else ():
        if isinstance(item, dict):
            errors.extend(_catalog_document_entry_errors(root, item, capability_ids))
        else:
            errors.append("document catalog entry is not an object")
    return errors


def _catalog_source_errors(root: Path, catalog: dict[str, object]) -> list[str]:
    errors: list[str] = []
    sources = [(guide, source) for guide, items in CONSOLIDATED_GUIDES.items() for source in items]
    digest = hashlib.sha256(json.dumps(sources, separators=(",", ":")).encode("utf-8")).hexdigest()
    inventory = catalog.get("source_inventory", {})
    if inventory.get("count") != 70 or inventory.get("sha256") != digest:
        errors.append("document catalog consolidated-source inventory is stale")
    expected_sources = {
        (source, f"docs/{guide}", f"#{_source_anchor(source)}")
        for guide, items in CONSOLIDATED_GUIDES.items()
        for source in items
    }
    source_sections = catalog.get("source_sections")
    actual_sources: set[tuple[str, str, str]] = set()
    source_ids: set[str] = set()
    for item in source_sections if isinstance(source_sections, list) else ():
        if not isinstance(item, dict) or set(item) != {"source_id", "guide", "anchor", "class", "status"}:
            errors.append("document catalog source-section metadata is not closed")
            continue
        identity = (str(item["source_id"]), str(item["guide"]), str(item["anchor"]))
        if identity in actual_sources:
            errors.append(f"document catalog has duplicate source section: {identity[0]}")
        actual_sources.add(identity)
        folded = identity[0].casefold()
        if folded in source_ids:
            errors.append(f"document catalog has case-colliding source ID: {identity[0]}")
        source_ids.add(folded)
        guide_path = _safe_repo_path(root, identity[1])
        if guide_path is None or not _has_anchor(guide_path, identity[2].removeprefix("#")):
            errors.append(f"document catalog source anchor is missing: {identity[1]}{identity[2]}")
        if item.get("class") in {"historical_snapshot", "historical_log"} and item.get("status") != "preserved":
            errors.append(f"historical source is not marked preserved: {identity[0]}")
    if actual_sources != expected_sources or len(actual_sources) != 70:
        errors.append("document catalog must classify exactly all 70 consolidated source sections")
    return errors


def _generated_document_index_errors(root: Path, catalog: dict[str, object]) -> list[str]:
    index = (root / "docs" / "README.md").read_text(encoding="utf-8")
    marker = "<!-- generated: document-catalog-v1 -->"
    end_marker = "<!-- /generated: document-catalog-v1 -->"
    if marker not in index or end_marker not in index:
        return ["docs/README.md lacks the generated document catalog"]
    embedded = index.partition(marker)[2].partition(end_marker)[0].strip() + "\n"
    return [] if embedded == render_document_index(catalog) else ["docs/README.md generated document catalog is stale"]


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
    if not isinstance(catalog, dict):
        return ["document catalog root is not an object"]
    if set(catalog) != {"schema_version", "authority", "source_inventory", "documents", "source_sections"}:
        errors.append("document catalog root is not closed-schema")
    if catalog.get("schema_version") != 1 or catalog.get("authority") != path.relative_to(root).as_posix():
        errors.append("document catalog authority/schema is unsupported")
    errors.extend(_catalog_document_errors(root, catalog))
    errors.extend(_catalog_source_errors(root, catalog))
    errors.extend(_generated_document_index_errors(root, catalog))
    errors.extend(_progress_transition_errors(progress, root))
    errors.extend(check_local_task_audit(root))
    return errors


def render_local_task_audit(audit: object) -> str:
    """Render the current local-work view from its machine authority."""

    if not isinstance(audit, dict) or not isinstance(audit.get("tasks"), list):
        raise ValueError("local task audit is invalid")
    rows = sorted(
        (
            str(item.get("ticket")),
            str(item.get("local_work_state")),
            str(item.get("closure_blocker")),
        )
        for item in audit["tasks"]
        if isinstance(item, dict)
    )
    lines = (
        "| Ticket | Local work | Remaining closure blocker |",
        "| --- | --- | --- |",
        *(f"| `{ticket}` | `{state}` | `{blocker}` |" for ticket, state, blocker in rows),
    )
    return "\n".join(lines) + "\n"


def render_document_index(catalog: object) -> str:
    """Render the maintained physical-document index from the catalog."""

    if not isinstance(catalog, dict) or not isinstance(catalog.get("documents"), list):
        raise ValueError("document catalog is invalid")
    rows = sorted(
        (
            str(item.get("path")),
            str(item.get("class")),
            str(item.get("authority")),
        )
        for item in catalog["documents"]
        if isinstance(item, dict)
    )
    lines = (
        "| Path | Class | Authority |",
        "| --- | --- | --- |",
        *(f"| `{path}` | `{document_class}` | `{authority}` |" for path, document_class, authority in rows),
    )
    return "\n".join(lines) + "\n"


def _audit_entry_results(root: Path, tasks: object) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    actual: set[str] = set()
    must_be_closed: set[str] = set()
    for item in tasks if isinstance(tasks, list) else ():
        required = {"ticket", "local_work_state", "closure_blocker", "evidence"}
        if not isinstance(item, dict) or set(item) != required:
            errors.append("local task audit entry is not closed-schema")
            continue
        ticket = str(item["ticket"])
        if ticket in actual:
            errors.append(f"local task audit has duplicate ticket: {ticket}")
        actual.add(ticket)
        state = item.get("local_work_state")
        blocker = item.get("closure_blocker")
        if state not in {"completed", "regression_closed", "no_authorized_local_work", "pending_local"}:
            errors.append(f"local task audit state is invalid: {ticket}")
        if blocker not in {
            "none",
            "external_tool_evidence",
            "hosted_or_protected_evidence",
            "licensed_signed_evidence",
            "owner_decision",
        }:
            errors.append(f"local task audit blocker is invalid: {ticket}")
        if state == "no_authorized_local_work" and blocker == "none":
            errors.append(f"local task audit has unblocked unauthorized work: {ticket}")
        if state == "pending_local":
            errors.append(f"local task audit has unfinished repository-owned work: {ticket}")
        if state in {"completed", "regression_closed"} and blocker == "none":
            must_be_closed.add(ticket)
        evidence = item.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(_safe_repo_path(root, entry) is None for entry in evidence)
        ):
            errors.append(f"local task audit evidence is missing: {ticket}")
    return errors, actual, must_be_closed


def _latest_progress_states(root: Path) -> dict[str, str]:
    try:
        progress = json.loads(
            (root / "qualification" / "policies" / "progress-ledger-v1.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    latest: dict[str, tuple[int, str]] = {}
    for transition in progress.get("transitions", ()) if isinstance(progress, dict) else ():
        if isinstance(transition, dict) and isinstance(transition.get("sequence"), int):
            ticket = str(transition.get("ticket"))
            current = latest.get(ticket)
            if current is None or transition["sequence"] > current[0]:
                latest[ticket] = (transition["sequence"], str(transition.get("to")))
    return {ticket: state for ticket, (_sequence, state) in latest.items()}


def _generated_task_audit_errors(roadmap: str, audit: dict[str, object]) -> list[str]:
    marker = "<!-- generated: local-task-audit-v1 -->"
    end_marker = "<!-- /generated: local-task-audit-v1 -->"
    if marker not in roadmap or end_marker not in roadmap:
        return ["docs/roadmap.md lacks the generated local task audit"]
    embedded = roadmap.partition(marker)[2].partition(end_marker)[0].strip() + "\n"
    return [] if embedded == render_local_task_audit(audit) else ["docs/roadmap.md local task audit is stale"]


def check_local_task_audit(root: Path = ROOT) -> list[str]:
    """Require every current roadmap ticket to have a conservative local-work classification."""

    errors: list[str] = []
    path = root / "qualification" / "policies" / "local-task-audit-v1.json"
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"local task audit is unreadable: {error}"]
    if not isinstance(audit, dict):
        return ["local task audit root is not an object"]
    if set(audit) != {"schema_version", "audit_date", "scope", "tasks"} or audit.get("schema_version") != 1:
        errors.append("local task audit root is not closed-schema")
    if (
        audit.get("scope") != "all current roadmap tasks and all tracked Markdown"
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(audit.get("audit_date"))) is None
    ):
        errors.append("local task audit scope/date is invalid")
    roadmap = (root / "docs" / "roadmap.md").read_text(encoding="utf-8")
    pickup = roadmap.partition("| ID | Ready |")[2].partition("\n\nPickup rules:")[0]
    expected = set(re.findall(r"^\| `([A-Z]+(?:-[A-Z]+)*-[0-9]+)` \|", pickup, re.MULTILINE))
    entry_errors, actual, must_be_closed = _audit_entry_results(root, audit.get("tasks"))
    errors.extend(entry_errors)
    if actual != expected or len(actual) != 32:
        errors.append("local task audit must classify exactly every current roadmap ticket")
    latest = _latest_progress_states(root)
    for ticket in sorted(must_be_closed):
        if latest.get(ticket, "open") != "closed":
            errors.append(f"local task audit completion lacks a closed progress transition: {ticket}")
    errors.extend(_generated_task_audit_errors(roadmap, audit))
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
    seen: set[tuple[str, int]] = set()
    for transition in progress.get("transitions", ()):
        if not isinstance(transition, dict):
            errors.append("progress transition is not an object")
            continue
        ticket = str(transition.get("ticket"))
        sequence = transition.get("sequence")
        edge = (transition.get("from"), transition.get("to"))
        previous = latest.get(ticket)
        identity = (ticket, sequence) if isinstance(sequence, int) else (ticket, 0)
        if identity in seen:
            errors.append(f"progress transition sequence is duplicated: {ticket}")
        seen.add(identity)
        if (
            edge not in allowed
            or not isinstance(sequence, int)
            or re.fullmatch(r"[A-Z]+(?:-[A-Z]+)*-[0-9]+", ticket) is None
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(transition.get("date"))) is None
        ):
            errors.append(f"progress transition is invalid: {ticket}")
        elif previous is None and (sequence != 1 or edge[0] != "open"):
            errors.append(f"progress transition ordering is invalid: {ticket}")
        elif previous is not None and (sequence != previous[0] + 1 or edge[0] != previous[1]):
            errors.append(f"progress transition ordering is invalid: {ticket}")
        latest[ticket] = (sequence if isinstance(sequence, int) else 0, str(edge[1]))
        evidence = transition.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(_safe_repo_path(root, item) is None for item in evidence)
        ):
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
