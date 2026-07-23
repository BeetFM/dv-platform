import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.contracts import FeedbackEvent
from dv_platform.analysis.dependencies import build_dependency_graph
from dv_platform.cli import _known_affected_artifact_paths
from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ArtifactKind,
    ArtifactTrace,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    VerificationCheck,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.generators.artifacts import select_affected_artifacts, write_generated_artifacts


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

    def test_dependency_graph_reaches_scenario_symbol_artifact_run_and_coverage(self) -> None:
        ref = EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "checks")
        check = VerificationCheck("check-1", "Check one.", executable=True, coverage_point_ids=("point-1",))
        scenario = VerificationScenario(
            "scenario-1",
            "typed",
            (ScenarioStimulus("drive", "sig", "1"),),
            ScenarioOracle("equals", "sig", "1"),
            ScenarioCompletion("cycles", timeout_cycles=2),
            (ScenarioCoverageGoal("goal-1", "functional"),),
            (VerificationTarget.COCOTB,),
            check_ids=(check.check_id,),
            evidence_refs=(ref,),
            executable=True,
        )
        plan = VerificationPlan("top", (VerificationTarget.COCOTB,), check_details=(check,), scenarios=(scenario,))
        artifact = GeneratedArtifact(
            Path("test.py"),
            ArtifactKind.TESTBENCH,
            VerificationTarget.COCOTB,
            "# test\n",
            "top",
            provenance_refs=(ref,),
            traceability=(ArtifactTrace("trace", "test_one", check_ids=(check.check_id,), evidence_refs=(ref,)),),
        )

        affected = build_dependency_graph(plan, (artifact,)).affected(("check:check-1",))

        self.assertEqual(affected.scenario_ids, ("scenario-1",))
        self.assertEqual(affected.generated_symbols, ("cocotb/top/test_one",))
        self.assertEqual(affected.artifact_paths, ("cocotb/top/test.py",))
        self.assertEqual(affected.run_targets, ("cocotb/top",))
        self.assertEqual(affected.coverage_point_ids, ("cocotb/top", "goal-1", "point-1"))

    def test_revision_writer_preserves_unaffected_files_with_fresh_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            config = default_config(Path(directory))
            ref = EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "generation")

            def report(path: str, content: str) -> GeneratedArtifact:
                return GeneratedArtifact(
                    Path(path),
                    ArtifactKind.REPORT,
                    VerificationTarget.SYSTEMVERILOG,
                    content,
                    "top",
                    provenance_refs=(ref,),
                )

            write_generated_artifacts(config, (report("first.txt", "first-v1\n"), report("second.txt", "second-v1\n")))
            write_generated_artifacts(
                config,
                (report("first.txt", "first-v2\n"), report("second.txt", "second-v2\n")),
                affected_paths={(VerificationTarget.SYSTEMVERILOG, "top"): {"first.txt"}},
            )
            directory_path = config.output_dir / "simulation" / "systemverilog" / "modules" / "top"
            self.assertEqual((directory_path / "first.txt").read_text(encoding="utf-8"), "first-v2\n")
            self.assertEqual((directory_path / "second.txt").read_text(encoding="utf-8"), "second-v1\n")
            provenance = json.loads((directory_path / "provenance.json").read_text(encoding="utf-8"))
            second = next(item for item in provenance["artifacts"] if item["path"] == "second.txt")
            self.assertEqual(second["size_bytes"], len("second-v1\n"))

    def test_known_artifact_dependencies_are_resolved_from_existing_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            config = default_config(Path(directory))
            scenario = VerificationScenario(
                "scenario-1",
                "typed",
                (ScenarioStimulus("drive"),),
                ScenarioOracle("equals"),
                ScenarioCompletion("cycles"),
                (),
                (VerificationTarget.COCOTB,),
                requirement_ids=("requirement-1",),
                check_ids=("check-1",),
            )
            plan = VerificationPlan(
                "top",
                (VerificationTarget.COCOTB, VerificationTarget.FORMAL, VerificationTarget.SYSTEMVERILOG),
                scenarios=(scenario,),
            )
            cocotb = config.output_dir / "simulation" / "cocotb" / "modules" / "top"
            cocotb.mkdir(parents=True)
            (cocotb / "provenance.json").write_text(
                json.dumps(
                    {
                        "artifacts": [
                            "bad",
                            {"path": 7},
                            {"path": "no-traces.py", "traceability": "bad"},
                            {
                                "path": "test_top.py",
                                "traceability": [
                                    "bad",
                                    {"check_ids": ["check-1"], "requirement_ids": []},
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            formal = config.output_dir / "formal" / "modules" / "top"
            formal.mkdir(parents=True)
            (formal / "provenance.json").write_text("not-json", encoding="utf-8")
            event = FeedbackEvent(
                "event",
                "run",
                VerificationTarget.COCOTB,
                "top",
                "fail",
                affected_artifacts=("explicit.py",),
            )

            paths = _known_affected_artifact_paths(config, plan, (event,), ("scenario-1",))

            self.assertEqual(paths, ("explicit.py", "test_top.py"))

            (cocotb / "provenance.json").write_text("[]", encoding="utf-8")
            self.assertEqual(_known_affected_artifact_paths(config, plan, (), ()), ())


if __name__ == "__main__":
    unittest.main()
