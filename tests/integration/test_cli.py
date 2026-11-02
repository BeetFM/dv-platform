import json
import runpy
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.cli import main
from dv_platform.core.config import default_config, load_config, validate_config, write_config
from dv_platform.domain.models import AdapterPluginConfig, AIConfig, ContextOptimizationConfig, ProductConfig


def invoke(root, *arguments):
    output = StringIO()
    with redirect_stdout(output):
        code = main(["--repo-root", str(root), "--json", *arguments])
    return code, json.loads(output.getvalue())


class CLITests(TestCase):
    def test_init_writes_pd_configuration_and_refuses_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            code, result = invoke(root, "init")
            self.assertEqual(code, 0)
            config = load_config(root / "dv-platform.toml")
            self.assertEqual(config.ai.allowed_stages, ("physical_design",))
            self.assertNotIn("[rtl]", Path(result["data"]["config"]).read_text())
            self.assertEqual(invoke(root, "init")[0], 1)

    def test_status_reports_unmet_required_physical_domains(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_config(
                replace(default_config(root), product=ProductConfig(required_physical_domains=("asic_timing",))),
                root / "dv-platform.toml",
            )
            self.assertEqual(invoke(root, "status")[0], 0)
            code, result = invoke(root, "status", "--policy", "ci")
            self.assertEqual(code, 1)
            self.assertEqual(result["data"]["physical"]["overall"], "unknown")

    def test_production_ci_requires_approval_even_when_timing_cache_passes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            product = ProductConfig(
                require_production_signoff=True, signoff_trust_policy_path=root / "external-trust.json"
            )
            write_config(replace(default_config(root), product=product), root / "dv-platform.toml")
            with patch("dv_platform.cli.collect_physical_status", return_value={"overall": "passed"}):
                self.assertEqual(invoke(root, "status", "--policy", "ci")[0], 1)
                self.assertEqual(invoke(root, "status")[0], 0)
            product = replace(product, signoff_trust_policy_path=None)
            self.assertTrue(validate_config(replace(default_config(root), product=product)))

    def test_context_status_and_graph_update_remain_available(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(invoke(directory, "context-optimize")[0], 0)
            with patch("dv_platform.ai.code_graph.run_code_graph_command") as run:
                run.return_value.returncode = 0
                run.return_value.stdout, run.return_value.stderr = "updated", ""
                self.assertEqual(invoke(directory, "context-optimize", "update-graph", "--base", "HEAD")[0], 0)
                self.assertEqual(run.call_args.args[1:], ("update-graph", "HEAD"))

    def test_support_bundle_and_dry_run_purge(self):
        with TemporaryDirectory() as directory:
            code, result = invoke(directory, "support-bundle")
            self.assertEqual(code, 0)
            self.assertTrue(Path(result["data"]["bundle"]).is_file())
            code, result = invoke(directory, "purge")
            self.assertEqual(code, 0)
            self.assertFalse(result["data"]["applied"])

    def test_current_configuration_round_trips_security_ai_and_context_settings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                allow_network=True,
                strict=True,
                ci=True,
                redact_patterns=("token=.*",),
                approved_plugin_publishers=("Acme",),
                adapter_plugins=(AdapterPluginConfig("analyzer_runner", "openroad", 2),),
                ai=AIConfig(model="fixture/physical", api_key_env="API_KEY"),
                context_optimization=ContextOptimizationConfig(headroom_mode="advisory"),
            )
            path = root / "dv-platform.toml"
            write_config(config, path)
            self.assertEqual(load_config(path), config)
            self.assertEqual(validate_config(config), ())

    def test_module_entrypoint_and_plain_status_work(self):
        with TemporaryDirectory() as directory:
            output = StringIO()
            with patch("sys.argv", ["dv-platform", "--repo-root", directory, "status"]), redirect_stdout(output):
                with self.assertRaises(SystemExit) as raised:
                    runpy.run_module("dv_platform", run_name="__main__")
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("physical=", output.getvalue())

    def test_network_and_ci_flags_reach_status_and_failed_graph_update_is_reported(self):
        with TemporaryDirectory() as directory:
            with patch("dv_platform.cli.platform_status", return_value={"physical": {"overall": "passed"}}) as status:
                self.assertEqual(invoke(directory, "--allow-network", "--ci", "status", "--policy", "ci")[0], 0)
                self.assertTrue(status.call_args.args[0].allow_network)
                self.assertTrue(status.call_args.args[0].ci)
                self.assertTrue(status.call_args.args[0].strict)
            with patch("dv_platform.ai.code_graph.run_code_graph_command") as run:
                run.return_value.returncode = 1
                run.return_value.stdout, run.return_value.stderr = "", "fixture failed"
                code, result = invoke(directory, "context-optimize", "build-graph")
                self.assertEqual(code, 1)
                self.assertEqual(result["data"]["stderr"], "fixture failed")

    def test_missing_explicit_config_and_malformed_toml_types_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            code, result = invoke(root, "--config", str(root / "missing.toml"), "status")
            self.assertEqual(code, 1)
            self.assertIn("does not exist", result["error"])
            path = root / "dv-platform.toml"
            for text in (
                '[policy]\nallow_network = "false"\n',
                "[ai]\nmax_retries = true\n",
                '[security]\nredact_patterns = "secret"\n',
                "ai = []\n",
                "[ai]\ntimeout_seconds = nan\n",
                "[policy]\nallow_netwrok = true\n",
                "[rtl]\nlegacy = true\n",
            ):
                with self.subTest(text=text):
                    path.write_text(text)
                    self.assertEqual(invoke(root, "status")[0], 1)

    def test_invalid_config_is_rejected_before_dispatch(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dv-platform.toml"
            path.write_text('[security]\nsecret_provider = "unsupported"\n')
            code, result = invoke(directory, "status")
            self.assertEqual(code, 1)
            self.assertIn("secret_provider", result["error"])
