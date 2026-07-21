import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import (
    PLAN_SCHEMA_VERSION,
    plan_from_json,
    read_plan_records,
    read_stored_plans,
    write_plan_outputs,
)
from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLCDCPath,
    RTLClock,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLParameter,
    RTLPort,
    RTLProtocol,
    RTLReset,
    RTLType,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)


class PlanStoreTests(unittest.TestCase):
    def test_v16_scenarios_migrate_without_preserving_executable_claims(self) -> None:
        plan = plan_from_json(
            {
                "schema_version": 16,
                "module": "legacy_apb",
                "targets": ["cocotb"],
                "scenarios": [
                    {
                        "scenario_id": "legacy:scenario:1",
                        "kind": "apb4_transfer",
                        "stimulus": [{"kind": "next_cycle"}],
                        "oracle": {"kind": "handshake"},
                        "completion": {"kind": "cycles", "timeout_cycles": 4},
                        "coverage_goals": [{"goal_id": "goal", "kind": "transfer"}],
                        "supported_targets": ["cocotb"],
                        "executable": True,
                    }
                ],
            }
        )

        scenario = plan.scenarios[0]
        self.assertFalse(scenario.executable)
        self.assertEqual(scenario.supported_targets, ())
        self.assertEqual(str(scenario.target_states[0].state), "unsupported")
        self.assertIn("re-plan", scenario.target_states[0].reason or "")

    def test_write_plan_outputs_persists_sqlite_and_markdown_views(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            plan = VerificationPlan(
                module="fifo",
                targets=(VerificationTarget.COCOTB,),
                design_unit="fifo_rtl",
                elaborated_design_unit="fifo_rtl__D2",
                specialization_id="spec1234",
                design_unit_kind="module",
                ports=(
                    RTLPort(name="clk", direction="input"),
                    RTLPort(name="en", direction="input", width=1),
                    RTLPort(name="count", direction="output", width=8, signed=True),
                ),
                clocks=(RTLClock(name="clk", direction="input", classification="sensitivity"),),
                resets=(RTLReset(name="reset", direction="input", active_low=False, classification="sensitivity"),),
                parameters=(RTLParameter(name="WIDTH", default_value="32'h8", width=32),),
                memories=(RTLMemory(name="storage", element_width=8, depth=2),),
                memory_accesses=(
                    RTLMemoryAccess(
                        "fifo:memory:storage:write:1",
                        "storage",
                        "write",
                        address_signals=("address",),
                        data_signals=("data",),
                        enable_signals=("enable",),
                        synchronous=True,
                    ),
                ),
                type_details=(RTLType("packet", "packet_t", "structdtype", members=("data", "tag")),),
                instances=(
                    RTLInstance(
                        name="u_child",
                        module_name="child",
                        elaborated_module_name="child__W8",
                        connections=(
                            RTLConnection(
                                port_name="data",
                                direction="input",
                                signal_refs=("count",),
                                expression=RTLExpression(kind="varref", name="count"),
                            ),
                        ),
                    ),
                ),
                control_domains=(RTLControlDomain("domain_1", "clk", reset="reset"),),
                cdc_paths=(RTLCDCPath("fifo:cdc:flag", "flag", "domain_1", "domain_2", safe=False),),
                generate_scopes=(RTLGenerateScope("lanes", "lanes", "begin", instance_names=("lanes.0",)),),
                imports=("fifo_types",),
                protocols=(RTLProtocol("fifo:ready_valid:in", "ready_valid", "in", "sink", "en", "count"),),
                structured_requirements=(
                    VerificationRequirement(
                        requirement_id="fifo:docreq:1",
                        scope="fifo",
                        statement="FIFO increments count.",
                        category="increment",
                        signals=("enable", "count"),
                        expected_value="1",
                        condition="enable",
                        confidence="deterministic",
                        evidence_refs=(EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/fifo.md", "chunk:1"),),
                    ),
                ),
                requirement_conflicts=(
                    RequirementConflict(
                        conflict_id="fifo:conflict:test",
                        scope="fifo",
                        requirement_ids=("fifo:docreq:1", "fifo:docreq:2"),
                        reason="Test conflict record.",
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
                        domain_id="domain_1",
                        evidence_refs=(
                            EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "procedure:fifo.alwaysff"),
                        ),
                    ),
                ),
                claims=(VerificationClaim("fifo:clock", "fifo", "clock exists", status=ClaimStatus.SUPPORTED),),
                checks=("Drive clock.",),
                check_details=(VerificationCheck("fifo:check:clock", "Drive clock.", "clock", False),),
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
            self.assertIn("## Protocol Channels", module_paths[0].read_text(encoding="utf-8"))
            self.assertIn("| fifo | 1 | 0 |", index_path.read_text(encoding="utf-8"))
            self.assertIn("# Claim Report", claim_report_paths[1].read_text(encoding="utf-8"))

            records = read_plan_records(sqlite_path)
            self.assertEqual(records[0]["module"], "fifo")
            self.assertEqual(records[0]["plan"]["schema_version"], PLAN_SCHEMA_VERSION)
            self.assertEqual(records[0]["plan"]["ports"][2]["name"], "count")
            self.assertEqual(records[0]["plan"]["ports"][2]["width"], 8)
            self.assertTrue(records[0]["plan"]["ports"][2]["signed"])
            self.assertEqual(records[0]["plan"]["clocks"][0]["classification"], "sensitivity")
            self.assertFalse(records[0]["plan"]["resets"][0]["active_low"])
            self.assertEqual(records[0]["plan"]["checks"], ["Drive clock."])
            self.assertEqual(records[0]["plan"]["structured_requirements"][0]["requirement_id"], "fifo:docreq:1")
            self.assertEqual(records[0]["plan"]["structured_requirements"][0]["category"], "increment")
            self.assertEqual(records[0]["plan"]["requirement_conflicts"][0]["conflict_id"], "fifo:conflict:test")
            self.assertEqual(records[0]["plan"]["behaviors"][0]["behavior_id"], "fifo:behavior:1:1")
            self.assertEqual(records[0]["plan"]["behaviors"][0]["kind"], "increment")
            self.assertTrue(records[0]["gate"]["allowed"])

            loaded_plans = read_stored_plans(sqlite_path)
            self.assertEqual(loaded_plans, (plan,))

    def test_write_plan_outputs_rejects_module_path_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            plan = VerificationPlan(module="../../outside", targets=())

            with self.assertRaisesRegex(ValueError, "path separators"):
                write_plan_outputs(config, (plan,))

    def test_write_plan_outputs_removes_stale_human_views(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            write_plan_outputs(config, (VerificationPlan(module="old", targets=()),))

            write_plan_outputs(config, (VerificationPlan(module="new", targets=()),))

            self.assertFalse((config.work_dir / "plans" / "modules" / "old.plan.md").exists())
            self.assertFalse((config.work_dir / "plans" / "claims" / "old").exists())

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
