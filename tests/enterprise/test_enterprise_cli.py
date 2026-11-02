import json
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.core.config import default_config, write_config
from dv_platform.enterprise.cli import main
from tests.support.entitlements import issue_test_entitlement


def _main(arguments):
    output = StringIO()
    with redirect_stdout(output):
        code = main(arguments)
    return code, json.loads(output.getvalue())


class EnterpriseCLITests(TestCase):
    def test_free_plan_denies_execution_before_tool_loading(self):
        with (
            TemporaryDirectory() as directory,
            patch("dv_platform.enterprise.cli.active_product_plan", return_value=None),
            patch("dv_platform.enterprise.cli.load_adapter_plugins") as load,
        ):
            code, result = _main(["--repo-root", directory, "--json", "run", "--run-id", "trial", "--", "openroad"])
            self.assertEqual(code, 1)
            self.assertIn("cli.enterprise", result["error"]["message"])
            load.assert_not_called()

    def test_licensed_profiles_only_expose_openroad(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(default_config(root), product=issue_test_entitlement(root, ("cli.enterprise",)))
            write_config(config, root / "dv-platform.toml")
            code, result = _main(["--repo-root", directory, "--json", "profiles"])
            self.assertEqual(code, 0)
            self.assertEqual([profile["name"] for profile in result["data"]["profiles"]], ["openroad"])

    def test_run_rejects_unsafe_ids_and_missing_commands(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                product=issue_test_entitlement(Path(directory), ("cli.enterprise", "adapter.enterprise")),
            )
            with patch("dv_platform.enterprise.cli._config", return_value=config):
                for arguments in (("--run-id", "../escape", "--", "openroad"), ("--run-id", "trial")):
                    with self.subTest(arguments=arguments):
                        code, result = _main(["--json", "run", *arguments])
                        self.assertEqual(code, 1)
                        self.assertIn("error", result)

    def test_licensed_run_executes_and_normalizes_a_traceable_result(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root), product=issue_test_entitlement(root, ("cli.enterprise", "adapter.enterprise"))
            )
            script = "import json,os,pathlib; pathlib.Path(os.environ['DV_PLATFORM_RESULT_PATH']).write_text(json.dumps({'schema_version':1,'status':'passed','checks':[{'check_id':'TIMING','module':'gcd','kind':'timing','status':'passed'}],'artifacts':[],'diagnostics':[]}))"
            with patch("dv_platform.enterprise.cli._config", return_value=config):
                code, result = _main(
                    ["--json", "run", "--run-id", "native-contract", "--strict", "--", sys.executable, "-c", script]
                )
            self.assertEqual(code, 0)
            self.assertTrue(result["data"]["traceability_complete"])
            self.assertEqual(result["data"]["checks"], 1)
            self.assertTrue(Path(result["data"]["summary"]).is_file())

    def test_configured_strict_policy_applies_without_the_cli_strict_flag(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                strict=True,
                product=issue_test_entitlement(root, ("cli.enterprise", "adapter.enterprise")),
            )
            with patch("dv_platform.enterprise.cli._config", return_value=config):
                code, result = _main(["--json", "run", "--run-id", "strict-config", "--", sys.executable, "-c", "pass"])
            self.assertEqual(code, 1)
            self.assertFalse(result["data"]["traceability_complete"])

    def test_bootstrap_plan_is_honored_when_config_has_no_explicit_entitlement(self):
        from dv_platform.product import resolve_configured_product_plan

        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = default_config(root)
            plan = resolve_configured_product_plan(
                replace(config, product=issue_test_entitlement(root, ("cli.enterprise",)))
            )
            with (
                patch("dv_platform.enterprise.cli._config", return_value=config),
                patch("dv_platform.enterprise.cli.active_product_plan", return_value=plan),
            ):
                self.assertEqual(_main(["--json", "profiles"])[0], 0)

    def test_private_bootstrap_honors_configured_entitlements_and_reports_enterprise_status(self):
        import importlib.util

        from tests.support.paths import REPOSITORY_ROOT

        path = REPOSITORY_ROOT / "enterprise/src/dv_platform_enterprise/cli.py"
        spec = importlib.util.spec_from_file_location("enterprise_bootstrap", path)
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            product = issue_test_entitlement(root, ("cli.enterprise", "entitlement.status"))
            write_config(replace(default_config(root), product=product), root / "dv-platform.toml")
            for command in (("profiles",), ("status",), ("entitlement", "status")):
                output = StringIO()
                with redirect_stdout(output):
                    code = bootstrap.main(["--repo-root", directory, "--json", *command])
                self.assertEqual(code, 0, output.getvalue())
                result = json.loads(output.getvalue())
                if command == ("status",):
                    self.assertEqual(result["data"]["product"]["distribution"], "enterprise")
                elif command == ("entitlement", "status"):
                    self.assertEqual(result["entitlement_state"], "valid")
            (root / "dv-platform.toml").unlink()
            output = StringIO()
            with redirect_stdout(output):
                code = bootstrap.main(["--repo-root", directory, "--json", "profiles"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_ci_status_requires_physical_closure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            product = issue_test_entitlement(root, ("cli.enterprise",))
            config = replace(default_config(root), product=replace(product, required_physical_domains=("asic_timing",)))
            with patch("dv_platform.enterprise.cli._config", return_value=config):
                code, result = _main(["--json", "status", "--policy", "ci"])
            self.assertEqual(code, 1)
            self.assertEqual(result["data"]["physical"]["overall"], "unknown")
