import hashlib
import io
import json
import sqlite3
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.contracts import AgentProposal
from dv_platform.analysis.plan_store import write_plan_outputs
from dv_platform.analysis.revisions import create_feedback_revision, read_revision_plan
from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.cli import main
from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ArtifactKind,
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    RTLPort,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators import write_generated_artifacts


def _tree_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _report(module: str, content: str) -> GeneratedArtifact:
    return GeneratedArtifact(
        Path("report.txt"),
        ArtifactKind.REPORT,
        VerificationTarget.SYSTEMVERILOG,
        content,
        module,
        provenance_refs=(EvidenceRef(EvidenceKind.VERILATOR_AST, f"V{module}.xml", f"module:{module}"),),
    )


def _module_and_plan(name: str):
    evidence = EvidenceRef(EvidenceKind.VERILATOR_AST, f"V{name}.xml", f"module:{name}")
    plan = VerificationPlan(
        name,
        (VerificationTarget.COCOTB,),
        ports=(RTLPort("clock", "input", width=1), RTLPort("data_o", "output", width=1)),
        claims=(
            VerificationClaim(
                f"{name}:module",
                name,
                "Module ports are present.",
                status=ClaimStatus.SUPPORTED,
                evidence_refs=(evidence,),
            ),
        ),
    )
    return name, plan


class TargetedGenerationFreshnessTests(unittest.TestCase):
    def test_targeted_writer_preserves_unaffected_module_byte_for_byte(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            write_generated_artifacts(config, (_report("first", "first-v1\n"), _report("second", "second-v1\n")))
            modules = config.output_dir / "simulation" / "systemverilog" / "modules"
            first = modules / "first"
            second = modules / "second"
            second_before = _tree_hash(second)

            write_generated_artifacts(config, (_report("first", "first-v2\n"),), replace_target=None)

            self.assertEqual((first / "report.txt").read_text(encoding="utf-8"), "first-v2\n")
            self.assertEqual(_tree_hash(second), second_before)

    def test_revision_generation_preserves_other_module_and_invalidates_old_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            _first_module, first_plan = _module_and_plan("first")
            _second_module, second_plan = _module_and_plan("second")
            write_plan_outputs(config, (first_plan, second_plan))
            initial_output = io.StringIO()
            with redirect_stdout(initial_output):
                initial_exit = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])
            self.assertEqual(initial_exit, 0, initial_output.getvalue())

            modules = config.output_dir / "simulation" / "cocotb" / "modules"
            second_hash = _tree_hash(modules / "second")
            old_first_provenance_hash = hashlib.sha256((modules / "first" / "provenance.json").read_bytes()).hexdigest()
            evidence = EvidenceRef(EvidenceKind.TOOL_LOG, "failed-run", "run:first")
            proposal = AgentProposal(
                "add-error-check",
                "feedback:first",
                "add_check",
                "Exercise the error response.",
                (evidence,),
                {
                    "operation": "add_check",
                    "check_id": "first:check:error",
                    "statement": "Exercise the error response.",
                    "category": "protocol",
                },
            )
            revision = create_feedback_revision(
                config.work_dir,
                first_plan,
                (),
                proposals=(proposal,),
                evidence_ids={"failed-run"},
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo),
                        "--json",
                        "generate",
                        "--target",
                        "cocotb",
                        "--revision",
                        revision.revision_id,
                    ]
                )

            self.assertEqual(exit_code, 0, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["data"]["revision"], revision.revision_id)
            self.assertEqual(_tree_hash(modules / "second"), second_hash)
            snapshot = read_revision_plan(config.work_dir, revision.revision_id)
            assert snapshot is not None
            self.assertIn("first:check:error", {check.check_id for check in snapshot.check_details})

            run_summary = config.work_dir / "runs" / "simulation" / "cocotb" / "first" / "summary.json"
            run_summary.parent.mkdir(parents=True)
            run_summary.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "first",
                        "status": "passed",
                        "return_code": 0,
                        "provenance_sha256": old_first_provenance_hash,
                        "verification_coverage": {"complete": True},
                    }
                ),
                encoding="utf-8",
            )
            status = collect_platform_status(config)
            self.assertIn(
                {"target": "cocotb", "module": "first"},
                status["runs"]["expected_missing"],
            )
            self.assertIn(
                "expected_runs_missing",
                {failure["code"] for failure in evaluate_status_policy(status, require_tools=False)},
            )

    def test_tampered_and_snapshotless_revisions_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            _module, plan = _module_and_plan("top")
            write_plan_outputs(config, (plan,))
            evidence = EvidenceRef(EvidenceKind.TOOL_LOG, "event", "run:one")
            proposal = AgentProposal(
                "p",
                "task",
                "add_check",
                "Add check.",
                (evidence,),
                {"operation": "add_check", "check_id": "top:check:new"},
            )
            revision = create_feedback_revision(
                config.work_dir, plan, (), proposals=(proposal,), evidence_ids={"event"}
            )
            database = config.work_dir / "plans" / "revisions.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "update plan_revisions set snapshot_json = ? where revision_id = ?",
                    (json.dumps({"schema_version": 16, "module": "different"}), revision.revision_id),
                )
                connection.commit()

            output = io.StringIO()
            with redirect_stdout(output):
                stale = main(
                    [
                        "--repo-root",
                        str(repo),
                        "--json",
                        "generate",
                        "--target",
                        "cocotb",
                        "--revision",
                        revision.revision_id,
                    ]
                )
            self.assertEqual(stale, 2)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "stale_revision")

            with sqlite3.connect(database) as connection:
                connection.execute(
                    "update plan_revisions set snapshot_json = null where revision_id = ?", (revision.revision_id,)
                )
                connection.commit()
            output = io.StringIO()
            with redirect_stdout(output):
                missing = main(
                    [
                        "--repo-root",
                        str(repo),
                        "--json",
                        "generate",
                        "--target",
                        "cocotb",
                        "--revision",
                        revision.revision_id,
                    ]
                )
            self.assertEqual(missing, 2)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "stale_revision")


if __name__ == "__main__":
    unittest.main()
