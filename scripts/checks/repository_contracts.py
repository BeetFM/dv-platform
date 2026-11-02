"""Check current documentation links, PD command scope, and retained evidence integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote

from dv_platform.cli import build_parser
from dv_platform.enterprise.cli import build_parser as build_enterprise_parser
from dv_platform.enterprise.profiles import ENTERPRISE_TOOL_PROFILES

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = unicodedata.normalize("NFKC", re.sub(r"[`*_~]", "", value).strip().lower())
    value = "".join(character for character in value if character.isalnum() or character in " _-")
    value = re.sub(r"[ _]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


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


def _safe_repo_path(root: Path, value: object, *, require_exists: bool = True) -> Path | None:
    """Resolve an evidence/document path without accepting escapes or symlinks."""

    if (
        not isinstance(value, str)
        or not value
        or "#" in value
        or "\\" in value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
        or Path(value).as_posix() != value
    ):
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
    return candidate if candidate.exists() or not require_exists else None


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
                if target_path.is_relative_to((root / "qualification/evidence").resolve(strict=False)):
                    continue
                errors.append(f"{document.relative_to(root)}: broken link {target}")
                continue
            fragment = unquote(target.partition("#")[2])
            if fragment and target_path.is_file() and not _has_anchor(target_path, fragment):
                errors.append(f"{document.relative_to(root)}: broken anchor {target}")
    return errors


def check_workflow() -> list[str]:
    errors = []
    expected = (
        {"init", "status", "context-optimize", "support-bundle", "purge"},
        {"physical-optimize", "rtl-optimize", "signoff", "run", "status", "profiles"},
    )
    for parser, commands in zip((build_parser(), build_enterprise_parser()), expected, strict=True):
        actual = next(action.choices for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        if set(actual) != commands:
            errors.append(f"{parser.prog}: unexpected command scope")
    if tuple(profile.name for profile in ENTERPRISE_TOOL_PROFILES) != ("openroad",):
        errors.append("only the OpenROAD tool profile is supported")
    for name in (
        "AGENTS.md",
        "docs/README.md",
        "docs/verification.md",
        "src/dv_platform/physical_design.tcl",
    ):
        if not (ROOT / name).is_file():
            errors.append(f"missing workflow file: {name}")
    return errors


def check_evidence(root: Path = ROOT, *, require_artifacts: bool = False) -> list[str]:
    errors = []
    manifests = sorted((root / "qualification/evidence/PHYS-01").glob("*.json"))
    if require_artifacts and not manifests:
        errors.append("missing local qualification evidence manifests")
    for manifest in manifests:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        artifacts = document.get("artifacts") if isinstance(document, dict) else None
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"{manifest.name}: missing artifact records")
            continue
        paths: dict[Path, str] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
                errors.append(f"{manifest.name}: malformed artifact record")
                continue
            path = _safe_repo_path(root, artifact["path"], require_exists=False)
            if (
                path is None
                or path in paths
                or not isinstance(artifact["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]) is None
            ):
                errors.append(f"{manifest.name}: invalid or unsafe artifact {artifact['path']}")
                continue
            paths[path] = artifact["sha256"]
        if require_artifacts or any(path.exists() for path in paths):
            errors.extend(_check_artifact_files(manifest, paths))
    return errors


def _check_artifact_files(manifest: Path, paths: dict[Path, str]) -> list[str]:
    errors = []
    for path, digest in paths.items():
        if not path.is_file():
            errors.append(f"{manifest.name}: missing artifact {path.name}")
        else:
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    errors.append(f"{manifest.name}: changed artifact {path.name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-local-evidence", action="store_true")
    args = parser.parse_args()
    errors = check_internal_links() + check_workflow() + check_evidence(require_artifacts=args.require_local_evidence)
    for error in errors:
        print(error)
    if not errors:
        mode = "required" if args.require_local_evidence else "when present"
        print(f"repository contracts passed: documentation, OpenROAD scope, manifests; local artifact hashes {mode}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
