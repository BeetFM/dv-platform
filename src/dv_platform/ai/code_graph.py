"""Bounded advisory source-context access through code-review-graph."""

from __future__ import annotations

import hashlib
import json
import os
import select
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.models import CLIConfig, EvidenceKind, EvidenceRef, RTLModule
from dv_platform.core.security import resolve_secret

GRAPH_TOOLS = "build_or_update_graph_tool,get_minimal_context_tool,query_graph_tool,list_graph_stats_tool"
MAX_MCP_HEADER_BYTES = 64 * 1024
MAX_MCP_BODY_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class CodeGraphResult:
    text: str
    evidence_ref: EvidenceRef | None
    calls: int
    status: str
    error: str | None = None
    provenance: dict[str, object] | None = None


def planning_code_graph_context(
    config: CLIConfig,
    module: RTLModule,
    cancel_event: threading.Event | None = None,
) -> CodeGraphResult:
    """Return capped advisory graph context for one AI planning prompt."""

    options = config.context_optimization
    if (
        not _optimization_enabled_for_ai(config)
        or "planning" not in options.stages
        or not _planning_preflight_ready(config)
    ):
        return CodeGraphResult("", None, 0, "disabled")
    client: CodeReviewGraphClient | None = None
    try:
        client = CodeReviewGraphClient(config, cancel_event=cancel_event)
        snippets = []
        _raise_if_cancelled(cancel_event)
        minimal = client.call_tool(
            "get_minimal_context_tool",
            {
                "task": f"verification planning for module {module.name} in repo {config.repo_root}",
                "detail_level": options.code_graph_detail_level,
            },
        )
        snippets.append(("minimal_context", _stringify_tool_result(minimal)))
        calls = 1
        if module.source is not None:
            _raise_if_cancelled(cancel_event)
            query = client.call_tool(
                "query_graph_tool",
                {"pattern": "file_summary", "file": _display_source(module.source, config.repo_root)},
            )
            snippets.append(("file_summary", _stringify_tool_result(query)))
            calls += 1
    except InterruptedError:
        raise
    except Exception as error:
        if options.code_graph_mode == "required":
            raise RuntimeError(f"required code-graph optimization failed: {type(error).__name__}") from error
        severity = "error" if config.ci else "fallback"
        provenance = _code_graph_provenance(config, client)
        provenance["outcome"] = severity
        return CodeGraphResult("", None, 0, severity, type(error).__name__, provenance)
    finally:
        if client is not None:
            client.close()
    text = _cap_graph_text(snippets, options.code_graph_max_context_chars)
    if not text:
        if options.code_graph_mode == "required":
            raise RuntimeError("required code-graph optimization returned empty context")
        provenance = _code_graph_provenance(config, client)
        provenance["outcome"] = "empty"
        return CodeGraphResult("", None, calls, "empty", provenance=provenance)
    provenance = _code_graph_provenance(config, client)
    provenance["outcome"] = "available"
    return CodeGraphResult(
        text,
        EvidenceRef(
            kind=EvidenceKind.CODE_GRAPH_CONTEXT,
            source_id="code-review-graph",
            locator=f"module:{module.name}",
            summary=f"Advisory code graph context for {module.name}",
        ),
        calls,
        "available",
        provenance=provenance,
    )


class CodeReviewGraphClient:
    """Minimal JSON-RPC-over-stdio MCP client for the local code-review-graph server."""

    def __init__(self, config: CLIConfig, cancel_event: threading.Event | None = None) -> None:
        self.timeout = config.context_optimization.code_graph_timeout_seconds
        self.cancel_event = cancel_event
        command = shlex.split(config.context_optimization.code_graph_command)
        if not command:
            raise ValueError("empty code graph command")
        resolved = shutil.which(command[0])
        if resolved is None:
            raise FileNotFoundError(command[0])
        self.command = (resolved, *command[1:], "serve", "--tools", GRAPH_TOOLS)
        self.executable = resolved
        self.executable_version = _executable_version(resolved)
        self.process = subprocess.Popen(
            self.command,
            cwd=config.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            env=_optimizer_environment(),
            start_new_session=os.name != "nt",
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0,
        )
        self._closed = False
        self._next_id = 1
        try:
            initialize = self._request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "dv-platform", "version": "1"},
                },
            )
            if not isinstance(initialize, dict):
                raise ValueError("MCP initialize result must be an object")
            protocol = initialize.get("protocolVersion")
            capabilities = initialize.get("capabilities")
            if not isinstance(protocol, str) or not protocol:
                raise ValueError("MCP initialize result lacks protocolVersion")
            if not isinstance(capabilities, dict):
                raise ValueError("MCP initialize result lacks capabilities")
            self.protocol_version = protocol
            self.server_capabilities = capabilities
            self._notify("notifications/initialized", {})
            if config.context_optimization.code_graph_auto_update:
                self.call_tool("build_or_update_graph_tool", {"repo_root": str(config.repo_root)})
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> CodeReviewGraphClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        process = self.process
        try:
            if process.poll() is None:
                _signal_process_tree(process, signal.SIGTERM)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    _signal_process_tree(process, signal.SIGKILL)
                    process.wait(timeout=1)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, object]) -> object:
        _raise_if_cancelled(self.cancel_event)
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            _raise_if_cancelled(self.cancel_event)
            message = self._read_message(deadline)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return message.get("result")
        raise TimeoutError(method)

    def _write(self, payload: dict[str, object]) -> None:
        if self.process.stdin is None:
            raise BrokenPipeError("code-review-graph stdin closed")
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        self.process.stdin.flush()

    def _read_message(self, deadline: float) -> dict[str, Any]:  # noqa: C901
        if self.process.stdout is None:
            raise BrokenPipeError("code-review-graph stdout closed")
        header = b""
        while b"\r\n\r\n" not in header:
            _raise_if_cancelled(self.cancel_event)
            if len(header) >= MAX_MCP_HEADER_BYTES:
                raise ValueError("MCP headers exceed configured limit")
            if time.monotonic() >= deadline:
                raise TimeoutError("code-review-graph response")
            if self.process.poll() is not None:
                raise BrokenPipeError("code-review-graph exited")
            ready, _, _ = select.select(
                [self.process.stdout],
                [],
                [],
                min(0.05, max(0.0, deadline - time.monotonic())),
            )
            if not ready:
                continue
            chunk = os.read(self.process.stdout.fileno(), 1)
            if not chunk:
                raise BrokenPipeError("code-review-graph exited")
            header += chunk
        length = 0
        for line in header.decode("ascii", errors="ignore").splitlines():
            name, separator, value = line.partition(":")
            if separator and name.casefold() == "content-length":
                length = int(value.strip())
        if length <= 0:
            raise ValueError("missing MCP content-length")
        if length > MAX_MCP_BODY_BYTES:
            raise ValueError("MCP body exceeds configured limit")
        body = bytearray()
        while len(body) < length:
            _raise_if_cancelled(self.cancel_event)
            if time.monotonic() >= deadline:
                raise TimeoutError("code-review-graph response body")
            ready, _, _ = select.select(
                [self.process.stdout],
                [],
                [],
                min(0.05, max(0.0, deadline - time.monotonic())),
            )
            if not ready:
                continue
            chunk = os.read(self.process.stdout.fileno(), length - len(body))
            if not chunk:
                raise BrokenPipeError("code-review-graph exited during response")
            body.extend(chunk)
        value = json.loads(bytes(body).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("MCP response must be a JSON object")
        return value


def code_graph_status(config: CLIConfig) -> dict[str, object]:
    options = config.context_optimization
    command = shlex.split(options.code_graph_command) if options.code_graph_command.strip() else []
    executable = command[0] if command else ""
    available = bool(executable and shutil.which(executable))
    graph_dir = config.repo_root / ".code-review-graph"
    return {
        "enabled": _optimization_enabled_for_ai(config),
        "command": options.code_graph_command,
        "available": available,
        "executable": shutil.which(executable) if available else None,
        "version": _executable_version(str(shutil.which(executable))) if available else None,
        "graph_present": graph_dir.exists(),
        "graph_path": str(graph_dir),
        "auto_update": options.code_graph_auto_update,
    }


def _optimization_enabled_for_ai(config: CLIConfig) -> bool:
    return bool(config.ai.model.strip()) and config.context_optimization.code_graph_mode != "off"


def _planning_preflight_ready(config: CLIConfig) -> bool:
    """Mirror provider eligibility before launching a local optimizer process."""

    if "planning" not in config.ai.allowed_stages or not config.allow_network:
        return False
    if config.ai.api_key_env and not resolve_secret(config, config.ai.api_key_env):
        return False
    return True


_SECRET_ENV_MARKERS = ("KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL", "LICENSE", "PROXY")


def _optimizer_environment() -> dict[str, str]:
    """Pass only a minimal non-sensitive environment to the local graph server."""

    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP"}
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed and not any(marker in key.upper() for marker in _SECRET_ENV_MARKERS)
    }


def _signal_process_tree(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
    """Signal the owned process group, tolerating normal exit races."""

    try:
        if os.name == "nt":
            process.send_signal(signum)
        else:
            os.killpg(process.pid, signum)
    except (ProcessLookupError, OSError):
        pass


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("code-graph request cancelled")


def _executable_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            (executable, "--version"),
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
            env=_optimizer_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0][:512] if text else None


def _code_graph_provenance(config: CLIConfig, client: CodeReviewGraphClient | None) -> dict[str, object]:
    command = (
        tuple(client.command)
        if client is not None
        else tuple((*shlex.split(config.context_optimization.code_graph_command), "serve", "--tools", GRAPH_TOOLS))
    )
    command_json = json.dumps(command, separators=(",", ":"))
    return {
        "executable": client.executable if client is not None else None,
        "executable_version": client.executable_version if client is not None else None,
        "mcp_protocol_version": getattr(client, "protocol_version", None),
        "mcp_capabilities": getattr(client, "server_capabilities", {}),
        "graph_commit": _git_commit(config.repo_root),
        "graph_index_digest": _directory_digest(config.repo_root / ".code-review-graph"),
        "command": list(command),
        "command_identity": hashlib.sha256(command_json.encode("utf-8")).hexdigest(),
    }


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
            env=_optimizer_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip()
    return commit if len(commit) == 40 else None


def _directory_digest(path: Path) -> str | None:
    if not path.is_dir() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    files = tuple(item for item in sorted(path.rglob("*")) if item.is_file() and not item.is_symlink())
    if len(files) > 4096 or sum(item.stat().st_size for item in files) > 64 * 1024 * 1024:
        return None
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def run_code_graph_command(config: CLIConfig, action: str, base: str | None = None) -> subprocess.CompletedProcess[str]:
    command = shlex.split(config.context_optimization.code_graph_command)
    if not command:
        raise ValueError("empty code graph command")
    args = [*command, "build"] if action == "build-graph" else [*command, "update"]
    if base is not None:
        args.extend(["--base", base])
    return subprocess.run(
        args,
        cwd=config.repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.context_optimization.code_graph_timeout_seconds,
    )


def _stringify_tool_result(value: object) -> str:
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            pieces = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    pieces.append(item["text"])
            if pieces:
                return "\n".join(pieces)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _cap_graph_text(snippets: list[tuple[str, str]], max_chars: int) -> str:
    text = "\n\n".join(f"[{name}]\n{body}" for name, body in snippets if body.strip())
    return text[:max_chars]


def _display_source(source: Path, repo_root: Path) -> str:
    path = source if source.is_absolute() else repo_root / source
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.name
