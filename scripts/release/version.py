"""Enforce exact tag, package, and generated filename version consistency."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from scripts.release.release_policy import ReleasePolicyError, project_version, resolve_release
except ModuleNotFoundError as error:
    if error.name != "scripts":
        raise
    from release_policy import ReleasePolicyError, project_version, resolve_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    version = project_version(root)
    errors: list[str] = []
    try:
        resolve_release(args.tag, version)
    except ReleasePolicyError as error:
        errors.append(str(error))
    if args.dist is not None and args.dist.is_dir():
        artifacts = tuple(
            path.name for path in args.dist.iterdir() if path.suffix == ".whl" or path.name.endswith(".tar.gz")
        )
        normalized = version.replace("-", "_")
        if not artifacts or any(f"-{normalized}" not in name for name in artifacts):
            errors.append(f"distribution filenames do not all contain version {normalized}: {artifacts}")
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
