"""Secure validation for bounded SRAM hexadecimal initialization profiles."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path

from dv_platform.core.models import RTLModule, VerificationDepthPolicy

PROFILE = "bounded_sram_init_hex"
MAX_INIT_BYTES = 64 * 1024 * 1024
_HEX = re.compile(r"^[0-9a-fA-F]+$")


@dataclass(frozen=True)
class MemoryInitialization:
    profile: str
    path: str
    sha256: str
    depth: int
    width: int
    memory: str
    default_policy: str
    words: tuple[int, ...]


def validate_memory_initialization(
    repo_root: Path,
    relative_path: str,
    *,
    depth: int,
    width: int,
    memory: str,
    default_policy: str,
) -> MemoryInitialization:
    """Validate and fingerprint one strict, one-word-per-line hex image."""

    raw, normalized_path = _read_initialization_file(repo_root, relative_path)
    words = _parse_initialization_words(raw, depth, width)
    if not memory:
        raise ValueError("memory initialization requires memory identity")
    if default_policy not in {"explicit_zero", "file_complete"}:
        raise ValueError("memory initialization default policy must be explicit_zero or file_complete")
    return MemoryInitialization(
        PROFILE,
        normalized_path,
        hashlib.sha256(raw).hexdigest(),
        depth,
        width,
        memory,
        default_policy,
        words,
    )


def _read_initialization_file(repo_root: Path, relative_path: str) -> tuple[bytes, str]:
    root = repo_root.resolve(strict=True)
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError("memory initialization path must be repository-relative without escapes")
    path = root.joinpath(candidate)
    if any(item.is_symlink() for item in (path, *path.parents) if item != root):
        raise ValueError("memory initialization path must not traverse symbolic links")
    resolved = path.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError("memory initialization file must be a regular repository file")
    raw = resolved.read_bytes()
    if len(raw) > MAX_INIT_BYTES:
        raise ValueError(f"memory initialization exceeds {MAX_INIT_BYTES} bytes")
    return raw, candidate.as_posix()


def _parse_initialization_words(raw: bytes, depth: int, width: int) -> tuple[int, ...]:
    if depth < 1 or width < 1:
        raise ValueError("memory initialization requires positive depth and width")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("memory initialization must be ASCII hexadecimal") from exc
    lines = text.splitlines()
    if len(lines) != depth or not lines:
        raise ValueError(f"memory initialization requires exactly {depth} words")
    digits = (width + 3) // 4
    words: list[int] = []
    for line_number, line in enumerate(lines, 1):
        if not line or line.strip() != line or len(line) != digits or _HEX.fullmatch(line) is None:
            raise ValueError(f"invalid hexadecimal word at line {line_number}")
        value = int(line, 16)
        if value >= 1 << width:
            raise ValueError(f"memory initialization word overflows width at line {line_number}")
        words.append(value)
    return tuple(words)


def bind_memory_initializations(
    repo_root: Path,
    modules: tuple[RTLModule, ...],
    policies: tuple[VerificationDepthPolicy, ...],
) -> tuple[RTLModule, ...]:
    """Bind validated initialization identities into normalized memory facts."""

    by_module: dict[str, list[VerificationDepthPolicy]] = {}
    for policy in policies:
        if policy.kind == "memory" and policy.parameter("profile") == PROFILE:
            by_module.setdefault(policy.module, []).append(policy)
    bound: list[RTLModule] = []
    for module in modules:
        module_policies = by_module.get(module.name, ()) or by_module.get(module.original_name or "", ())
        memories = []
        for memory in module.memories:
            matches = [policy for policy in module_policies if policy.subject == memory.name]
            if not matches:
                memories.append(memory)
                continue
            if len(matches) != 1 or memory.depth is None or memory.element_width is None:
                raise ValueError(f"memory initialization policy does not resolve uniquely: {module.name}/{memory.name}")
            policy = matches[0]
            metadata = validate_memory_initialization(
                repo_root,
                policy.parameter("path") or "",
                depth=memory.depth,
                width=memory.element_width,
                memory=memory.name,
                default_policy=policy.parameter("default_policy") or "",
            )
            configured_sha256 = policy.parameter("sha256")
            if configured_sha256 is not None and configured_sha256 != metadata.sha256:
                raise ValueError(f"memory initialization digest is stale: {metadata.path}")
            memories.append(
                replace(
                    memory,
                    initialization_profile=metadata.profile,
                    initialization_path=metadata.path,
                    initialization_sha256=metadata.sha256,
                    initialization_default_policy=metadata.default_policy,
                )
            )
        bound.append(replace(module, memories=tuple(memories)))
    return tuple(bound)
