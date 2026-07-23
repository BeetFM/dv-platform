# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Simulation run command construction and execution."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.models import CLIConfig
from dv_platform.core.sandbox import sandbox_command
from dv_platform.core.security import redact_text


@dataclass(frozen=True)
class _ProcessResult:
    """Bounded result from a tool process and all of its descendants."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def _set_process_memory_limit(pid: int, memory_limit_mb: int) -> None:
    """Apply an address-space limit to a running POSIX process and its descendants."""

    if os.name != "posix" or memory_limit_mb <= 0:
        return
    try:
        import resource

        limit = memory_limit_mb * 1024 * 1024
        prlimit = getattr(resource, "prlimit", None)
        if prlimit is not None:
            prlimit(pid, resource.RLIMIT_AS, (limit, limit))
    except (ImportError, OSError, ValueError):
        # The parent still has timeout and process-group containment if this
        # platform does not expose RLIMIT_AS.
        return


def _terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float = 2.0) -> None:
    """Terminate a process and its descendants, escalating after a short grace period."""

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def _capture_process_stream(
    stream: Any,
    output_path: Path,
    max_output_bytes: int,
    truncated_result: list[bool],
) -> None:
    """Drain a pipe without allowing an unbounded tool log to consume RAM."""

    max_output_bytes = max(1, max_output_bytes)
    head_limit = max_output_bytes // 2
    tail_limit = max_output_bytes - head_limit
    head = bytearray()
    tail = bytearray()
    truncated = False
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            head_remaining = max(0, head_limit - len(head))
            if head_remaining:
                head.extend(chunk[:head_remaining])
            tail_chunk = chunk[head_remaining:]
            if tail_chunk:
                truncated = True
                tail.extend(tail_chunk)
                if len(tail) > tail_limit:
                    del tail[: len(tail) - tail_limit]
    finally:
        stream.close()
        truncated_result.append(truncated)
        payload = bytes(head)
        if truncated:
            payload += b"\n... output truncated by dv-platform ...\n" + bytes(tail)
        output_path.write_bytes(payload)


def _run_bounded_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    timeout_seconds: float,
    stdout_path: Path,
    stderr_path: Path,
    max_output_bytes: int,
    memory_limit_mb: int,
    config: CLIConfig | None = None,
) -> _ProcessResult:
    """Run a tool with bounded logs, memory, timeout, and descendant cleanup."""

    if config is not None:
        command = sandbox_command(
            config,
            command,
            cwd,
            readonly_paths=(config.repo_root, config.output_dir),
            writable_paths=(stdout_path.parent,),
        )
    popen_kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "bufsize": 0,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags

    process = subprocess.Popen(command, **popen_kwargs)
    _set_process_memory_limit(process.pid, memory_limit_mb)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_truncated: list[bool] = []
    stderr_truncated: list[bool] = []
    stdout_thread = threading.Thread(
        target=_capture_process_stream,
        args=(process.stdout, stdout_path, max_output_bytes, stdout_truncated),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_capture_process_stream,
        args=(process.stderr, stderr_path, max_output_bytes, stderr_truncated),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
    except BaseException:
        # Ctrl-C and unexpected parent-side failures must not orphan solver
        # descendants while the caller unwinds.
        _terminate_process_group(process)
        stdout_thread.join()
        stderr_thread.join()
        raise
    stdout_thread.join()
    stderr_thread.join()
    return _ProcessResult(
        returncode=124 if timed_out else process.returncode,
        stdout=_process_output(stdout_path.read_bytes()),
        stderr=_process_output(stderr_path.read_bytes()),
        timed_out=timed_out,
        stdout_truncated=bool(stdout_truncated and stdout_truncated[0]),
        stderr_truncated=bool(stderr_truncated and stderr_truncated[0]),
    )


def _redact_process_output(config: CLIConfig, output: str, truncated: bool, stream_name: str) -> str:
    """Redact bounded tool output and make truncation visible to the user."""

    if truncated:
        output += f"\n{stream_name.capitalize()} was truncated after {config.max_output_bytes} bytes.\n"
    return redact_text(config, output)


def _process_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


for _legacy_class in (_ProcessResult,):
    _legacy_class.__module__ = "dv_platform.run"
del _legacy_class
