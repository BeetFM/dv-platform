import json
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.ai.code_graph import CodeGraphResult
from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.model_client import ModelRequest, ModelResponse
from dv_platform.analysis.ai_planning import build_planning_context
from dv_platform.core.config import default_config, load_config, validate_config, write_config
from dv_platform.core.models import (
    AIConfig,
    CLIConfig,
    ContextOptimizationConfig,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLPort,
    VerificationPlan,
    VerificationTarget,
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
        json.loads(self.rfile.read(length).decode("utf-8"))
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
        self.assertTrue(optimizer_readiness(ai_config)["enabled"])
        self.assertTrue(code_graph_status(ai_config)["enabled"])

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
        self.assertTrue(optimizer_readiness(legacy_disabled)["headroom"]["enabled"])
        self.assertTrue(code_graph_status(legacy_disabled)["enabled"])

    def test_context_optimization_config_round_trips_and_validates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            path = repo / "dv-platform.toml"
            config = replace(
                default_config(repo),
                ai=AIConfig(model="openai/test"),
                context_optimization=ContextOptimizationConfig(
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

    def test_gateway_uses_headroom_compression_when_anchors_survive(self) -> None:
        with _headroom_server(
            'Create for module "top" schema version 2 E0001 '
            "<UNTRUSTED_EVIDENCE_DATA>{}</UNTRUSTED_EVIDENCE_DATA>"
        ) as endpoint:
            config = _optimized_config(Path.cwd(), endpoint)
            client = CapturingClient()
            result = LiteLLMGateway(config, client).execute(
                stage="planning",
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

    def test_gateway_falls_back_to_original_when_headroom_removes_anchor(self) -> None:
        with _headroom_server("missing anchors") as endpoint:
            config = _optimized_config(Path.cwd(), endpoint)
            client = CapturingClient()
            result = LiteLLMGateway(config, client).execute(
                stage="planning",
                system_prompt="system",
                user_prompt='module "top" schema version 2 E0001 <UNTRUSTED_EVIDENCE_DATA>raw</UNTRUSTED_EVIDENCE_DATA>',
                response_schema={},
                context='{"module":"top"}',
            )

        self.assertIn("raw", client.requests[0].user_prompt)
        self.assertEqual(result.optimization_metrics[0].status, "anchor_removed")

    def test_planning_context_includes_capped_code_graph_evidence(self) -> None:
        module = RTLModule(name="top", source=Path("top.sv"), ports=("data_o",))
        plan = VerificationPlan("top", (VerificationTarget.COCOTB,), ports=(RTLPort("data_o", "output"),))
        config = replace(
            default_config(Path.cwd()),
            ai=AIConfig(model="openai/test"),
            context_optimization=ContextOptimizationConfig(
                code_graph_max_context_chars=32,
            ),
        )
        graph = CodeGraphResult(
            "graph context " * 10,
            EvidenceRef(EvidenceKind.CODE_GRAPH_CONTEXT, "code-review-graph", "module:top"),
            2,
            "available",
        )
        with patch("dv_platform.ai.planning.context.planning_code_graph_context", return_value=graph):
            context = build_planning_context(config, module, plan)

        payload = json.loads(context.text)
        self.assertEqual(payload["code_graph_context"]["text"], ("graph context " * 10)[:32])
        graph_id = payload["code_graph_context"]["evidence_id"]
        self.assertEqual(context.evidence_by_id[graph_id].kind, EvidenceKind.CODE_GRAPH_CONTEXT)


def _optimized_config(repo: Path, endpoint: str) -> CLIConfig:
    return replace(
        default_config(repo),
        allow_network=True,
        ai=AIConfig(model="openai/test"),
        context_optimization=ContextOptimizationConfig(
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
