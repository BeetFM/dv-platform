import unittest
from pathlib import Path

from dv_platform.agent.contracts import FeedbackEvent
from dv_platform.core.models import (
    ArtifactKind,
    ArtifactTrace,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    VerificationTarget,
)
from dv_platform.generators.artifacts import select_affected_artifacts


class TargetedRegenerationTests(unittest.TestCase):
    def test_only_artifacts_depending_on_failed_check_are_selected(self) -> None:
        ref = EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "checks")
        first = GeneratedArtifact(
            Path("first.sv"),
            ArtifactKind.TESTBENCH,
            VerificationTarget.SYSTEMVERILOG,
            "module first; endmodule\n",
            "top",
            provenance_refs=(ref,),
            traceability=(ArtifactTrace("t1", "first", check_ids=("check-1",), evidence_refs=(ref,)),),
        )
        second = GeneratedArtifact(
            Path("second.sv"),
            ArtifactKind.TESTBENCH,
            VerificationTarget.SYSTEMVERILOG,
            "module second; endmodule\n",
            "top",
            provenance_refs=(ref,),
            traceability=(ArtifactTrace("t2", "second", check_ids=("check-2",), evidence_refs=(ref,)),),
        )
        event = FeedbackEvent("event-1", "run-1", VerificationTarget.SYSTEMVERILOG, "top", "fail", check_id="check-1")
        self.assertEqual(select_affected_artifacts((first, second), (event,)), (first,))

    def test_explicit_artifact_locator_is_also_supported(self) -> None:
        ref = EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "checks")
        artifact = GeneratedArtifact(
            Path("second.sv"),
            ArtifactKind.TESTBENCH,
            VerificationTarget.SYSTEMVERILOG,
            "module second; endmodule\n",
            "top",
            provenance_refs=(ref,),
            traceability=(ArtifactTrace("t2", "second", evidence_refs=(ref,)),),
        )
        event = FeedbackEvent(
            "event-2", "run-1", VerificationTarget.SYSTEMVERILOG, "top", "fail", affected_artifacts=("second.sv",)
        )
        self.assertEqual(select_affected_artifacts((artifact,), (event,)), (artifact,))


if __name__ == "__main__":
    unittest.main()
