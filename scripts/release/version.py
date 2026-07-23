"""Enforce exact tag, package, and generated filename version consistency."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = str(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
    expected = args.tag.removeprefix("v")
    errors: list[str] = []
    if expected != version:
        errors.append(f"release tag {args.tag} does not match project version {version}")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?", version) is None:
        errors.append(f"unsupported release version shape: {version}")
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
