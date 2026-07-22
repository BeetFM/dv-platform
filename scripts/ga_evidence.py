"""Create and verify clean-checkout, commit-bound GA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def generate(stage: int, root: Path, test_log: Path, coverage: Path, artifacts: Path, output: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not 6 <= stage <= 13:
        raise ValueError("GA evidence stage must be 6..13")
    if _git(root, "status", "--porcelain"):
        raise ValueError("GA evidence requires a clean checkout")
    commit = _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("GA evidence requires a resolved commit")
    log = test_log.read_text(encoding="utf-8", errors="replace")
    matches = tuple(re.finditer(r"Ran\s+(\d+)\s+tests?.*?\n\n(OK[^\n]*)", log, re.DOTALL))
    if not matches:
        raise ValueError("GA evidence cannot find a passing unittest summary")
    tests = int(matches[-1].group(1))
    summary = matches[-1].group(2)
    skipped_match = re.search(r"skipped=(\d+)", summary)
    coverage_json = json.loads(coverage.read_text(encoding="utf-8"))
    totals = coverage_json.get("totals") if isinstance(coverage_json, dict) else None
    if not isinstance(totals, dict):
        raise ValueError("GA evidence coverage totals are missing")
    combined = float(totals.get("percent_covered", -1))
    branches = int(totals.get("num_branches", 0))
    covered_branches = int(totals.get("covered_branches", -1))
    branch_percentage = 100.0 * covered_branches / branches if branches else 100.0
    artifact_digests = {
        path.relative_to(artifacts).as_posix(): _sha256(path)
        for path in sorted(artifacts.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    if not artifact_digests:
        raise ValueError("GA evidence requires generated artifacts")
    workflow = root / ".github" / "workflows" / "ci.yml"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "stage": stage,
        "commit": commit,
        "source_tree_sha256": _tree_digest(root),
        "workflow_sha256": _sha256(workflow),
        "lockfile_sha256": _sha256(root / "uv.lock"),
        "tests": {
            "passed": tests - (int(skipped_match.group(1)) if skipped_match else 0),
            "skipped": int(skipped_match.group(1)) if skipped_match else 0,
            "failed": 0,
        },
        "coverage": {"combined": combined, "branch": branch_percentage},
        "tools": {"python": _version(("python", "--version")), "uv": _version(("uv", "--version"))},
        "artifacts": artifact_digests,
        "status": "passed",
    }
    payload["evidence_sha256"] = _payload_digest(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def verify(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("status") != "passed":
        raise ValueError("invalid GA evidence identity or status")
    expected = value.get("evidence_sha256")
    if expected != _payload_digest(value):
        raise ValueError("GA evidence digest mismatch")
    for field, width in (("commit", 40), ("source_tree_sha256", 64), ("workflow_sha256", 64), ("lockfile_sha256", 64)):
        if re.fullmatch(rf"[0-9a-f]{{{width}}}", str(value.get(field, ""))) is None:
            raise ValueError(f"GA evidence {field} is invalid")
    tests = value.get("tests")
    coverage = value.get("coverage")
    if not isinstance(tests, dict) or tests.get("failed") != 0 or int(tests.get("passed", 0)) < 1:
        raise ValueError("GA evidence test result is incomplete")
    if not isinstance(coverage, dict) or not all(
        isinstance(coverage.get(name), (int, float)) for name in ("combined", "branch")
    ):
        raise ValueError("GA evidence coverage result is incomplete")
    if not isinstance(value.get("artifacts"), dict) or not value["artifacts"]:
        raise ValueError("GA evidence artifact identities are incomplete")
    return value


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(("git", *arguments), cwd=root, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _version(command: tuple[str, ...]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    value = (result.stdout or result.stderr).strip().splitlines()
    return value[0] if result.returncode == 0 and value else f"exit-{result.returncode}"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in _git(root, "ls-files", "-z").split("\0"):
        if not relative:
            continue
        path = root / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_digest(value: dict[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("evidence_sha256", None)
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--stage", type=int, required=True)
    create.add_argument("--root", type=Path, default=Path.cwd())
    create.add_argument("--test-log", type=Path, required=True)
    create.add_argument("--coverage", type=Path, required=True)
    create.add_argument("--artifacts", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("verify")
    check.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            generate(args.stage, args.root, args.test_log, args.coverage, args.artifacts, args.output)
        else:
            verify(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    print("GA evidence verified" if args.command == "verify" else f"GA evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
