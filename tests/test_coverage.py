import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.coverage import import_coverage_reports, read_coverage_summary
from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.cli import main
from dv_platform.core.config import default_config
from dv_platform.core.models import CoveragePolicy, VerificationCheck, VerificationPlan, VerificationTarget


class CoverageImportTests(unittest.TestCase):
    def test_import_lcov_merges_counts_and_enforces_thresholds(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(
                default_config(repo),
                coverage_policy=CoveragePolicy(line_minimum=80.0, branch_minimum=60.0),
            )
            first = repo / "first.info"
            first.write_text(
                "SF:rtl/a.sv\nLF:10\nLH:9\nBRF:4\nBRH:3\nend_of_record\n",
                encoding="utf-8",
            )
            second = repo / "second.info"
            second.write_text(
                "SF:rtl/b.sv\nLF:10\nLH:7\nBRF:6\nBRH:3\nend_of_record\n",
                encoding="utf-8",
            )

            path, summary = import_coverage_reports(config, (first, second))

            self.assertEqual(path, repo / ".dv-platform" / "coverage" / "summary.json")
            self.assertEqual(summary["metrics"]["line"]["percentage"], 80.0)
            self.assertEqual(summary["metrics"]["branch"]["percentage"], 60.0)
            self.assertTrue(summary["passed"])
            self.assertEqual(read_coverage_summary(config), summary)
            self.assertTrue(any(gap["module"] == "rtl/b.sv" for gap in summary["gaps"]))
            self.assertTrue((path.parent / "summary.md").is_file())
            self.assertTrue((path.parent / "summary.yaml").is_file())
            self.assertTrue((path.parent / "closure.sarif").is_file())

    def test_import_json_reports_missing_configured_metric_as_failed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(
                default_config(repo),
                coverage_policy=CoveragePolicy(toggle_minimum=70.0),
            )
            report = repo / "coverage.json"
            report.write_text(json.dumps({"metrics": {"line": 95.0}}), encoding="utf-8")

            _path, summary = import_coverage_reports(config, (report,))

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["gates"][0]["reason"], "metric missing")

    def test_status_policy_requires_import_when_coverage_policy_is_enabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = replace(
                default_config(Path(temp_dir)),
                coverage_policy=CoveragePolicy(functional_minimum=75.0),
            )

            failures = evaluate_status_policy(collect_platform_status(config), require_tools=False)

            self.assertIn("coverage_missing", {failure["code"] for failure in failures})

    def test_failed_point_is_an_actionable_closure_gap(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            report = repo / "run-summary.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            {
                                "module": "fifo",
                                "point_id": "cocotb:fifo:check:ordering",
                                "kind": "functional",
                                "status": "failed",
                                "check_ids": ["fifo:check:ordering"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            _path, summary = import_coverage_reports(config, (report,))

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["closure"]["counts"]["failed"], 1)
            self.assertEqual(summary["closure_gaps"][0]["status"], "failed")
            sarif = json.loads((repo / ".dv-platform" / "coverage" / "closure.sarif").read_text())
            self.assertEqual(sarif["runs"][0]["results"][0]["level"], "error")
            failures = evaluate_status_policy(collect_platform_status(config), require_tools=False)
            self.assertIn("coverage_checks_failed", {failure["code"] for failure in failures})

    def test_waiver_requires_approval_and_orphan_dispositions_are_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            report = repo / "closure.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [{"module": "fifo", "point_id": "cp:empty", "covered": False}],
                        "waivers": [
                            {
                                "module": "fifo",
                                "point_id": "cp:missing",
                                "disposition_id": "waiver:1",
                                "reason": "Not implemented in this specialization.",
                                "approved_by": "verification-lead",
                                "expires_at": "2027-01-01",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unknown points"):
                import_coverage_reports(config, (report,))

            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["waivers"][0]["point_id"] = "cp:empty"
            del payload["waivers"][0]["approved_by"]
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved_by"):
                import_coverage_reports(config, (report,))

    def test_expired_waiver_remains_an_actionable_gap(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "closure.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [{"module": "fifo", "point_id": "cp:empty", "covered": False}],
                        "waivers": [
                            {
                                "module": "fifo",
                                "point_id": "cp:empty",
                                "disposition_id": "waiver:expired",
                                "reason": "Temporary architectural waiver.",
                                "approved_by": "verification-lead",
                                "expires_at": "2026-01-01",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            _path, summary = import_coverage_reports(default_config(repo), (report,), as_of=date(2026, 7, 19))

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["closure"]["counts"]["uncovered"], 1)
            self.assertEqual(summary["closure"]["expired_dispositions"][0]["disposition_id"], "waiver:expired")

    def test_point_import_reconciles_plan_checks_and_exposes_unmeasured_checks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            plan = VerificationPlan(
                module="fifo",
                targets=(VerificationTarget.COCOTB,),
                check_details=(
                    VerificationCheck("fifo:check:ordering", "Verify ordering.", executable=True),
                    VerificationCheck("fifo:check:error", "Verify errors.", executable=True),
                ),
            )
            write_plan_outputs(config, (plan,))
            report = repo / "closure.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            {
                                "module": "fifo",
                                "point_id": "cp:ordering",
                                "status": "covered",
                                "check_ids": ["fifo:check:ordering"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            _path, summary = import_coverage_reports(config, (report,))
            stored = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["plan_feedback"]["mapped_checks"], 1)
            self.assertEqual(len(summary["plan_feedback"]["unmeasured_checks"]), 1)
            self.assertEqual(stored.check_details[0].closure_status, "covered")
            self.assertEqual(stored.check_details[0].coverage_point_ids, ("cp:ordering",))
            self.assertEqual(stored.check_details[1].closure_status, "unmeasured")

    def test_vendor_importer_is_dispatched_and_core_gates_normalized_output(self) -> None:
        class FakeUCISImporter:
            def supports(self, path: Path) -> bool:
                return path.suffix == ".ucis"

            def import_coverage(self, path: Path) -> dict[str, object]:
                return {
                    "coverage_points": [
                        {
                            "module": "fifo",
                            "point_id": "ucis:cover:empty",
                            "kind": "coverpoint",
                            "covered": False,
                            "requirement_ids": ["fifo:req:empty"],
                        }
                    ]
                }

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "coverage.ucis"
            report.write_bytes(b"vendor database")

            _path, summary = import_coverage_reports(
                default_config(repo),
                (report,),
                coverage_importers=(FakeUCISImporter(),),
            )

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["closure"]["counts"]["uncovered"], 1)

    def test_coverage_summary_migrates_v1_and_rejects_future_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            summary_path = config.work_dir / "coverage" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps({"schema_version": 1, "metrics": {}, "modules": [], "gates": [], "passed": True}),
                encoding="utf-8",
            )

            migrated = read_coverage_summary(config)

            self.assertIsNotNone(migrated)
            self.assertEqual(migrated["schema_version"], 3)
            self.assertFalse(migrated["parameter_sweeps"]["present"])
            self.assertFalse(migrated["closure"]["present"])
            summary_path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported coverage schema version"):
                read_coverage_summary(config)
            failures = evaluate_status_policy(collect_platform_status(config), require_tools=False)
            self.assertIn("coverage_schema_invalid", {failure["code"] for failure in failures})

    def test_coverage_command_imports_persisted_module_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            run_summary = repo / ".dv-platform" / "runs" / "formal" / "fifo" / "summary.json"
            run_summary.parent.mkdir(parents=True)
            run_summary.write_text(
                json.dumps(
                    {
                        "formal_points": [
                            {
                                "module": "fifo",
                                "point_id": "formal:fifo:check:reset",
                                "status": "covered",
                                "check_ids": ["fifo:check:reset"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            exit_code = main(["--repo-root", str(repo), "coverage", "--from-runs"])
            summary = json.loads((repo / ".dv-platform" / "coverage" / "summary.json").read_text())

            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["closure"]["counts"]["covered"], 1)

    def test_bounded_and_unsupported_formal_points_remain_actionable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            report = repo / "formal.json"
            report.write_text(
                json.dumps(
                    {
                        "formal_points": [
                            {"module": "bridge", "point_id": "cdc:bounded", "status": "bounded_pass"},
                            {"module": "bridge", "point_id": "cdc:hidden", "status": "unsupported"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            _path, summary = import_coverage_reports(config, (report,))

            self.assertFalse(summary["closure"]["passed"])
            self.assertEqual(summary["closure"]["counts"]["bounded_pass"], 1)
            self.assertEqual(summary["closure"]["counts"]["unsupported"], 1)
            self.assertEqual(summary["closure"]["counts"]["actionable"], 2)

    def test_protocol_transaction_vendor_and_filter_fields_are_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            report = repo / "functional.json"
            report.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            {
                                "module": "fabric",
                                "point_id": "axi:burst-cross",
                                "kind": "cross",
                                "hits": 2,
                                "check_id": "CHK-AXI",
                                "cross_members": ["burst_length", "response"],
                                "vendor_provenance": {"adapter": "vivado", "database": "run-7"},
                                "protocol_transaction": {
                                    "profile_id": "axi4-1.0",
                                    "channel": "R",
                                    "trace_id": "trace-1",
                                    "beat": 3,
                                },
                                "severity": "high",
                                "confidence": "measured",
                                "target": "uvm",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            _path, summary = import_coverage_reports(default_config(repo), (report,))
            point = summary["closure"]["points"][0]
            self.assertEqual(point["check_ids"], ["CHK-AXI"])
            self.assertEqual(point["protocol_transaction"]["profile_id"], "axi4-1.0")
            self.assertEqual(point["vendor_provenance"]["adapter"], "vivado")
            self.assertEqual(point["cross_members"], ["burst_length", "response"])
            self.assertEqual((point["severity"], point["confidence"], point["target"]), ("high", "measured", "uvm"))


if __name__ == "__main__":
    unittest.main()
