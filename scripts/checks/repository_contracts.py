"""Check documentation links, CLI examples, schemas, and capability vocabulary."""

from __future__ import annotations

import io
import json
import re
import shlex
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from dv_platform.cli import build_parser
from dv_platform.core.schema import PLAN_REVISION_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = tuple(sorted((*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md"))))
LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")
FENCE = re.compile(r"```(?:bash|console|shell)\n(.*?)```", re.DOTALL)
CAPABILITY_STATES = {"supported", "partial", "scaffold", "unsupported"}


def check_internal_links() -> list[str]:
    errors: list[str] = []
    for document in MARKDOWN:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            target = target.split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_text = target.split("#", 1)[0]
            if path_text and not (document.parent / path_text).resolve(strict=False).exists():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")
    return errors


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
    matrix = (ROOT / "docs/capability-matrix.md").read_text(encoding="utf-8")
    expected = (
        (f"Plan schema v{PLAN_SCHEMA_VERSION}", "plan"),
        (f"Immutable revisions v{PLAN_REVISION_SCHEMA_VERSION}", "revision"),
        (f"RTL facts v{RTL_FACTS_SCHEMA_VERSION}", "RTL facts"),
    )
    for text, label in expected:
        if text not in matrix:
            errors.append(f"docs/capability-matrix.md: stale {label} schema version; expected {text!r}")
    for schema in sorted((ROOT / "schemas").glob("*.schema.json")):
        payload = json.loads(schema.read_text(encoding="utf-8"))
        version = payload.get("properties", {}).get("schema_version", {}).get("const")
        match = re.search(r"-v(\d+)\.schema\.json$", schema.name)
        if match and version != int(match.group(1)):
            errors.append(f"{schema.relative_to(ROOT)}: filename version and schema_version const disagree")
    return errors


def check_capability_matrix() -> list[str]:
    matrix_path = ROOT / "docs/capability-matrix.md"
    text = matrix_path.read_text(encoding="utf-8")
    errors: list[str] = []
    if "status --check" in text or "status --check" in (ROOT / "docs/production-closure-runbook.md").read_text():
        errors.append("documentation references nonexistent status --check")
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if cells and cells[0] in {"Target", "Profile", "Capability"}:
            continue
        state_cells = [cell for cell in cells if any(cell.startswith(state) for state in CAPABILITY_STATES)]
        if len(cells) >= 3 and not state_cells:
            errors.append(f"docs/capability-matrix.md: row has no recognized state: {cells[0]}")
    return errors


def main() -> int:
    errors = [*check_internal_links(), *check_cli_examples(), *check_schema_versions(), *check_capability_matrix()]
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"repository contracts passed ({len(MARKDOWN)} Markdown files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
