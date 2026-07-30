"""Create and verify the immutable build-once release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any


class ReleaseManifestError(ValueError):
    """Raised for release subject substitution or context mismatch."""


def create_manifest(directory: Path, root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    directory = directory.resolve(strict=True)
    version = str(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
    commit = _git(root, "rev-parse", "HEAD")
    subjects = _subjects(directory, output)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "repository": os.environ.get("GITHUB_REPOSITORY", "local/veriforge"),
        "ref": os.environ.get("GITHUB_REF", "local"),
        "tag": os.environ.get("GITHUB_REF_NAME", f"v{version}"),
        "commit": commit,
        "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
        "workflow_sha256": _sha256(root / ".github" / "workflows" / "release.yml"),
        "lockfile_sha256": _sha256(root / "uv.lock"),
        "package": {"name": "dv-platform", "version": version},
        "subjects": subjects,
    }
    payload["manifest_sha256"] = _payload_digest(payload)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def verify_manifest(
    path: Path,
    directory: Path,
    *,
    root: Path,
    expected_commit: str | None = None,
    expected_tag: str | None = None,
    expected_repository: str | None = None,
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ReleaseManifestError("unsupported release manifest")
    if value.get("manifest_sha256") != _payload_digest(value):
        raise ReleaseManifestError("release manifest digest mismatch")
    if expected_commit is not None and value.get("commit") != expected_commit:
        raise ReleaseManifestError("release manifest commit mismatch")
    if expected_tag is not None and value.get("tag") != expected_tag:
        raise ReleaseManifestError("release manifest tag mismatch")
    if expected_repository is not None and value.get("repository") != expected_repository:
        raise ReleaseManifestError("release manifest repository mismatch")
    root = root.resolve(strict=True)
    if value.get("commit") != _git(root, "rev-parse", "HEAD"):
        raise ReleaseManifestError("release manifest does not match checkout")
    expected = _subjects(directory.resolve(strict=True), path)
    if value.get("subjects") != expected:
        raise ReleaseManifestError("release manifest subjects differ from build directory")
    return value


def _subjects(directory: Path, excluded: Path) -> dict[str, str]:
    return {
        file.name: _sha256(file)
        for file in sorted(directory.iterdir(), key=lambda item: item.name)
        if file.is_file()
        and not file.is_symlink()
        and file.resolve() != excluded.resolve()
        and (file.name.endswith(".whl") or file.name.endswith(".tar.gz"))
    }


def _payload_digest(value: dict[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("manifest_sha256", None)
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(("git", *args), cwd=root, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise ReleaseManifestError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-tag")
    args = parser.parse_args()
    try:
        if args.command == "create":
            create_manifest(args.directory, args.root, args.manifest)
        else:
            verify_manifest(
                args.manifest,
                args.directory,
                root=args.root,
                expected_commit=args.expected_commit,
                expected_tag=args.expected_tag,
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    print("release manifest verified" if args.command == "verify" else f"release manifest written: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
