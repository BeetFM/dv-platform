import json
import os
import subprocess
import sys
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dv_platform.ai.code_graph import CodeReviewGraphClient, code_graph_context
from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.model_client import ModelRequest, ModelResponse
from dv_platform.core.config import default_config, load_config, validate_config, write_config
from dv_platform.core.models import (
    AIConfig,
    CLIConfig,
    ContextOptimizationConfig,
)


class CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse("{}", prompt_tokens=1, completion_tokens=1, total_tokens=2)


class HeadroomHandler(BaseHTTPRequestHandler):
    compressed = ""

    def do_POST(self) -> None:
        length = int(self.headers["content-length"])
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        HeadroomHandler.last_payload = payload
        if not payload.get("model") or payload.get("config", {}).get("compress_user_messages") is not True:
            self.send_error(400, "model and compress_user_messages are required")
            return
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": self.compressed}],
                "tokens_before": 100,
                "tokens_after": 40,
                "transforms": ["compress"],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *args) -> None:
        return


class ContextOptimizationTests(unittest.TestCase):
    def test_context_optimization_defaults_follow_ai_configuration(self) -> None:
        base = default_config(Path.cwd())
        from dv_platform.ai.code_graph import code_graph_status
        from dv_platform.ai.optimization import optimizer_readiness

        self.assertFalse(optimizer_readiness(base)["enabled"])
        self.assertFalse(code_graph_status(base)["enabled"])

        ai_config = replace(base, ai=AIConfig(model="openai/test"))
        self.assertFalse(optimizer_readiness(ai_config)["enabled"])
        self.assertFalse(code_graph_status(ai_config)["enabled"])

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dv-platform.toml"
            path.write_text(
                "\n".join(
                    (
                        "[paths]",
                        'repo_root = "."',
                        "[ai]",
                        'model = "openai/test"',
                        "[context_optimization]",
                        "enabled = false",
                        "headroom_enabled = false",
                        "code_graph_enabled = false",
                    )
                ),
                encoding="utf-8",
            )
            legacy_disabled = load_config(path)
        self.assertFalse(optimizer_readiness(legacy_disabled)["headroom"]["enabled"])
        self.assertFalse(code_graph_status(legacy_disabled)["enabled"])

    def test_context_optimization_config_round_trips_and_validates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            path = repo / "dv-platform.toml"
            config = replace(
                default_config(repo),
                ai=AIConfig(model="openai/test"),
                context_optimization=ContextOptimizationConfig(
                    headroom_mode="advisory",
                    code_graph_mode="advisory",
                    code_graph_command="code-review-graph",
                    code_graph_max_context_chars=2048,
                ),
            )
            write_config(config, path)
            loaded = load_config(path)

            self.assertEqual(loaded.context_optimization, config.context_optimization)
            self.assertFalse(
                tuple(
                    item
                    for item in validate_config(config)
                    if item.severity == "error" or "context_optimization" in item.message
                )
            )

            unsafe = replace(
                config,
                context_optimization=replace(
                    config.context_optimization,
                    headroom_endpoint="https://example.test",
                    code_graph_command="",
                ),
            )
            messages = tuple(item.message for item in validate_config(unsafe))
            self.assertTrue(any("local HTTP" in message for message in messages))
            self.assertTrue(any("code_graph_command" in message for message in messages))

    def test_context_optimization_rejects_contradictory_legacy_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dv-platform.toml"
            path.write_text(
                "\n".join(
                    (
                        "[paths]",
                        'repo_root = "."',
                        "[context_optimization]",
                        'headroom_mode = "required"',
                        "headroom_enabled = false",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "contradicts legacy"):
                load_config(path)

    def test_gateway_uses_headroom_compression_when_anchors_survive(self) -> None:
        with _headroom_server(
            'Create for module "top" schema version 2 E0001 <UNTRUSTED_EVIDENCE_DATA>{}</UNTRUSTED_EVIDENCE_DATA>'
        ) as endpoint:
            config = _optimized_config(Path.cwd(), endpoint)
            client = CapturingClient()
            result = LiteLLMGateway(config, client).execute(
                stage="physical_design",
                system_prompt="system",
                user_prompt=(
                    'Create for module "top" schema version 2 E0001 '
                    "<UNTRUSTED_EVIDENCE_DATA>{large}</UNTRUSTED_EVIDENCE_DATA>"
                ),
                response_schema={},
                context='{"module":"top"}',
            )

        self.assertEqual(result.status, "accepted")
        self.assertIn("{}</UNTRUSTED_EVIDENCE_DATA>", client.requests[0].user_prompt)
        self.assertEqual(result.optimization_metrics[0].status, "compressed")
        record = json.loads(result.run_record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["optimization"][0]["saved_tokens"], 60)
        self.assertNotIn("{large}", result.run_record_path.read_text(encoding="utf-8"))

    def test_headroom_preserves_structured_physical_requirements_and_evidence(self) -> None:
        prompt = {
            "requirements": {"setup_wns_ns": 0},
            "assessment": {"gap": 0.03},
            "analysis": {"metrics": {"setup_wns_ns": -0.03}, "evidence_ids": ["setup:0"]},
        }
        for changed in (False, True):
            compressed = json.loads(json.dumps(prompt))
            if changed:
                compressed["requirements"]["setup_wns_ns"] = -0.1
            with (
                TemporaryDirectory() as directory,
                _headroom_server(json.dumps(compressed, separators=(",", ":"))) as endpoint,
            ):
                config = _optimized_config(Path(directory), endpoint)
                client = CapturingClient()
                result = LiteLLMGateway(config, client).execute(
                    stage="physical_design",
                    system_prompt="system",
                    user_prompt=json.dumps(prompt, indent=2),
                    response_schema={},
                    context="evidence",
                )
                self.assertEqual(result.optimization_metrics[0].status, "compressed")
                self.assertEqual(json.loads(client.requests[0].user_prompt), prompt)
                self.assertEqual(HeadroomHandler.last_payload["messages"][-1]["content"], "{}")

    def test_mcp_tool_errors_are_not_accepted_as_context(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fake_mcp.py"
            _write_fake_mcp(script)
            with CodeReviewGraphClient(_code_graph_config(root, script, "tool_error")) as client:
                with self.assertRaisesRegex(RuntimeError, "tool failed"):
                    client.call_tool("get_minimal_context_tool", {})

    def test_gateway_falls_back_to_original_when_headroom_removes_anchor(self) -> None:
        with _headroom_server("missing anchors") as endpoint:
            config = _optimized_config(Path.cwd(), endpoint)
            client = CapturingClient()
            result = LiteLLMGateway(config, client).execute(
                stage="physical_design",
                system_prompt="system",
                user_prompt='module "top" schema version 2 E0001 <UNTRUSTED_EVIDENCE_DATA>raw</UNTRUSTED_EVIDENCE_DATA>',
                response_schema={},
                context='{"module":"top"}',
            )

        self.assertIn("raw", client.requests[0].user_prompt)
        self.assertEqual(result.optimization_metrics[0].status, "anchor_removed")

    def test_code_graph_failure_closes_client(self) -> None:
        module = SimpleNamespace(name="top", source=Path("top.sv"), ports=("data_o",))
        config = replace(
            default_config(Path.cwd()),
            allow_network=True,
            ai=AIConfig(model="openai/test"),
            context_optimization=ContextOptimizationConfig(code_graph_mode="advisory"),
        )
        client = MagicMock()
        client.call_tool.side_effect = RuntimeError("malformed response")
        with patch("dv_platform.ai.code_graph.CodeReviewGraphClient", return_value=client):
            result = code_graph_context(config, module)
        self.assertEqual(result.status, "fallback")
        client.close.assert_called_once_with()

    def test_required_code_graph_failure_is_fatal_and_closes_client(self) -> None:
        module = SimpleNamespace(name="top", source=Path("top.sv"), ports=("data_o",))
        config = replace(
            default_config(Path.cwd()),
            allow_network=True,
            ai=AIConfig(model="openai/test"),
            context_optimization=ContextOptimizationConfig(code_graph_mode="required"),
        )
        client = MagicMock()
        client.call_tool.side_effect = RuntimeError("malformed response")
        with (
            patch("dv_platform.ai.code_graph.CodeReviewGraphClient", return_value=client),
            self.assertRaisesRegex(RuntimeError, "required code-graph"),
        ):
            code_graph_context(config, module)
        client.close.assert_called_once_with()

    def test_code_graph_close_reaps_and_closes_pipes(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("graph", 1), None]
        client = CodeReviewGraphClient.__new__(CodeReviewGraphClient)
        client.process = process
        with patch("dv_platform.ai.code_graph._signal_process_tree") as signal_tree:
            client.close()
        self.assertEqual(signal_tree.call_count, 2)
        process.stdin.close.assert_called_once_with()
        process.stdout.close.assert_called_once_with()

    def test_real_mcp_process_protocol_lifecycle_and_fd_census(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fake_mcp.py"
            _write_fake_mcp(script)
            before_fds = len(tuple(Path("/proc/self/fd").iterdir())) if Path("/proc/self/fd").is_dir() else None
            pids: list[int] = []
            for _ in range(5):
                with CodeReviewGraphClient(_code_graph_config(root, script, "healthy")) as client:
                    pids.append(client.process.pid)
                    result = client.call_tool("get_minimal_context_tool", {"task": "test"})
                    self.assertEqual(result["content"][0]["text"], "graph context")
                    self.assertEqual(client.protocol_version, "2024-11-05")
                    self.assertEqual(client.server_capabilities, {"tools": {}})
            for pid in pids:
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
            if before_fds is not None:
                self.assertLessEqual(len(tuple(Path("/proc/self/fd").iterdir())), before_fds + 1)

    def test_real_mcp_context_persists_bounded_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fake_mcp.py"
            _write_fake_mcp(script)
            graph_dir = root / ".code-review-graph"
            graph_dir.mkdir()
            (graph_dir / "index.bin").write_bytes(b"graph")

            result = code_graph_context(
                _code_graph_config(root, script, "healthy"),
                SimpleNamespace(name="top", source=None),
            )

            self.assertEqual(result.status, "available")
            self.assertEqual(result.provenance["outcome"], "available")
            self.assertEqual(result.provenance["mcp_protocol_version"], "2024-11-05")
            self.assertEqual(len(str(result.provenance["graph_index_digest"])), 64)
            self.assertEqual(len(str(result.provenance["command_identity"])), 64)

    def test_real_mcp_process_handles_wrong_ids_and_failure_frames(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fake_mcp.py"
            _write_fake_mcp(script)
            with CodeReviewGraphClient(_code_graph_config(root, script, "wrong_then_correct")) as client:
                self.assertIsInstance(client.call_tool("get_minimal_context_tool", {}), dict)
            for behavior, pattern in (
                ("crash", "exited"),
                ("oversized", "configured limit"),
                ("partial", "response body"),
                ("wrong_only", "response"),
            ):
                with self.subTest(behavior=behavior), self.assertRaisesRegex(Exception, pattern):
                    CodeReviewGraphClient(_code_graph_config(root, script, behavior))

    def test_real_mcp_process_cancellation_reaps_child(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fake_mcp.py"
            _write_fake_mcp(script)
            cancellation = threading.Event()
            timer = threading.Timer(0.05, cancellation.set)
            timer.start()
            try:
                with self.assertRaisesRegex(InterruptedError, "cancelled"):
                    CodeReviewGraphClient(
                        _code_graph_config(root, script, "partial", timeout=1.0),
                        cancel_event=cancellation,
                    )
            finally:
                timer.cancel()


def _optimized_config(repo: Path, endpoint: str) -> CLIConfig:
    return replace(
        default_config(repo),
        allow_network=True,
        ai=AIConfig(model="openai/test"),
        context_optimization=ContextOptimizationConfig(
            headroom_mode="advisory",
            code_graph_mode="advisory",
            headroom_endpoint=endpoint,
        ),
    )


class _headroom_server:
    def __init__(self, compressed: str) -> None:
        self.compressed = compressed
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> str:
        HeadroomHandler.compressed = self.compressed
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), HeadroomHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, *_args) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()


def _code_graph_config(repo: Path, script: Path, behavior: str, *, timeout: float = 0.2) -> CLIConfig:
    return replace(
        default_config(repo),
        allow_network=True,
        ai=AIConfig(model="openai/test"),
        context_optimization=ContextOptimizationConfig(
            code_graph_mode="advisory",
            code_graph_command=f"{sys.executable} {script} {behavior}",
            code_graph_timeout_seconds=timeout,
        ),
    )


def _write_fake_mcp(path: Path) -> None:
    path.write_text(
        """
import json
import sys
import time

behavior = sys.argv[1]

def read_message():
    line = sys.stdin.buffer.readline()
    if not line:
        raise SystemExit(0)
    return json.loads(line)

def send(value):
    body = json.dumps(value, separators=(",", ":")).encode()
    sys.stdout.buffer.write(body + b"\\n")
    sys.stdout.buffer.flush()

while True:
    request = read_message()
    if "id" not in request:
        continue
    request_id = request["id"]
    if behavior == "crash":
        raise SystemExit(3)
    if behavior == "oversized":
        sys.stdout.buffer.write(b"{" + b" " * 4200000)
        sys.stdout.buffer.flush()
        time.sleep(2)
        continue
    if behavior == "partial":
        sys.stdout.buffer.write(b"{")
        sys.stdout.buffer.flush()
        time.sleep(2)
        continue
    if behavior in {"wrong_only", "wrong_then_correct"}:
        send({"jsonrpc": "2.0", "id": request_id + 100, "result": {}})
        if behavior == "wrong_only":
            time.sleep(2)
            continue
    if request["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    else:
        params = request["params"]
        arguments = params["arguments"]
        invalid = (params["name"] == "get_minimal_context_tool" and "detail_level" in arguments) or (params["name"] == "query_graph_tool" and "target" not in arguments)
        result = {"content": [{"type": "text", "text": "graph context"}], "isError": invalid or behavior == "tool_error"}
    send({"jsonrpc": "2.0", "id": request_id, "result": result})
""".lstrip(),
        encoding="utf-8",
    )
