import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.review import (
    generate_design_decisions,
    generate_run_feedback_decisions,
    read_review_records,
    write_review_outputs,
)
from dv_platform.core.config import default_config
from dv_platform.core.models import EvidenceKind, EvidenceRef, RTLModule, RTLPort, Severity


class ReviewTests(unittest.TestCase):
    def test_generate_design_decisions_reports_missing_output_drive_evidence(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vstub.xml", "port:stub.done_o")
        module = RTLModule(
            name="stub",
            ports=("done_o",),
            port_details=(RTLPort(name="done_o", direction="output"),),
            ast_refs=(ref,),
        )

        decisions = generate_design_decisions((module,))

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].title, "Output ports have no extracted drive evidence")
        self.assertEqual(decisions[0].severity, Severity.HIGH)
        self.assertEqual(decisions[0].evidence_refs, (ref,))

    def test_write_review_outputs_persists_sqlite_json_and_markdown(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vstub.xml", "port:stub.done_o")
            module = RTLModule(
                name="stub",
                ports=("done_o",),
                port_details=(RTLPort(name="done_o", direction="output"),),
                ast_refs=(ref,),
            )
            decisions = generate_design_decisions((module,))

            sqlite_path, json_path, markdown_path = write_review_outputs(config, decisions)

            self.assertEqual(sqlite_path, repo / ".dv-platform" / "review" / "review.sqlite")
            self.assertEqual(json_path, repo / ".dv-platform" / "review" / "review.json")
            self.assertEqual(markdown_path, repo / ".dv-platform" / "review" / "review.md")
            self.assertIn("# Design Review", markdown_path.read_text(encoding="utf-8"))
            records = read_review_records(sqlite_path)
            self.assertEqual(records[0]["scope"], "stub")
            self.assertEqual(records[0]["severity"], "high")

    def test_generate_run_feedback_decisions_reports_failed_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            provenance_path = (
                repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "counter" / "provenance.json"
            )
            provenance_path.parent.mkdir(parents=True)
            provenance_path.write_text("{}\n", encoding="utf-8")
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "counter" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "counter",
                        "status": "failed",
                        "return_code": 1,
                        "results_error": "counter did not increment",
                        "provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            decisions = generate_run_feedback_decisions(config)

            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0].scope, "counter")
            self.assertEqual(decisions[0].title, "cocotb run failed")
            self.assertEqual(decisions[0].severity, Severity.HIGH)
            self.assertEqual(decisions[0].evidence_refs[0].kind, EvidenceKind.TOOL_LOG)
            self.assertEqual(decisions[0].evidence_refs[0].source_id, str(summary_path))


if __name__ == "__main__":
    unittest.main()
