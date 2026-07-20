import sys
from dataclasses import replace
from importlib.metadata import EntryPoint
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.core.config import default_config, validate_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.core.plugins import load_adapter_plugins
from dv_platform.enterprise.adapters import (
    EnterpriseAdapterError,
    EnterpriseInvocation,
    QuestaSimulatorRunner,
)
from dv_platform.enterprise.profiles import ENTERPRISE_TOOL_PROFILES, enterprise_profile


class EnterpriseAdapterTests(TestCase):
    def test_secure_runner_normalizes_traceable_results_and_redacts_logs(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            artifact = root / "coverage.ucis.xml"
            artifact.write_text("<UCIS />", encoding="utf-8")
            script = (
                "import json,os,pathlib,sys; "
                "print('token=' + os.environ['DV_TEST_TOKEN']); "
                "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
                "'schema_version':1,'status':'passed',"
                "'checks':[{'check_id':'CHK-1','module':'bridge','kind':'simulation','status':'passed'}],"
                "'artifacts':[{'kind':'ucis','path':'coverage.ucis.xml'}],"
                "'diagnostics':[]}),encoding='utf-8')"
            )
            invocation = _invocation(
                root,
                (sys.executable, "-c", script, str(result_path)),
                environment_names=("DV_TEST_TOKEN",),
                environment=(("DV_TEST_TOKEN", "secret-value"),),
                redact_patterns=("secret-value",),
            )

            result = QuestaSimulatorRunner().execute(invocation, strict=True)

            self.assertTrue(result.passed)
            self.assertTrue(result.traceability_complete)
            self.assertEqual(result.checks[0].check_id, "CHK-1")
            self.assertEqual(result.artifacts[0].path, artifact)
            self.assertIn("[REDACTED]", invocation.stdout_path.read_text(encoding="utf-8"))
            summary = invocation.summary_path.read_text(encoding="utf-8")
            self.assertNotIn("secret-value", summary)
            self.assertNotIn(script, summary)
            summary_payload = __import__("json").loads(summary)
            self.assertEqual(summary_payload["coverage_points"][0]["check_id"], "CHK-1")
            self.assertEqual(summary_payload["formal_points"], [])

    def test_strict_runner_rejects_missing_result_and_unsafe_outputs(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = QuestaSimulatorRunner().execute(_invocation(root, (sys.executable, "-c", "pass")), strict=True)
            self.assertFalse(result.passed)
            self.assertIn("result manifest is missing", " ".join(result.diagnostics))

            unsafe = replace(
                _invocation(root, (sys.executable, "-c", "pass")),
                summary_path=root.parent / "escape.json",
            )
            with self.assertRaisesRegex(EnterpriseAdapterError, "escapes working directory"):
                QuestaSimulatorRunner().execute(unsafe)

    def test_rejects_missing_and_escaping_reported_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, artifact_path in enumerate(("missing.xml", "../escape.xml")):
                script = (
                    "import json,pathlib,sys; "
                    "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
                    "'schema_version':1,'status':'passed',"
                    "'checks':[{'check_id':'C','module':'m','kind':'simulation','status':'passed'}],"
                    f"'artifacts':[{{'kind':'coverage','path':'{artifact_path}'}}],"
                    "'diagnostics':[]}),encoding='utf-8')"
                )
                invocation = _invocation(root, (sys.executable, "-c", script, str(root / "result.json")))
                with self.subTest(index=index), self.assertRaises(EnterpriseAdapterError):
                    QuestaSimulatorRunner().execute(invocation, strict=True)

    def test_profiles_and_plugins_are_versioned_and_configurable(self) -> None:
        names = {profile.name for profile in ENTERPRISE_TOOL_PROFILES}
        self.assertTrue(
            {
                "questa",
                "vcs",
                "xcelium",
                "riviera_pro",
                "jaspergold",
                "vc_formal",
                "spyglass",
                "alint_pro",
            }
            <= names
        )
        self.assertIn("systemverilog", enterprise_profile("questa").languages)
        entry_point = EntryPoint(
            name="questa",
            value="dv_platform.enterprise.adapters:QuestaSimulatorRunner",
            group="dv_platform.simulator_runner",
        )
        plugins = load_adapter_plugins(
            (AdapterPluginConfig(kind="simulator_runner", name="questa"),),
            entry_points=(entry_point,),
        )
        self.assertIsInstance(plugins[0].adapter, QuestaSimulatorRunner)

        config = replace(
            default_config(Path(".")),
            adapter_plugins=(
                AdapterPluginConfig(kind="semantic_importer", name="semantic_manifest"),
                AdapterPluginConfig(kind="requirements_importer", name="requirements_manifest"),
                AdapterPluginConfig(kind="analyzer_runner", name="spyglass"),
            ),
        )
        messages = [item.message for item in validate_config(config)]
        self.assertFalse(any("Invalid adapter plugin" in message for message in messages))


def _invocation(
    root: Path,
    command: tuple[str, ...],
    *,
    environment_names: tuple[str, ...] = (),
    environment: tuple[tuple[str, str], ...] = (),
    redact_patterns: tuple[str, ...] = (),
) -> EnterpriseInvocation:
    return EnterpriseInvocation(
        adapter="questa",
        family="simulator",
        command=command,
        cwd=root,
        result_path=root / "result.json",
        summary_path=root / "summary.json",
        stdout_path=root / "stdout.log",
        stderr_path=root / "stderr.log",
        timeout_seconds=5,
        environment_names=environment_names,
        environment=environment,
        redact_patterns=redact_patterns,
    )
