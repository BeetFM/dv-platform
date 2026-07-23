"""Generate an in-toto SLSA provenance statement for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    subjects = []
    for path in sorted(args.artifact_dir.iterdir()):
        if (
            not path.is_file()
            or path.is_symlink()
            or path.name.startswith(".")
            or path.resolve(strict=False) == args.output.resolve(strict=False)
        ):
            continue
        subjects.append({"name": path.name, "digest": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}})
    root = Path(__file__).resolve().parents[2]
    repository = os.environ.get("GITHUB_REPOSITORY", "local/veriforge")
    commit = os.environ.get("GITHUB_SHA") or _git_commit(root)
    lock_digest = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://veriforge.dev/build-types/python-wheel/v1",
                "externalParameters": {
                    "ref": os.environ.get("GITHUB_REF", "local"),
                    "tag": os.environ.get("GITHUB_REF_NAME", "local"),
                },
                "internalParameters": {"lockfileSha256": lock_digest, "buildCommand": "uv build"},
                "resolvedDependencies": [
                    {"uri": f"git+https://github.com/{repository}", "digest": {"gitCommit": commit}}
                ],
            },
            "runDetails": {
                "builder": {"id": f"https://github.com/{repository}/actions/workflows/release.yml"},
                "metadata": {"invocationId": os.environ.get("GITHUB_RUN_ID", "local")},
            },
        },
    }
    args.output.write_text(json.dumps(statement, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=root, check=False, capture_output=True, text=True, timeout=30
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 else "0" * 40


if __name__ == "__main__":
    raise SystemExit(main())
