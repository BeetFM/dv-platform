import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.coverage import import_coverage_reports, read_coverage_summary
from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.core.config import default_config
from dv_platform.core.models import CoveragePolicy, FormalToolConfig, SimulatorConfig, VerificationTarget


class CoverageIngestionBranchTests(unittest.TestCase):
    def test_empty_and_unsupported_inputs_are_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            with self.assertRaisesRegex(ValueError, "At least one"):
                import_coverage_reports(config, ())
            unsupported = repo / "coverage.bin"
            unsupported.write_bytes(b"data")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                import_coverage_reports(config, (unsupported,))

    def test_importer_probe_and_import_errors_are_wrapped(self) -> None:
        class Importer:
            def __init__(self, fail_probe: bool) -> None:
                self.fail_probe = fail_probe

            def supports(self, _path: Path) -> bool:
                if self.fail_probe:
                    raise RuntimeError("probe failed")
                return True

            def import_coverage(self, _path: Path):
                raise RuntimeError("import failed")

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "vendor.db"
            report.write_text("vendor", encoding="utf-8")
            for fail_probe, message in ((True, "probing"), (False, "import failed")):
                with self.subTest(fail_probe=fail_probe), self.assertRaisesRegex(ValueError, message):
                    import_coverage_reports(default_config(repo), (report,), (Importer(fail_probe),))

    def test_json_shape_and_metric_failure_matrix(self) -> None:
        invalid_payloads = (
            [],
            {"metrics": {"line": -1}},
            {"metrics": {"branch": 101}},
            {"coverage_points": "bad"},
            {"dispositions": "bad"},
            {"coverage_points": ["bad"]},
            {"coverage_points": [{"module": "", "point_id": "p", "covered": True}]},
            {"coverage_points": [{"module": "m", "point_id": "", "covered": True}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "kind": " ", "covered": True}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "status": "invented"}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "hits": -1}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "hits": True}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "covered": 1}]},
            {"coverage_points": [{"module": "m", "point_id": "p"}]},
            {"coverage_points": [{"module": "m", "point_id": "p", "covered": True, "check_ids": "c"}]},
        )
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "coverage.json"
            for payload in invalid_payloads:
                report.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    import_coverage_reports(default_config(repo), (report,))

    def test_disposition_failure_matrix(self) -> None:
        point = {"module": "m", "point_id": "p", "covered": False}
        base = {
            "module": "m",
            "point_id": "p",
            "status": "waived",
            "disposition_id": "d",
            "reason": "accepted gap",
            "approved_by": "lead",
            "expires_at": "2027-01-01",
        }
        invalid = (
            "not-an-object",
            {**base, "status": "covered"},
            {**base, "disposition_id": ""},
            {**base, "reason": ""},
            {**base, "approved_by": ""},
            {**base, "expires_at": ""},
            {**base, "expires_at": "not-a-date"},
            {**base, "evidence_refs": "not-a-list"},
            {
                **base,
                "status": "unreachable",
                "approved_by": None,
                "expires_at": None,
                "evidence_refs": [],
            },
        )
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "coverage.json"
            for disposition in invalid:
                report.write_text(
                    json.dumps({"coverage_points": [point], "dispositions": [disposition]}),
                    encoding="utf-8",
                )
                with self.subTest(disposition=disposition), self.assertRaises(ValueError):
                    import_coverage_reports(default_config(repo), (report,))

    def test_duplicate_point_and_disposition_conflicts_are_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            first = repo / "first.json"
            second = repo / "second.json"
            first.write_text(
                json.dumps(
                    {
                        "coverage_points": [{"module": "m", "point_id": "p", "kind": "cover", "covered": False}],
                        "waivers": [
                            {
                                "module": "m",
                                "point_id": "p",
                                "waiver_id": "w",
                                "reason": "reason one",
                                "approved_by": "lead",
                                "expires_at": "2027-01-01",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {"coverage_points": [{"module": "m", "point_id": "p", "kind": "assertion", "covered": False}]}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "kind conflict"):
                import_coverage_reports(default_config(repo), (first, second))

            second.write_text(
                json.dumps(
                    {
                        "coverage_points": [{"module": "m", "point_id": "p", "kind": "cover", "covered": False}],
                        "waivers": [
                            {
                                "module": "m",
                                "point_id": "p",
                                "waiver_id": "w",
                                "reason": "different reason",
                                "approved_by": "lead",
                                "expires_at": "2027-01-01",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                import_coverage_reports(default_config(repo), (first, second))

    def test_xml_aggregate_lcov_eof_and_json_module_shapes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            xml = repo / "coverage.xml"
            xml.write_text('<coverage line-rate="0.75" branch-rate="0.5"/>', encoding="utf-8")
            lcov = repo / "coverage.info"
            lcov.write_text("ignored\nSF:rtl/top.sv\nLF:4\nLH:3\n", encoding="utf-8")
            mapping = repo / "mapping.json"
            mapping.write_text(json.dumps({"modules": {"top": {"functional": 80}}}), encoding="utf-8")

            _path, summary = import_coverage_reports(default_config(repo), (xml, lcov, mapping))

            self.assertEqual(summary["metrics"]["line"]["percentage"], 75.0)
            self.assertEqual(summary["metrics"]["functional"]["percentage"], 80.0)

            xml.write_text("<coverage/>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no supported metrics"):
                import_coverage_reports(default_config(repo), (xml,))

    def test_covered_point_with_disposition_is_stale_and_strictly_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "coverage.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            {
                                "module": "m",
                                "point_id": "p",
                                "kind": "assertion",
                                "covered": True,
                                "check_ids": ["c"],
                            }
                        ],
                        "unreachable": [
                            {
                                "module": "m",
                                "point_id": "p",
                                "disposition_id": "u",
                                "reason": "proof",
                                "evidence_refs": ["formal:proof"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            _path, summary = import_coverage_reports(replace(default_config(repo), strict=True), (report,))

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["closure"]["stale_dispositions"][0]["disposition_id"], "u")

    def test_summary_non_object_and_old_schema_are_handled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            path = config.work_dir / "coverage" / "summary.json"
            path.parent.mkdir(parents=True)
            path.write_text("[]", encoding="utf-8")
            self.assertIsNone(read_coverage_summary(config))
            path.write_text(json.dumps({"schema_version": 0}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "minimum readable"):
                read_coverage_summary(config)


class StatusPolicyBranchTests(unittest.TestCase):
    def test_closure_and_plan_feedback_failures_are_independent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            status = collect_platform_status(default_config(Path(temp_dir)))
            status["coverage"] = {
                "passed": False,
                "closure": {
                    "present": True,
                    "counts": {"failed": 2, "uncovered": 3},
                    "traceability_complete": False,
                    "stale_dispositions": [{"point_id": "p"}],
                },
                "plan_feedback": {
                    "plans_available": False,
                    "unmeasured_checks": [{"check_id": "c"}],
                    "stale_point_mappings": [{"point_id": "p"}],
                },
            }

            codes = {failure["code"] for failure in evaluate_status_policy(status, require_tools=False)}

            self.assertTrue(
                {
                    "coverage_gate_failed",
                    "coverage_checks_failed",
                    "coverage_closure_open",
                    "coverage_traceability_incomplete",
                    "coverage_dispositions_stale",
                    "coverage_checks_unmeasured",
                    "coverage_plan_mappings_stale",
                    "coverage_plans_missing",
                }
                <= codes
            )

    def test_missing_configured_tools_are_reported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = replace(
                default_config(Path(temp_dir)),
                verilator_executable="definitely-missing-verilator",
                simulators=(SimulatorConfig(VerificationTarget.COCOTB, "missing-sim", "definitely-missing-sim --run"),),
                formal_tools=(FormalToolConfig("missing-formal", "definitely-missing-formal prove"),),
                coverage_policy=CoveragePolicy(line_minimum=90),
            )
            codes = {
                failure["code"]
                for failure in evaluate_status_policy(collect_platform_status(config), require_tools=True)
            }

            self.assertTrue(
                {"verilator_missing", "simulator_missing", "formal_tool_missing", "coverage_missing"} <= codes
            )


if __name__ == "__main__":
    unittest.main()
