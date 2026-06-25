from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans, write_plan_outputs
from dv_platform.core.config import default_config
from dv_platform.core.models import ClaimStatus, VerificationClaim, VerificationPlan, VerificationTarget


class PlanStoreTests(unittest.TestCase):
    def test_write_plan_outputs_persists_sqlite_and_markdown_views(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            plan = VerificationPlan(
                module="fifo",
                targets=(VerificationTarget.COCOTB,),
                claims=(VerificationClaim("fifo:clock", "fifo", "clock exists", status=ClaimStatus.SUPPORTED),),
                checks=("Drive clock.",),
                requirements=("FIFO increments count.",),
            )

            sqlite_path, module_paths, index_path, claim_report_paths = write_plan_outputs(config, (plan,))

            self.assertEqual(sqlite_path, repo / ".dv-platform" / "plans" / "plans.sqlite")
            self.assertEqual(module_paths, (repo / ".dv-platform" / "plans" / "modules" / "fifo.plan.md",))
            self.assertEqual(index_path, repo / ".dv-platform" / "plans" / "index.md")
            self.assertEqual(
                claim_report_paths,
                (
                    repo / ".dv-platform" / "plans" / "claims" / "fifo" / "claims.json",
                    repo / ".dv-platform" / "plans" / "claims" / "fifo" / "claims.md",
                ),
            )
            self.assertIn("# fifo Verification Plan", module_paths[0].read_text(encoding="utf-8"))
            self.assertIn("| fifo | 1 | 0 |", index_path.read_text(encoding="utf-8"))
            self.assertIn("# Claim Report", claim_report_paths[1].read_text(encoding="utf-8"))

            records = read_plan_records(sqlite_path)
            self.assertEqual(records[0]["module"], "fifo")
            self.assertEqual(records[0]["plan"]["checks"], ["Drive clock."])
            self.assertTrue(records[0]["gate"]["allowed"])

            loaded_plans = read_stored_plans(sqlite_path)
            self.assertEqual(loaded_plans, (plan,))

    def test_write_plan_outputs_replaces_previous_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)

            write_plan_outputs(config, (VerificationPlan(module="old", targets=()),))
            sqlite_path, _, _, _ = write_plan_outputs(config, (VerificationPlan(module="new", targets=()),))

            records = read_plan_records(sqlite_path)
            self.assertEqual(tuple(record["module"] for record in records), ("new",))


if __name__ == "__main__":
    unittest.main()
