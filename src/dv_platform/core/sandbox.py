"""Rootless OCI command construction for isolated tool execution."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from dv_platform.core.models import CLIConfig


def sandbox_command(
    config: CLIConfig,
    command: tuple[str, ...],
    cwd: Path,
    *,
    readonly_paths: tuple[Path, ...] = (),
    writable_paths: tuple[Path, ...] = (),
) -> tuple[str, ...]:
    """Wrap a command in a network-denied, read-only-root OCI sandbox."""

    if not config.sandbox_enabled:
        return command
    if config.sandbox_image is None:
        raise ValueError("sandbox image is required")
    runtime = shutil.which(config.sandbox_runtime)
    if runtime is None:
        raise ValueError(f"sandbox runtime is unavailable: {config.sandbox_runtime}")
    root = cwd.resolve()
    environment: list[str] = []
    for name in config.sandbox_environment:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError(f"invalid sandbox environment name: {name}")
        if name in os.environ:
            environment.extend(("--env", name))
    user = ("--userns=keep-id",) if config.sandbox_runtime == "podman" else ("--user", f"{os.getuid()}:{os.getgid()}")
    readonly = _unique_roots((config.repo_root, config.output_dir, root, *readonly_paths))
    writable = _unique_roots(writable_paths)
    if not writable:
        raise ValueError("sandbox execution requires an isolated writable output directory")
    mounts: list[str] = []
    for path, mode in (*((path, "ro") for path in readonly), *((path, "rw") for path in writable)):
        mounts.extend(("--volume", f"{path}:{path}:{mode},rprivate"))
    return (
        runtime,
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        *user,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--memory={config.max_process_memory_mb}m",
        "--cpus=1",
        "--pids-limit=512",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=256m",
        *mounts,
        f"--workdir={root}",
        *environment,
        config.sandbox_image,
        *command,
    )


def _unique_roots(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    values: list[Path] = []
    for raw in paths:
        path = raw.expanduser().resolve(strict=False)
        if path not in values:
            values.append(path)
    return tuple(values)
