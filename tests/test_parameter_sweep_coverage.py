import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.coverage import import_coverage_reports
from dv_platform.analysis.plan_store import write_plan_outputs
from dv_platform.core.config import default_config
from dv_platform.core.models import RTLParameter, VerificationCheck, VerificationPlan, VerificationTarget


class ParameterSweepCoverageTests(unittest.TestCase):
    def test_cross_point_aggregation_requires_closed_evidence_at_every_sweep(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                parameter_sweeps=(("WIDTH=4",), ("WIDTH=8",)),
                top_modules=("counter",),
            )
            plans = (
                self._plan("counter__sweep_a", "spec-a", "4", "check-a"),
                self._plan("counter__sweep_b", "spec-b", "8", "check-b"),
            )
            write_plan_outputs(config, plans)
            complete = root / "complete.json"
            complete.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            self._point("counter__sweep_a", "check-a", "covered"),
                            self._point("counter__sweep_b", "check-b", "covered"),
                        ]
                    }
                ),
                encoding="utf-8",
            )

            _path, passed = import_coverage_reports(config, (complete,))

            sweeps = passed["parameter_sweeps"]
            self.assertTrue(sweeps["present"])
            self.assertTrue(sweeps["passed"])
            self.assertEqual(sweeps["configured_points"], 2)
            cross_point = sweeps["groups"][0]["cross_points"][0]
            self.assertTrue(cross_point["passed"])
            self.assertEqual({item["status"] for item in cross_point["results"]}, {"covered"})
            self.assertIn("Parameter Sweep Cross-Points", (config.work_dir / "coverage" / "summary.md").read_text())

    def test_cross_point_aggregation_reports_missing_or_open_sweep_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                parameter_sweeps=(("WIDTH=4",), ("WIDTH=8",)),
                top_modules=("counter",),
            )
            write_plan_outputs(
                config,
                (
                    self._plan("counter__sweep_a", "spec-a", "4", "check-a"),
                    self._plan("counter__sweep_b", "spec-b", "8", "check-b"),
                ),
            )
            incomplete = root / "incomplete.json"
            incomplete.write_text(
                json.dumps(
                    {
                        "coverage_points": [
                            self._point("counter__sweep_a", "check-a", "covered"),
                            self._point("counter__sweep_b", "check-b", "uncovered"),
                        ]
                    }
                ),
                encoding="utf-8",
            )

            _path, payload = import_coverage_reports(config, (incomplete,))

            self.assertFalse(payload["passed"])
            self.assertFalse(payload["parameter_sweeps"]["passed"])
            self.assertTrue(payload["parameter_sweeps"]["gaps"])
            self.assertIn("parameter-sweep cross-point coverage is incomplete", payload["closure"]["policy_failures"])

    @staticmethod
    def _plan(module: str, specialization: str, width: str, check_id: str) -> VerificationPlan:
        return VerificationPlan(
            module,
            (VerificationTarget.COCOTB,),
            design_unit="counter",
            specialization_id=specialization,
            parameters=(RTLParameter("WIDTH", default_value=width),),
            checks=(f"Verify connectivity for module {module}.",),
            check_details=(
                VerificationCheck(
                    check_id,
                    f"Verify connectivity for module {module}.",
                    "connectivity",
                    True,
                ),
            ),
        )

    @staticmethod
    def _point(module: str, check_id: str, status: str) -> dict[str, object]:
        return {
            "module": module,
            "point_id": f"point:{module}",
            "kind": "functional",
            "status": status,
            "check_ids": [check_id],
        }


if __name__ == "__main__":
    unittest.main()
