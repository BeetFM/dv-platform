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
    if len(matches) != 1:
        raise ValueError("GA evidence requires exactly one passing unittest summary")
    if re.search(r"(?:FAILED|ERROR|Traceback|interrupted)", log, re.IGNORECASE):
        raise ValueError("GA evidence test log contains a failure or interrupted run")
    tests = int(matches[0].group(1))
    summary = matches[0].group(2)
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


def verify_context(
    path: Path,
    *,
    root: Path,
    artifacts: Path,
    expected_stage: int | None = None,
    expected_commit: str | None = None,
    expected_workflow: Path | None = None,
    expected_lockfile: Path | None = None,
) -> dict[str, Any]:
    """Verify evidence against the checkout and artifact subjects it claims.

    ``verify`` checks the signed payload shape; this function checks whether the
    payload belongs to the candidate currently being qualified.  The two modes
    are intentionally separate so historical ledger inspection cannot be used
    accidentally as candidate evidence.
    """
    value = verify(path)
    root = root.resolve(strict=True)
    artifacts = artifacts.resolve(strict=True)
    if expected_stage is not None and value.get("stage") != expected_stage:
        raise ValueError(f"GA evidence stage mismatch: {value.get('stage')} != {expected_stage}")
    actual_commit = _git(root, "rev-parse", "HEAD")
    commit = expected_commit or actual_commit
    if value.get("commit") != commit:
        raise ValueError("GA evidence commit does not match candidate checkout")
    if value.get("source_tree_sha256") != _tree_digest(root):
        raise ValueError("GA evidence source tree digest does not match candidate checkout")
    workflow = expected_workflow or root / ".github" / "workflows" / "ci.yml"
    lockfile = expected_lockfile or root / "uv.lock"
    if value.get("workflow_sha256") != _sha256(workflow):
        raise ValueError("GA evidence workflow digest does not match candidate checkout")
    if value.get("lockfile_sha256") != _sha256(lockfile):
        raise ValueError("GA evidence lockfile digest does not match candidate checkout")
    claimed = value.get("artifacts")
    if not isinstance(claimed, dict) or not claimed:
        raise ValueError("GA evidence artifact identities are incomplete")
    actual: dict[str, str] = {}
    for subject in sorted(artifacts.rglob("*")):
        if subject.is_symlink():
            raise ValueError(f"GA evidence artifact is symlinked: {subject}")
        if subject.is_file():
            actual[subject.relative_to(artifacts).as_posix()] = _sha256(subject)
    if actual != claimed:
        missing = sorted(set(claimed) - set(actual))
        extra = sorted(set(actual) - set(claimed))
        changed = sorted(name for name in set(actual) & set(claimed) if actual[name] != claimed[name])
        details = ", ".join(
            part for part in (
                f"missing={missing}" if missing else "",
                f"extra={extra}" if extra else "",
                f"changed={changed}" if changed else "",
            ) if part
        )
        raise ValueError(f"GA evidence artifact subjects differ: {details}")
    return value


def create_candidate_bundle(
    *,
    root: Path,
    evidence: list[Path],
    output: Path,
    status: str = "passed",
    baseline: Path | None = None,
) -> dict[str, Any]:
    """Create a digest-bound manifest for candidate evidence components."""
    root = root.resolve(strict=True)
    commit = _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("candidate bundle requires a resolved commit")
    relative = [path.resolve().relative_to(output.parent.resolve()).as_posix() for path in evidence]
    payload: dict[str, Any] = {"schema_version": 1, "status": status, "commit": commit, "evidence": sorted(relative)}
    if baseline is not None:
        payload["baseline"] = baseline.resolve().relative_to(output.parent.resolve()).as_posix()
    payload["bundle_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


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
    check.add_argument("--root", type=Path)
    check.add_argument("--artifacts", type=Path)
    check.add_argument("--expected-stage", type=int)
    check.add_argument("--expected-commit")
    check.add_argument("--workflow", type=Path)
    check.add_argument("--lockfile", type=Path)
    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--root", type=Path, default=Path.cwd())
    bundle.add_argument("--evidence", type=Path, action="append", required=True)
    bundle.add_argument("--baseline", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            generate(args.stage, args.root, args.test_log, args.coverage, args.artifacts, args.output)
        elif args.command == "bundle":
            create_candidate_bundle(
                root=args.root, evidence=args.evidence, baseline=args.baseline, output=args.output
            )
        else:
            if (args.root is None) != (args.artifacts is None):
                raise ValueError("--root and --artifacts must be supplied together")
            if args.root is not None:
                verify_context(
                    args.input,
                    root=args.root,
                    artifacts=args.artifacts,
                    expected_stage=args.expected_stage,
                    expected_commit=args.expected_commit,
                    expected_workflow=args.workflow,
                    expected_lockfile=args.lockfile,
                )
            else:
                verify(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    print("GA evidence verified" if args.command == "verify" else f"GA evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
