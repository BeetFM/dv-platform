import json
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent
from dv_platform.analysis.revisions import (
    create_feedback_revision,
    read_revision_plan,
    read_revisions,
    record_revision,
    record_revision_generation,
)
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    ScenarioCompletion,
    ScenarioOracle,
    ScenarioStimulus,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)


class FeedbackRevisionTests(unittest.TestCase):
    def test_invalid_proposal_is_rejected_without_mutating_plan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,))
            event = FeedbackEvent("e1", "run", VerificationTarget.COCOTB, "top", "fail", check_id="c1")
            valid = AgentProposal(
                "p1", "task", "check", "valid", (EvidenceRef(EvidenceKind.TOOL_LOG, "E1", "E1"),), {"check_id": "c2"}
            )
            invalid = AgentProposal("p2", "task", "check", "invalid", (EvidenceRef(EvidenceKind.TOOL_LOG, "E9", "E9"),))
            revision = create_feedback_revision(root, plan, (event,), proposals=(valid, invalid), evidence_ids={"E1"})
            self.assertEqual(revision.accepted_proposal_ids, ("p1",))
            self.assertEqual(revision.rejected_proposal_ids, ("p2",))
            self.assertEqual(revision.resulting_plan_hash, revision.input_plan_hash)
            self.assertEqual(revision.schema_version, 3)
            self.assertEqual(revision.affected_check_ids, ("c1",))
            self.assertEqual(revision.required_rerun_targets, ("cocotb",))
            self.assertEqual(
                tuple(state for proposal, state, _reason in revision.operation_states if proposal == "p1"),
                ("proposed", "validated", "no-op"),
            )
            self.assertEqual(
                tuple(state for proposal, state, _reason in revision.operation_states if proposal == "p2"),
                ("proposed", "rejected"),
            )
            self.assertEqual(plan, VerificationPlan("top", (VerificationTarget.COCOTB,)))
            self.assertEqual(read_revisions(root, "top"), (revision,))

    def test_revision_records_are_append_only(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = VerificationPlan("top", ())
            first = create_feedback_revision(root, plan, (), dry_run=True)
            record_revision(root, first)
            second = create_feedback_revision(root, plan, (), dry_run=False)
            revisions = read_revisions(root, "top")
            self.assertEqual(len(revisions), 2)
            self.assertEqual(second.parent_revision_id, first.revision_id)
            self.assertEqual(second.parent_snapshot_hash, first.resulting_plan_hash)

    def test_changed_canonical_or_rtl_inputs_require_an_explicit_fork(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project-manifest.json").write_text('{"rtl":"one"}\n', encoding="utf-8")
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,))
            first = create_feedback_revision(root, plan, ())
            changed = replace(plan, checks=("new intent",))

            with self.assertRaisesRegex(ValueError, "explicitly fork"):
                create_feedback_revision(root, changed, ())
            fork = create_feedback_revision(root, changed, (), fork_on_input_change=True)

            self.assertIsNone(fork.parent_revision_id)
            self.assertNotEqual(fork.canonical_plan_hash, first.canonical_plan_hash)

    def test_scenario_template_parameters_round_trip_and_unknown_values_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = VerificationScenario(
                "s1",
                "reset_sequence",
                (ScenarioStimulus("hold", parameters=(("cycles", "2"),)),),
                ScenarioOracle("equals", "rst_n", "0"),
                ScenarioCompletion("cycles", timeout_cycles=4),
                (),
                (VerificationTarget.COCOTB,),
            )
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,), scenarios=(scenario,))
            revision = create_feedback_revision(
                root,
                plan,
                (),
                scenario_selections=(("s1", (("0:hold:cycles", "2"),)),),
                affected_artifact_paths=("test_top.py",),
            )

            self.assertEqual(read_revisions(root, "top")[0].scenario_selections, revision.scenario_selections)
            self.assertEqual(revision.affected_scenario_ids, ("s1",))
            self.assertEqual(revision.affected_artifact_paths, ("test_top.py",))
            self.assertEqual(revision.required_rerun_targets, ("cocotb",))
            with self.assertRaisesRegex(ValueError, "undeclared template parameters"):
                create_feedback_revision(
                    root,
                    plan,
                    (),
                    scenario_selections=(("s1", (("0:hold:cycles", "3"),)),),
                )
            with self.assertRaisesRegex(ValueError, "at most once"):
                create_feedback_revision(
                    root,
                    plan,
                    (),
                    scenario_selections=(("s1", ()), ("s1", ())),
                )
            with self.assertRaisesRegex(ValueError, "unknown deterministic template"):
                create_feedback_revision(root, plan, (), scenario_selections=(("missing", ()),))
            with self.assertRaisesRegex(ValueError, "unknown templates"):
                create_feedback_revision(root, plan, (), selected_scenario_ids=("missing",))

    def test_revision_generation_state_merges_targets_and_rejects_malformed_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,))
            revision = create_feedback_revision(root, plan, (), dry_run=True)
            provenance = root / "provenance.json"
            provenance.write_text('{"target":"cocotb"}\n', encoding="utf-8")

            path = record_revision_generation(root, revision, "cocotb", provenance)
            record_revision_generation(root, revision, "formal", provenance)
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(state["generated_targets"]), {"cocotb", "formal"})

            state["revision_id"] = "wrong"
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "generation state is invalid"):
                record_revision_generation(root, revision, "cocotb", provenance)
            state["revision_id"] = revision.revision_id
            state["generated_targets"] = []
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "target state is invalid"):
                record_revision_generation(root, revision, "cocotb", provenance)

    def test_legacy_revision_database_and_invalid_snapshot_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "plans" / "revisions.sqlite"
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "create table plan_revisions (revision_id text primary key, module text not null, "
                    "revision_json text not null, created_at text not null)"
                )
                connection.commit()
            self.assertIsNone(read_revision_plan(root, "legacy"))

            plan = VerificationPlan("top", ())
            revision = create_feedback_revision(root, plan, (), dry_run=True)
            record_revision(root, revision, resulting_plan=plan)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "update plan_revisions set snapshot_json = ? where revision_id = ?",
                    ("[]", revision.revision_id),
                )
                connection.commit()
            with self.assertRaisesRegex(ValueError, "invalid plan snapshot"):
                read_revision_plan(root, revision.revision_id)


if __name__ == "__main__":
    unittest.main()
