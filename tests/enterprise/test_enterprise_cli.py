import json
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.analysis.rtl import read_normalized_rtl_facts
from dv_platform.cli import main as platform_main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.enterprise.cli import main
from dv_platform.enterprise.store import enterprise_status
from tests.enterprise.test_enterprise_requirements import _document
from tests.enterprise.test_enterprise_semantics import _manifest
from tests.support.entitlements import issue_test_entitlement


class EnterpriseCLITests(TestCase):
    def test_imports_canonical_evidence_runs_adapter_and_passes_ci_status(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                product=issue_test_entitlement(
                    root,
                    (
                        "cli.enterprise",
                        "adapter.enterprise",
                        "evidence.enterprise.import",
                    ),
                ),
                adapter_plugins=(
                    AdapterPluginConfig(kind="semantic_importer", name="semantic_manifest"),
                    AdapterPluginConfig(kind="requirements_importer", name="requirements_manifest"),
                    AdapterPluginConfig(kind="simulator_runner", name="questa"),
                ),
            )
            config_path = root / "dv-platform.toml"
            write_config(config, config_path)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            semantic_path = root / "bridge.dvsem.json"
            semantic_path.write_text(json.dumps(_manifest("bridge.sv")), encoding="utf-8")
            requirements_path = root / "baseline.dvreq.json"
            requirements_path.write_text(json.dumps(_document()), encoding="utf-8")
            common = [
                "--repo-root",
                str(root),
                "--config",
                str(config_path),
                "--json",
            ]

            self.assertEqual(
                _main(common + ["import-semantics", "--input", str(semantic_path), "--strict"])[0],
                0,
            )
            plan_status, plan_payload = _platform_main(common + ["plan", "--target", "formal"])
            self.assertEqual(
                _main(
                    common
                    + [
                        "import-requirements",
                        "--input",
                        str(requirements_path),
                        "--strict",
                    ]
                )[0],
                0,
            )
            plan_status, plan_payload = _platform_main(common + ["plan", "--target", "formal"])
            script = (
                "import json,os,pathlib; "
                "pathlib.Path(os.environ['DV_PLATFORM_RESULT_PATH']).write_text(json.dumps({"
                "'schema_version':1,'status':'passed',"
                "'checks':[{'check_id':'SIM-1','module':'bridge','kind':'simulation','status':'passed'}],"
                "'artifacts':[],'diagnostics':[]}),encoding='utf-8')"
            )
            run_status, run_payload = _main(
                common
                + [
                    "run",
                    "--adapter",
                    "questa",
                    "--family",
                    "simulator",
                    "--run-id",
                    "nightly-1",
                    "--strict",
                    "--",
                    sys.executable,
                    "-c",
                    script,
                ]
            )
            status_code, status_payload = _main(common + ["status", "--policy", "ci"])
            coverage_status, coverage_payload = _platform_main(
                common
                + [
                    "coverage",
                    "--from-runs",
                    "--as-of",
                    "2026-07-19",
                ]
            )

            self.assertEqual(run_status, 0, run_payload)
            self.assertEqual(plan_status, 0, plan_payload)
            self.assertTrue(run_payload["data"]["traceability_complete"])
            self.assertEqual(status_code, 0, status_payload)
            self.assertTrue(status_payload["data"]["passed"])
            self.assertEqual(coverage_status, 1)
            self.assertEqual(
                coverage_payload["data"]["closure"]["points"][0]["point_id"],
                "enterprise:simulator:SIM-1",
            )
            normalized = read_normalized_rtl_facts(config)
            self.assertEqual(normalized[0].name, "bridge")
            self.assertTrue(enterprise_status(config)["requirements"]["present"])
            plans = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")
            self.assertIn(
                "REQ-1",
                {item.requirement_id for item in plans[0].structured_requirements},
            )

            _, platform_status = _platform_main(common + ["status", "--policy", "ci", "--no-require-tools"])
            policy_codes = {item["code"] for item in platform_status["data"]["policy"]["failures"]}
            self.assertNotIn("verilator_version_unsupported", policy_codes)

    def test_ci_status_fails_when_configured_evidence_is_missing(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                product=issue_test_entitlement(
                    root,
                    (
                        "cli.enterprise",
                        "adapter.enterprise",
                        "evidence.enterprise.import",
                    ),
                ),
                adapter_plugins=(AdapterPluginConfig(kind="semantic_importer", name="semantic_manifest"),),
            )
            config_path = root / "dv-platform.toml"
            write_config(config, config_path)

            status, payload = _main(
                [
                    "--repo-root",
                    str(root),
                    "--config",
                    str(config_path),
                    "--json",
                    "status",
                    "--policy",
                    "ci",
                ]
            )
            _, platform_payload = _platform_main(
                [
                    "--repo-root",
                    str(root),
                    "--config",
                    str(config_path),
                    "--json",
                    "status",
                    "--policy",
                    "ci",
                    "--no-require-tools",
                ]
            )

        self.assertEqual(status, 1)
        self.assertEqual(payload["data"]["failures"][0]["code"], "semantic_import_missing")
        platform_codes = {item["code"] for item in platform_payload["data"]["policy"]["failures"]}
        self.assertIn("semantic_import_missing", platform_codes)


def _main(arguments: list[str]) -> tuple[int, dict]:
    output = StringIO()
    with redirect_stdout(output):
        status = main(arguments)
    return status, json.loads(output.getvalue())


def _platform_main(arguments: list[str]) -> tuple[int, dict]:
    output = StringIO()
    with redirect_stdout(output):
        status = platform_main(arguments)
    return status, json.loads(output.getvalue())
