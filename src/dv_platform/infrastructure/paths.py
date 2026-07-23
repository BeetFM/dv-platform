"""Path-containment rules for names and generated state."""

from __future__ import annotations

from pathlib import Path


def validate_path_component(value: str, label: str = "path component") -> str:
    """Return a single safe filesystem component or reject the value."""

    if not value or value in {".", ".."}:
        raise ValueError(f"Invalid {label}: {value!r}")
    if "/" in value or "\\" in value or ":" in value:
        raise ValueError(f"Invalid {label}; path separators and drive prefixes are not allowed: {value!r}")
    if (
        value != value.strip()
        or value.startswith(".")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Invalid {label}; hidden, whitespace, and control-character names are not allowed: {value!r}")
    if Path(value).name != value:
        raise ValueError(f"Invalid {label}; expected one path component: {value!r}")
    return value


def contained_path(root: Path, *components: str | Path) -> Path:
    """Build a path and verify that its resolved location remains below root."""

    resolved_root = root.resolve(strict=False)
    candidate = resolved_root.joinpath(*components)
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate == resolved_root or resolved_root not in resolved_candidate.parents:
        raise ValueError(f"Path escapes configured root {resolved_root}: {candidate}")
    return candidate


def is_within(path: Path, root: Path) -> bool:
    """Return whether path resolves to root or one of its descendants."""

    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents
