import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.core.config import default_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.enterprise.adapters import (
    EnterpriseAdapterError,
    EnterpriseCommandAdapter,
    JasperGoldFormalRunner,
    QuestaSimulatorRunner,
    _load_result,
)
from dv_platform.enterprise.profiles import (
    ENTERPRISE_TOOL_PROFILES,
    detect_enterprise_tools,
    enterprise_profile,
)
from dv_platform.enterprise.requirements import RequirementsImportError, RequirementsManifestImporter
from dv_platform.enterprise.semantics import SemanticImportError, SemanticManifestImporter
from dv_platform.enterprise.store import enterprise_status, read_requirements_baseline
from tests.test_enterprise_adapters import _invocation
from tests.test_enterprise_cli import _main
from tests.test_enterprise_requirements import _document
from tests.test_enterprise_semantics import _manifest


class EnterpriseAdapterHardeningTests(TestCase):
    def test_rejects_unsafe_invocation_contracts(self) -> None:
        class WrongKindRunner(EnterpriseCommandAdapter):
            profile_name = "questa"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = _invocation(root, ("tool",))
            cases = (
                (QuestaSimulatorRunner(), replace(base, family="formal")),
                (WrongKindRunner(), base),
                (QuestaSimulatorRunner(), replace(base, command=())),
                (QuestaSimulatorRunner(), replace(base, command=("bad\x00arg",))),
                (QuestaSimulatorRunner(), replace(base, timeout_seconds=0)),
                (
                    QuestaSimulatorRunner(),
                    replace(
                        base,
                        environment_names=("TOKEN",),
                        environment=(("TOKEN", "one"), ("TOKEN", "two")),
                    ),
                ),
                (QuestaSimulatorRunner(), replace(base, environment=(("not-safe", "value"),))),
                (QuestaSimulatorRunner(), replace(base, environment=(("UNDECLARED", "value"),))),
                (QuestaSimulatorRunner(), replace(base, redact_patterns=("(",))),
            )
            for index, (runner, invocation) in enumerate(cases):
                with self.subTest(index=index), self.assertRaises(EnterpriseAdapterError):
                    runner.execute(invocation)

    def test_rejects_malformed_normalized_results(self) -> None:
        valid = {
            "schema_version": 1,
            "status": "passed",
            "checks": [
                {
                    "check_id": "CHK-1",
                    "module": "bridge",
                    "kind": "simulation",
                    "status": "passed",
                    "message": "complete",
                    "source_location": "bridge.sv:1",
                }
            ],
            "artifacts": [],
            "diagnostics": [],
        }
        cases: list[object] = [
            [],
            {**valid, "unexpected": True},
            {**valid, "schema_version": 99},
            {**valid, "status": "running"},
            {**valid, "checks": "invalid"},
            {**valid, "checks": [{**valid["checks"][0], "unexpected": True}]},
            {**valid, "checks": [valid["checks"][0], valid["checks"][0]]},
            {**valid, "checks": [{**valid["checks"][0], "status": "waived"}]},
            {**valid, "checks": [{**valid["checks"][0], "check_id": ""}]},
            {**valid, "checks": [{**valid["checks"][0], "message": 4}]},
            {**valid, "artifacts": [{"kind": "coverage", "path": "x", "extra": True}]},
            {**valid, "diagnostics": [7]},
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            result_path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseAdapterError, "invalid enterprise result JSON"):
                _load_result(result_path, root)
            for index, payload in enumerate(cases):
                result_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(EnterpriseAdapterError):
                    _load_result(result_path, root)

            target = root / "target.json"
            target.write_text(json.dumps(valid), encoding="utf-8")
            link = root / "linked.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(EnterpriseAdapterError, "escapes working directory"):
                _load_result(link, root)

    def test_normalizes_nonzero_strict_formal_and_timeout_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def command(result_path: Path, status: str = "passed", exit_code: int = 0) -> tuple[str, ...]:
                script = (
                    "import json,pathlib,sys; "
                    "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
                    "'schema_version':1,'status':'passed',"
                    f"'checks':[{{'check_id':'CHK','module':'bridge','kind':'property','status':'{status}'}}],"
                    "'artifacts':[],'diagnostics':['vendor diagnostic']}),encoding='utf-8'); "
                    f"raise SystemExit({exit_code})"
                )
                return (sys.executable, "-c", script, str(result_path))

            result_path = root / "nonzero.json"
            nonzero = QuestaSimulatorRunner().execute(
                replace(_invocation(root, command(result_path, exit_code=3)), result_path=result_path)
            )
            self.assertEqual(nonzero.status, "failed")
            self.assertIn("non-zero", " ".join(nonzero.diagnostics))

            result_path = root / "strict.json"
            strict = QuestaSimulatorRunner().execute(
                replace(_invocation(root, command(result_path, status="skipped")), result_path=result_path),
                strict=True,
            )
            self.assertEqual(strict.status, "failed")
            self.assertIn("skipped", " ".join(strict.diagnostics))

            result_path = root / "formal.json"
            formal_invocation = replace(
                _invocation(root, command(result_path)),
                adapter="jaspergold",
                family="formal",
                result_path=result_path,
            )
            formal = JasperGoldFormalRunner().execute(formal_invocation, strict=True)
            summary = json.loads(formal.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["coverage_points"], [])
            self.assertEqual(summary["formal_points"][0]["status"], "covered")

            timeout = QuestaSimulatorRunner().execute(
                replace(
                    _invocation(root, (sys.executable, "-c", "import time; time.sleep(2)")),
                    result_path=root / "timeout.json",
                    timeout_seconds=0.01,
                )
            )
            self.assertEqual(timeout.status, "timeout")
            self.assertIsNone(timeout.return_code)


class SemanticHardeningTests(TestCase):
    def test_supports_expected_manifest_names(self) -> None:
        importer = SemanticManifestImporter()
        self.assertTrue(importer.supports(Path("facts.DVSEM.JSON")))
        self.assertFalse(importer.supports(Path("facts.json")))

    def test_rejects_invalid_semantic_contracts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            importer = SemanticManifestImporter()
            invalid_json = root / "invalid.dvsem.json"
            invalid_json.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(SemanticImportError, "invalid semantic manifest JSON"):
                importer.import_semantics(invalid_json, root)

            cases: list[tuple[dict, bool]] = []

            def add(mutator, strict: bool = False) -> None:
                document = _manifest("bridge.sv")
                mutator(document)
                cases.append((document, strict))

            add(lambda item: item.update(schema_version="2"))
            add(lambda item: item.update(modules=[]))
            add(lambda item: item["modules"].append(deepcopy(item["modules"][0])))
            add(lambda item: item["modules"][0].update(language="rust"))
            add(lambda item: item["modules"][0].update(standard="1800-1900"))
            add(lambda item: item["modules"][0].update(design_unit_kind="architecture"))
            add(lambda item: item["modules"][0]["completeness"].pop("types"))
            add(lambda item: item["modules"][0]["completeness"].update(types="guessed"))
            add(lambda item: item["modules"][0].update(source="missing.sv"))
            add(lambda item: item.update(diagnostics=[{"severity": "fatal", "code": "X", "message": "bad"}]))
            add(lambda item: item.update(diagnostics=[{"severity": "error", "code": "X", "message": "bad"}]), True)
            add(lambda item: item["modules"][0].update(ports="invalid"))
            add(lambda item: item["modules"][0]["ports"][0].update(width=-1))
            add(lambda item: item["modules"][0]["ports"][0].update(signed="yes"))
            add(lambda item: item["modules"][0]["semantic_features"][0].update(supported_targets=["unknown"]))
            add(lambda item: item["modules"][0]["protocols"][0].update(signal_map=[["valid"]]))
            add(
                lambda item: item["modules"][0].update(
                    memories=[{"name": "ram"}],
                    memory_accesses=[{"access_id": "read", "memory": "ram", "kind": "read", "domain_id": "missing"}],
                )
            )
            add(
                lambda item: item["modules"][0].update(
                    cdc_paths=[
                        {
                            "path_id": "cdc",
                            "signal": "valid",
                            "source_domain": "main",
                            "destination_domain": "missing",
                        }
                    ]
                )
            )
            add(
                lambda item: item["modules"][0].update(
                    control_domains=[
                        {"domain_id": "a", "clock": "clk"},
                        {"domain_id": "b", "clock": "clk"},
                    ],
                    cdc_paths=[
                        {
                            "path_id": "cdc",
                            "signal": "valid",
                            "source_domain": "a",
                            "destination_domain": "b",
                            "safe": True,
                            "synchronizer_stages": 2,
                            "stage_signals": ["sync", "sync"],
                        }
                    ],
                )
            )
            add(
                lambda item: item["modules"][0]["instances"][0]["connections"].append(
                    {"port_name": "clk", "signal_refs": ["clk"]}
                )
            )
            for index, (document, strict) in enumerate(cases):
                path = root / f"invalid-{index}.dvsem.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(SemanticImportError):
                    importer.import_semantics(path, root, strict=strict)


class RequirementsAndStateHardeningTests(TestCase):
    def test_rejects_invalid_requirements_contracts(self) -> None:
        importer = RequirementsManifestImporter()
        self.assertTrue(importer.supports(Path("baseline.DVREQ.JSON")))
        self.assertFalse(importer.supports(Path("baseline.json")))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_json = root / "invalid.dvreq.json"
            invalid_json.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RequirementsImportError, "invalid requirements JSON"):
                importer.import_requirements(invalid_json)

            cases: list[object] = []

            def add(mutator) -> None:
                document = _document()
                mutator(document)
                cases.append(document)

            cases.append([])
            add(lambda item: item.update(unexpected=True))
            add(lambda item: item.update(schema_version=2))
            add(lambda item: item.update(exported_at="not-a-date"))
            add(lambda item: item.update(exported_at="2026-07-19T12:00:00"))
            add(lambda item: item.update(requirements=[]))
            add(lambda item: item["requirements"][0].update(unexpected=True))
            add(lambda item: item["requirements"].__setitem__(0, None))
            add(lambda item: item["requirements"][0].update(requirement_id=""))
            add(lambda item: item["requirements"][0].update(expected_value=""))
            add(lambda item: item["requirements"][0].update(signals=[""]))
            for index, document in enumerate(cases):
                path = root / f"invalid-{index}.requirements.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(RequirementsImportError):
                    importer.import_requirements(path)

    def test_reports_corrupt_failed_untraceable_and_missing_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                adapter_plugins=(
                    AdapterPluginConfig("semantic_importer", "semantic_manifest"),
                    AdapterPluginConfig("requirements_importer", "requirements_manifest"),
                    AdapterPluginConfig("simulator_runner", "questa"),
                ),
            )
            self.assertEqual(read_requirements_baseline(config), ())
            run_root = config.work_dir / "enterprise-runs"
            summaries = (
                ("invalid", "not-json"),
                (
                    "failed",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "adapter": "questa",
                            "family": "simulator",
                            "status": "failed",
                            "traceability_complete": True,
                        }
                    ),
                ),
                (
                    "untraceable",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "adapter": "other",
                            "family": "analyzer",
                            "status": "passed",
                            "traceability_complete": False,
                        }
                    ),
                ),
            )
            for run_id, payload in summaries:
                path = run_root / run_id / "summary.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")

            status = enterprise_status(config)
            codes = {item["code"] for item in status["failures"]}
            self.assertTrue(
                {
                    "semantic_import_missing",
                    "requirements_baseline_missing",
                    "enterprise_run_invalid",
                    "enterprise_run_failed",
                    "enterprise_run_untraceable",
                }
                <= codes
            )

            baseline = config.work_dir / "requirements" / "baseline.json"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(json.dumps({"schema_version": 1, "requirements": [7]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid requirement record"):
                read_requirements_baseline(config)


class EnterpriseProfileAndCLIHardeningTests(TestCase):
    def test_profile_lookup_and_detection_are_fail_closed(self) -> None:
        with self.assertRaisesRegex(LookupError, "unknown enterprise tool profile"):
            enterprise_profile("missing")
        with (
            patch("dv_platform.enterprise.profiles.which", side_effect=lambda command: f"/eda/{command}"),
            patch.dict("os.environ", {"LM_LICENSE_FILE": "27000@licenses"}, clear=True),
        ):
            detected = detect_enterprise_tools()
        self.assertEqual(len(detected), len(ENTERPRISE_TOOL_PROFILES))
        self.assertTrue(all(item.available for item in detected))

    def test_cli_profiles_and_configuration_errors_are_normalized(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            common = ["--repo-root", str(root), "--json"]
            status, payload = _main(common + ["profiles"])
            self.assertEqual(status, 0)
            self.assertEqual(len(payload["data"]["profiles"]), len(ENTERPRISE_TOOL_PROFILES))

            status, payload = _main(common + ["import-requirements", "--input", str(root / "missing.dvreq.json")])
            self.assertEqual(status, 1)
            self.assertEqual(payload["error"]["code"], "enterprise_command_failed")
