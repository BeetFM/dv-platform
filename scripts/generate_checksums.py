"""Generate deterministic basename-only SHA-256 records for release files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def generate_checksums(directory: Path, output: Path) -> tuple[str, ...]:
    root = directory.resolve(strict=True)
    destination = output.resolve(strict=False)
    subjects = tuple(
        sorted(
            (
                path
                for path in root.iterdir()
                if path.is_file()
                and not path.is_symlink()
                and not path.name.startswith(".")
                and path.resolve(strict=False) != destination
                and path.name != "provenance.intoto.json"
                and not path.name.endswith(".sigstore.json")
            ),
            key=lambda path: path.name,
        )
    )
    if not subjects:
        raise ValueError("release directory contains no checksum subjects")
    output.write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in subjects),
        encoding="utf-8",
    )
    return tuple(path.name for path in subjects)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        subjects = generate_checksums(args.artifact_dir, args.output)
    except (OSError, ValueError) as error:
        print(error)
        return 1
    print(f"checksums generated ({len(subjects)} subjects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
