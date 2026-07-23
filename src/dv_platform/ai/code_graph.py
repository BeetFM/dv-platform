"""Bounded advisory source-context access through code-review-graph."""

from __future__ import annotations

import json
import select
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.models import CLIConfig, EvidenceKind, EvidenceRef, RTLModule

GRAPH_TOOLS = "build_or_update_graph_tool,get_minimal_context_tool,query_graph_tool,list_graph_stats_tool"


@dataclass(frozen=True)
class CodeGraphResult:
    text: str
    evidence_ref: EvidenceRef | None
    calls: int
    status: str
    error: str | None = None


def planning_code_graph_context(config: CLIConfig, module: RTLModule) -> CodeGraphResult:
    """Return capped advisory graph context for one AI planning prompt."""

    options = config.context_optimization
    if not _optimization_enabled_for_ai(config) or "planning" not in options.stages:
        return CodeGraphResult("", None, 0, "disabled")
    try:
        client = CodeReviewGraphClient(config)
        snippets = []
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
            query = client.call_tool(
                "query_graph_tool",
                {"pattern": "file_summary", "file": _display_source(module.source, config.repo_root)},
            )
            snippets.append(("file_summary", _stringify_tool_result(query)))
            calls += 1
        client.close()
    except Exception as error:
        severity = "error" if config.ci else "fallback"
        return CodeGraphResult("", None, 0, severity, type(error).__name__)
    text = _cap_graph_text(snippets, options.code_graph_max_context_chars)
    if not text:
        return CodeGraphResult("", None, calls, "empty")
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
    )


class CodeReviewGraphClient:
    """Minimal JSON-RPC-over-stdio MCP client for the local code-review-graph server."""

    def __init__(self, config: CLIConfig) -> None:
        self.timeout = config.context_optimization.code_graph_timeout_seconds
        command = shlex.split(config.context_optimization.code_graph_command)
        if not command:
            raise ValueError("empty code graph command")
        if shutil.which(command[0]) is None:
            raise FileNotFoundError(command[0])
        self.process = subprocess.Popen(
            [*command, "serve", "--tools", GRAPH_TOOLS],
            cwd=config.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
        )
        self._next_id = 1
        self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "dv-platform", "version": "1"}})
        self._notify("notifications/initialized", {})
        if config.context_optimization.code_graph_auto_update:
            self.call_tool("build_or_update_graph_tool", {"repo_root": str(config.repo_root)})

    def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, object]) -> object:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
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

    def _read_message(self, deadline: float) -> dict[str, Any]:
        if self.process.stdout is None:
            raise BrokenPipeError("code-review-graph stdout closed")
        header = b""
        while b"\r\n\r\n" not in header:
            if time.monotonic() >= deadline:
                raise TimeoutError("code-review-graph response")
            if self.process.poll() is not None:
                raise BrokenPipeError("code-review-graph exited")
            ready, _, _ = select.select([self.process.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                raise TimeoutError("code-review-graph response")
            chunk = self.process.stdout.read(1)
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
        return json.loads(self.process.stdout.read(length).decode("utf-8"))


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
        "graph_present": graph_dir.exists(),
        "graph_path": str(graph_dir),
        "auto_update": options.code_graph_auto_update,
    }


def _optimization_enabled_for_ai(config: CLIConfig) -> bool:
    return bool(config.ai.model.strip())


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
