import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.plan_store import PLAN_SCHEMA_VERSION, read_plan_records, read_stored_plans, write_plan_outputs
from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    RTLPort,
    VerificationBehavior,
    VerificationClaim,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)


class PlanStoreTests(unittest.TestCase):
    def test_write_plan_outputs_persists_sqlite_and_markdown_views(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            plan = VerificationPlan(
                module="fifo",
                targets=(VerificationTarget.COCOTB,),
                ports=(
                    RTLPort(name="clk", direction="input"),
                    RTLPort(name="en", direction="input", width=1),
                    RTLPort(name="count", direction="output", width=8, signed=True),
                ),
                structured_requirements=(
                    VerificationRequirement(
                        requirement_id="fifo:docreq:1",
                        scope="fifo",
                        statement="FIFO increments count.",
                        evidence_refs=(EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/fifo.md", "chunk:1"),),
                    ),
                ),
                behaviors=(
                    VerificationBehavior(
                        behavior_id="fifo:behavior:1:1",
                        scope="fifo",
                        kind="increment",
                        target="count_o",
                        control="enable_i",
                        source="count_o",
                        evidence_refs=(EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "procedure:fifo.alwaysff"),),
                    ),
                ),
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
            self.assertEqual(records[0]["plan"]["schema_version"], PLAN_SCHEMA_VERSION)
            self.assertEqual(records[0]["plan"]["ports"][2]["name"], "count")
            self.assertEqual(records[0]["plan"]["ports"][2]["width"], 8)
            self.assertTrue(records[0]["plan"]["ports"][2]["signed"])
            self.assertEqual(records[0]["plan"]["checks"], ["Drive clock."])
            self.assertEqual(records[0]["plan"]["structured_requirements"][0]["requirement_id"], "fifo:docreq:1")
            self.assertEqual(records[0]["plan"]["behaviors"][0]["behavior_id"], "fifo:behavior:1:1")
            self.assertEqual(records[0]["plan"]["behaviors"][0]["kind"], "increment")
            self.assertTrue(records[0]["gate"]["allowed"])

            loaded_plans = read_stored_plans(sqlite_path)
            self.assertEqual(loaded_plans, (plan,))

    def test_read_stored_plans_migrates_legacy_versionless_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "plans.sqlite"
            with sqlite3.connect(sqlite_path) as connection:
                connection.execute(
                    """
                    create table plans (
                        module text primary key,
                        plan_json text not null,
                        gate_json text not null
                    )
                    """
                )
                connection.execute(
                    "insert into plans(module, plan_json, gate_json) values (?, ?, ?)",
                    (
                        "legacy",
                        json.dumps(
                            {
                                "module": "legacy",
                                "targets": ["cocotb"],
                                "requirements": [],
                                "structured_requirements": [],
                                "claims": [],
                                "checks": [],
                                "assumptions": [],
                                "open_questions": [],
                            }
                        ),
                        json.dumps({"allowed": True, "blocked": [], "warnings": []}),
                    ),
                )
                connection.commit()

            plans = read_stored_plans(sqlite_path)

            self.assertEqual(plans, (VerificationPlan(module="legacy", targets=(VerificationTarget.COCOTB,)),))

    def test_read_stored_plans_rejects_future_schema_version(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "plans.sqlite"
            with sqlite3.connect(sqlite_path) as connection:
                connection.execute(
                    """
                    create table plans (
                        module text primary key,
                        plan_json text not null,
                        gate_json text not null
                    )
                    """
                )
                connection.execute(
                    "insert into plans(module, plan_json, gate_json) values (?, ?, ?)",
                    (
                        "future",
                        json.dumps(
                            {
                                "schema_version": PLAN_SCHEMA_VERSION + 1,
                                "module": "future",
                                "targets": ["cocotb"],
                            }
                        ),
                        json.dumps({"allowed": True, "blocked": [], "warnings": []}),
                    ),
                )
                connection.commit()

            with self.assertRaisesRegex(ValueError, "Unsupported plan schema version"):
                read_stored_plans(sqlite_path)

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
