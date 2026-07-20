import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent
from dv_platform.analysis.revisions import create_feedback_revision, read_revisions, record_revision
from dv_platform.core.models import EvidenceKind, EvidenceRef, VerificationPlan, VerificationTarget


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


if __name__ == "__main__":
    unittest.main()
