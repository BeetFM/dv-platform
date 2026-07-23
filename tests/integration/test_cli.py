import hashlib
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.docs import LoadedDocument, chunk_document, write_document_index
from dv_platform.analysis.plan_store import read_plan_records, write_plan_outputs
from dv_platform.analysis.rtl import normalize_verilator_xml, write_normalized_rtl_facts
from dv_platform.cli import build_parser, config_from_args, main
from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, default_config, load_config, validate_config, write_config
from dv_platform.core.models import (
    AdapterPluginConfig,
    ClaimStatus,
    CoveragePolicy,
    EvidenceKind,
    EvidenceRef,
    FormalToolConfig,
    ProtocolProfile,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from tests.support.paths import FIXTURES_ROOT


class CLITests(unittest.TestCase):
    def test_config_rejects_unsafe_or_duplicate_parameter_overrides(self) -> None:
        config = replace(
            default_config(Path.cwd()),
            top_modules=("top",),
            parameter_overrides=("WIDTH=12", "WIDTH=8", "DEPTH=2;bad", "MASK=4'bface"),
        )

        diagnostics = validate_config(config)

        self.assertTrue(any("DEPTH=2;bad" in item.message for item in diagnostics))
        self.assertTrue(any("MASK=4'bface" in item.message for item in diagnostics))
        self.assertTrue(any("Duplicate parameter override" in item.message for item in diagnostics))

    def test_config_rejects_duplicate_parameter_sweeps(self) -> None:
        config = replace(
            default_config(Path.cwd()),
            top_modules=("top",),
            parameter_sweeps=(("WIDTH=8",), ("WIDTH=8",)),
        )

        diagnostics = validate_config(config)

        self.assertTrue(any("Duplicate parameter sweep" in item.message for item in diagnostics))

    def test_config_defaults_to_local_only_workflow(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo-root", "repo", "--work-dir", "work", "plan"])

        config = config_from_args(args)

        expected_root = Path("repo").resolve(strict=False)
        self.assertEqual(config.repo_root, expected_root)
        self.assertEqual(config.work_dir, expected_root / "work")
        self.assertEqual(config.retrieval_index_dir, expected_root / "work" / "rag-index")
        self.assertFalse(config.allow_network)
        self.assertFalse(config.strict)
        self.assertFalse(config.ci)

    def test_review_reports_missing_rtl_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo),
                        "--work-dir",
                        "work",
                        "--output-dir",
                        "out",
                        "review",
                    ]
                )

            self.assertEqual(exit_code, 2)
            text = output.getvalue()
            self.assertIn("run analyze-rtl first", text)

    def test_review_loads_rtl_facts_and_writes_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "review"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=review", text)
            self.assertIn("modules=1", text)
            self.assertIn("review_db=", text)
            self.assertTrue((repo / ".dv-platform" / "review" / "review.sqlite").is_file())
            self.assertTrue((repo / ".dv-platform" / "review" / "review.json").is_file())
            self.assertTrue((repo / ".dv-platform" / "review" / "review.md").is_file())

    def test_review_json_outputs_stable_envelope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "review"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "review")
            self.assertEqual(payload["data"]["modules"], 1)
            self.assertIn("review_json", payload["data"])

    def test_status_reports_schemas_generated_quality_and_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            _write_project_manifest(config, repo / "rtl" / "simple_counter.sv")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "cocotb"])
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "generate", "--target", "cocotb"])
            provenance_path = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "cocotb"
                / "modules"
                / "simple_counter"
                / "provenance.json"
            )
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "simple_counter" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "simple_counter",
                        "status": "failed",
                        "return_code": 1,
                        "provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "status"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=status", text)
            self.assertIn("rtl_facts_schema=current", text)
            self.assertIn("rtl_facts_modules=1", text)
            self.assertIn("plan_schema=current", text)
            self.assertIn("generated_modules=1", text)
            self.assertIn("quality_missing=0", text)
            self.assertIn("quality_failed=0", text)
            self.assertIn("artifacts_missing=0", text)
            self.assertIn("provenance_invalid=0", text)
            self.assertIn("integrity_missing=0", text)
            self.assertIn("integrity_failed=0", text)
            self.assertIn("tool_validation_missing=0", text)
            self.assertIn("tool_validation_failed=0", text)
            self.assertIn("traceability_missing=0", text)
            self.assertIn("execution_manifest_invalid=0", text)
            self.assertIn("expected_generated_missing=0", text)
            self.assertIn("unexpected_generated=0", text)
            self.assertIn("unsafe_generated_roots=0", text)
            self.assertIn("run_summaries=1", text)
            self.assertIn("failed_runs=1", text)
            self.assertIn("expected_runs_missing=0", text)
            self.assertIn("coverage_status=missing", text)

    def test_status_json_reports_missing_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "status")
            self.assertEqual(payload["data"]["schemas"]["rtl_facts"]["status"], "missing")
            self.assertEqual(payload["data"]["schemas"]["plans"]["status"], "missing")
            self.assertEqual(payload["data"]["summary"]["generated_modules"], 0)

    def test_status_ci_policy_fails_when_pipeline_state_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            failure_codes = {failure["code"] for failure in payload["data"]["policy"]["failures"]}
            self.assertIn("rtl_facts_schema_missing", failure_codes)
            self.assertIn("plans_schema_missing", failure_codes)
            self.assertIn("rtl_facts_empty", failure_codes)
            self.assertIn("plans_empty", failure_codes)

    def test_status_ci_policy_fails_on_failed_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            provenance_path = _prepare_generated_cocotb_state(repo)
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "simple_counter" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "simple_counter",
                        "status": "failed",
                        "return_code": 1,
                        "provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            text = output.getvalue()
            self.assertIn("error=Status CI policy failed.", text)
            self.assertIn("policy_failure=runs_failed", text)

    def test_status_ci_policy_rejects_run_from_previous_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            _prepare_generated_cocotb_state(repo)
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "simple_counter" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "simple_counter",
                        "status": "passed",
                        "return_code": 0,
                        "provenance_sha256": "0" * 64,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            failure_codes = {failure["code"] for failure in payload["data"]["policy"]["failures"]}
            self.assertIn("expected_runs_missing", failure_codes)

    def test_status_ci_policy_fails_on_missing_generated_quality_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            (generated_dir / "provenance.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "module": "fifo",
                        "target": "cocotb",
                        "artifacts": [
                            {
                                "path": "test_fifo.py",
                                "kind": "testbench",
                                "source_plan_module": "fifo",
                                "provenance_refs": [
                                    {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": "module:fifo"}
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "status_policy_failed")
            failure_codes = tuple(failure["code"] for failure in payload["data"]["policy"]["failures"])
            self.assertIn("generated_quality_missing", failure_codes)
            self.assertIn("generated_artifacts_missing", failure_codes)

    def test_status_ci_policy_fails_on_invalid_unplanned_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "systemverilog" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            (generated_dir / "provenance.json").write_text("{}\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            failure_codes = {failure["code"] for failure in payload["data"]["policy"]["failures"]}
            self.assertIn("generated_provenance_invalid", failure_codes)
            self.assertIn("unexpected_generated_modules", failure_codes)

    def test_status_ci_policy_rejects_generated_root_symlink_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            repo = base / "repo"
            repo.mkdir()
            outside = base / "outside"
            outside.mkdir()
            modules_dir = repo / "generated" / "dv-platform" / "simulation" / "systemverilog"
            modules_dir.mkdir(parents=True)
            (modules_dir / "modules").symlink_to(outside, target_is_directory=True)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "status", "--policy", "ci", "--no-require-tools"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            failure_codes = {failure["code"] for failure in payload["data"]["policy"]["failures"]}
            self.assertIn("unsafe_generated_roots", failure_codes)

    def test_review_includes_failed_run_feedback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            provenance_path = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "cocotb"
                / "modules"
                / "simple_counter"
                / "provenance.json"
            )
            provenance_path.parent.mkdir(parents=True)
            provenance_path.write_text("{}\n", encoding="utf-8")
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "simple_counter" / "summary.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "target": "cocotb",
                        "module": "simple_counter",
                        "status": "failed",
                        "return_code": 1,
                        "results_error": "count_o did not increment",
                        "provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                exit_code = main(["--repo-root", str(repo), "review"])

            self.assertEqual(exit_code, 0)
            review = json.loads((repo / ".dv-platform" / "review" / "review.json").read_text(encoding="utf-8"))
            titles = tuple(finding["title"] for finding in review["findings"])
            self.assertIn("cocotb run failed", titles)

    def test_init_writes_loadable_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME

            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--documentation-path",
                        "specs",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--include-path",
                        "rtl/include",
                        "--define",
                        "SYNTHESIS=0",
                        "--parameter",
                        "WIDTH=12",
                        "--top-module",
                        "top",
                    ]
                )

            self.assertEqual(exit_code, 0)
            config = load_config(config_path)
            self.assertEqual(config.documentation_paths, (repo / "specs",))
            self.assertEqual(config.rtl_filelists, (repo / "rtl" / "files.f",))
            self.assertEqual(config.include_paths, (repo / "rtl" / "include",))
            self.assertEqual(config.defines, ("SYNTHESIS=0",))
            self.assertEqual(config.parameter_overrides, ("WIDTH=12",))
            self.assertEqual(config.top_modules, ("top",))
            self.assertFalse(config.strict)
            self.assertFalse(config.ci)

    def test_init_writes_loadable_parameter_sweeps(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--parameter-sweep",
                        "WIDTH=8,DEPTH=2",
                        "--parameter-sweep",
                        "WIDTH=16,DEPTH=4",
                        "--top-module",
                        "top",
                    ]
                )

            self.assertEqual(exit_code, 0)
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            self.assertEqual(
                config.parameter_sweeps,
                (("WIDTH=8", "DEPTH=2"), ("WIDTH=16", "DEPTH=4")),
            )

    def test_init_json_outputs_created_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "init"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "init")
            self.assertEqual(payload["data"]["created_config"], str(repo / DEFAULT_CONFIG_FILENAME))

    def test_analyze_rtl_dry_run_discovers_sources_and_writes_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl" / "include").mkdir(parents=True)
            (repo / "docs").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            (repo / "docs" / "top.md").write_text("# Top\n", encoding="utf-8")
            (repo / "rtl" / "files.f").write_text(
                "+incdir+include\n+define+SIM=1\ntop.sv\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--documentation-path",
                        "docs",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                    ]
                )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl", "--dry-run"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            manifest_path = repo / ".dv-platform" / "project-manifest.json"
            self.assertIn("hdl_files=1", text)
            self.assertIn("documentation_files=1", text)
            self.assertIn(f"manifest={manifest_path}", text)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["hdl_files"][0]["path"], str(repo / "rtl" / "top.sv"))
            self.assertEqual(manifest["hdl_files"][0]["language"], "systemverilog")
            self.assertEqual(manifest["documentation_files"], [str(repo / "docs" / "top.md")])
            self.assertEqual(manifest["include_paths"], [str(repo / "rtl" / "include")])
            self.assertEqual(manifest["defines"], ["SIM=1"])
            self.assertIn("--top-module", manifest["verilator_command"])
            self.assertEqual(manifest["diagnostics"], [])

    def test_analyze_rtl_json_dry_run_outputs_manifest_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "analyze-rtl", "--dry-run"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "analyze-rtl")
            self.assertTrue(payload["data"]["dry_run"])
            self.assertEqual(payload["data"]["hdl_files"], 1)
            self.assertIn("verilator_command", payload["data"])

    def test_index_docs_loads_chunks_and_writes_local_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "counter.md").write_text(
                "# Counter\n\nThe simple_counter increments count_o when enable_i is asserted.\n",
                encoding="utf-8",
            )
            (repo / "docs" / "reset.rst").write_text(
                "Reset\n=====\n\nrst_n clears count_o.\n",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init", "--documentation-path", "docs"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "index-docs", "--chunk-size", "64"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            index_path = repo / ".dv-platform" / "rag-index" / "chunks.json"
            self.assertIn("command=index-docs", text)
            self.assertIn("documentation_files=2", text)
            self.assertIn(f"index={index_path}", text)

            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["schema_version"], 2)
            self.assertGreaterEqual(len(index["chunks"]), 2)

    def test_index_docs_json_outputs_index_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "counter.md").write_text("counter behavior\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init", "--documentation-path", "docs"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "index-docs"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "index-docs")
            self.assertEqual(payload["data"]["documentation_files"], 1)
            self.assertEqual(payload["data"]["index"], str(repo / ".dv-platform" / "rag-index" / "chunks.json"))

    def test_index_docs_reports_invalid_chunk_size(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "counter.md").write_text("counter\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "index-docs", "--chunk-size", "0"])

            self.assertEqual(exit_code, 2)
            self.assertIn("error=max_chars must be positive", output.getvalue())

    def test_plan_loads_rtl_facts_docs_and_writes_plan_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            chunks = chunk_document(
                LoadedDocument(
                    source=repo / "docs" / "counter.md",
                    text="The simple_counter increments count_o when enable_i is asserted.",
                )
            )
            write_document_index(config, chunks)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "plan", "--target", "cocotb", "--target", "formal"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=plan", text)
            self.assertIn("modules=1", text)
            self.assertIn("documentation_chunks=1", text)
            self.assertIn("claim_report_files=2", text)
            self.assertTrue((repo / ".dv-platform" / "plans" / "plans.sqlite").is_file())
            self.assertTrue((repo / ".dv-platform" / "plans" / "modules" / "simple_counter.plan.md").is_file())
            self.assertTrue((repo / ".dv-platform" / "plans" / "claims" / "simple_counter" / "claims.json").is_file())

    def test_plan_reports_missing_rtl_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "plan"])

            self.assertEqual(exit_code, 2)
            self.assertIn("run analyze-rtl first", output.getvalue())

    def test_plan_json_reports_missing_rtl_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "plan"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["command"], "plan")
            self.assertEqual(payload["error"]["code"], "missing_rtl_facts")

    def test_index_docs_and_plan_workflow_uses_fixture_inputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "counter.md").write_text(
                "The simple_counter increments count_o when enable_i is asserted.\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init", "--documentation-path", "docs"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")

            with redirect_stdout(io.StringIO()):
                index_exit = main(["--repo-root", str(repo), "index-docs"])
            with redirect_stdout(io.StringIO()):
                plan_exit = main(["--repo-root", str(repo), "plan"])

            self.assertEqual(index_exit, 0)
            self.assertEqual(plan_exit, 0)
            records = read_plan_records(repo / ".dv-platform" / "plans" / "plans.sqlite")
            self.assertEqual(records[0]["module"], "simple_counter")
            self.assertIn("simple_counter increments count_o", records[0]["plan"]["requirements"][0])
            self.assertTrue(records[0]["gate"]["allowed"])
            self.assertEqual(records[0]["gate"]["blocked"], [])

    def test_generate_cocotb_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "cocotb"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=generate", text)
            self.assertIn("artifacts=2", text)
            generated_test = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "cocotb"
                / "modules"
                / "simple_counter"
                / "test_simple_counter.py"
            )
            self.assertTrue(generated_test.is_file())
            self.assertIn("@cocotb.test()", generated_test.read_text(encoding="utf-8"))
            self.assertTrue((generated_test.parent / "provenance.json").is_file())

    def test_generate_json_outputs_stable_envelope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "cocotb"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "generate", "--target", "cocotb"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "generate")
            self.assertEqual(payload["data"]["target"], "cocotb")
            self.assertEqual(payload["data"]["artifacts"], 2)
            self.assertEqual(len(payload["data"]["artifact_paths"]), 2)

    def test_generate_formal_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "formal"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "formal"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=generate", text)
            self.assertIn("artifacts=3", text)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "simple_counter"
            harness = generated_dir / "formal_simple_counter.sv"
            sby = generated_dir / "simple_counter.sby"
            self.assertTrue(harness.is_file())
            self.assertTrue(sby.is_file())
            self.assertIn("module formal_simple_counter;", harness.read_text(encoding="utf-8"))
            self.assertIn("prep -top formal_simple_counter", sby.read_text(encoding="utf-8"))
            self.assertTrue((generated_dir / "provenance.json").is_file())

    def test_generate_systemverilog_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "systemverilog"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "systemverilog"])

            self.assertEqual(exit_code, 0)
            self.assertIn("artifacts=2", output.getvalue())
            generated_tb = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "systemverilog"
                / "modules"
                / "simple_counter"
                / "tb_simple_counter.sv"
            )
            self.assertTrue(generated_tb.is_file())
            self.assertIn("module tb_simple_counter;", generated_tb.read_text(encoding="utf-8"))
            self.assertTrue((generated_tb.parent / "provenance.json").is_file())

    def test_generate_verilog_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "verilog"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "verilog"])

            self.assertEqual(exit_code, 0)
            self.assertIn("artifacts=2", output.getvalue())
            generated_tb = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "verilog"
                / "modules"
                / "simple_counter"
                / "tb_simple_counter.v"
            )
            self.assertTrue(generated_tb.is_file())
            self.assertIn("module tb_simple_counter;", generated_tb.read_text(encoding="utf-8"))
            self.assertTrue((generated_tb.parent / "provenance.json").is_file())

    def test_generate_vhdl_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "vhdl"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "vhdl"])

            self.assertEqual(exit_code, 0)
            self.assertIn("artifacts=2", output.getvalue())
            generated_tb = (
                repo
                / "generated"
                / "dv-platform"
                / "simulation"
                / "vhdl"
                / "modules"
                / "simple_counter"
                / "tb_simple_counter.vhd"
            )
            self.assertTrue(generated_tb.is_file())
            self.assertIn("entity tb_simple_counter is", generated_tb.read_text(encoding="utf-8"))
            self.assertTrue((generated_tb.parent / "provenance.json").is_file())

    def test_generate_uvm_loads_plans_and_writes_scaffold_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "uvm"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "uvm"])

            self.assertEqual(exit_code, 0)
            self.assertIn("artifacts=5", output.getvalue())
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "uvm" / "modules" / "simple_counter"
            self.assertTrue((generated_dir / "simple_counter_pkg.sv").is_file())
            self.assertTrue((generated_dir / "simple_counter_if.sv").is_file())
            self.assertTrue((generated_dir / "tb_simple_counter_uvm.sv").is_file())
            self.assertIn(
                "Advanced UVM generation is blocked", (generated_dir / "README.md").read_text(encoding="utf-8")
            )
            self.assertTrue((generated_dir / "provenance.json").is_file())

    def test_index_plan_generate_workflow_uses_fixture_inputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "docs").mkdir()
            (repo / "docs" / "counter.md").write_text(
                "The simple_counter increments count_o when enable_i is asserted.\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init", "--documentation-path", "docs"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
            write_normalized_rtl_facts(config, modules, "Verilator test")

            with redirect_stdout(io.StringIO()):
                index_exit = main(["--repo-root", str(repo), "index-docs"])
            with redirect_stdout(io.StringIO()):
                plan_exit = main(["--repo-root", str(repo), "plan", "--target", "cocotb"])
            with redirect_stdout(io.StringIO()):
                generate_exit = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])

            self.assertEqual(index_exit, 0)
            self.assertEqual(plan_exit, 0)
            self.assertEqual(generate_exit, 0)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "simple_counter"
            generated_test = generated_dir / "test_simple_counter.py"
            provenance_path = generated_dir / "provenance.json"
            self.assertIn("simple_counter increments count_o", generated_test.read_text(encoding="utf-8"))

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["module"], "simple_counter")
            self.assertEqual(provenance["target"], "cocotb")
            self.assertGreaterEqual(len(provenance["artifacts"][0]["provenance_refs"]), 1)

    def test_generate_reports_missing_plans(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])

            self.assertEqual(exit_code, 2)
            self.assertIn("run plan first", output.getvalue())

    def test_generate_reports_artifact_quality_gate_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            plan = VerificationPlan(
                module="fifo",
                targets=(VerificationTarget.COCOTB,),
                claims=(
                    VerificationClaim(
                        "fifo:module", "fifo", "module exists", status=ClaimStatus.SUPPORTED, evidence_refs=(ref,)
                    ),
                ),
                checks=("Generate basic input/output connectivity checks.",),
            )
            write_plan_outputs(config, (plan,))

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])

            self.assertEqual(exit_code, 2)
            self.assertIn("error=Generated executable artifact failed quality gate", output.getvalue())
            self.assertIn("structured_ports", output.getvalue())

    def test_analyze_rtl_warns_when_filelists_are_missing_in_exploratory_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl", "--dry-run"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("warning=No RTL file lists configured", text)
            self.assertIn("hdl_files=1", text)

            manifest = json.loads((repo / ".dv-platform" / "project-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["diagnostics"][0]["severity"], "warning")

    def test_analyze_rtl_errors_when_filelists_are_missing_in_strict_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--strict", "analyze-rtl", "--dry-run"])

            self.assertEqual(exit_code, 2)
            self.assertIn("error=No RTL file lists configured", output.getvalue())
            self.assertFalse((repo / ".dv-platform" / "project-manifest.json").exists())

    def test_ci_flag_is_persisted_and_implies_strict(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            with redirect_stdout(io.StringIO()):
                exit_code = main(["--repo-root", str(repo), "--ci", "init"])

            self.assertEqual(exit_code, 0)
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            self.assertTrue(config.strict)
            self.assertTrue(config.ci)

    def test_config_loads_simulator_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config_path.write_text(
                """
[paths]
repo_root = "."

[[simulators]]
target = "cocotb"
name = "icarus"
command = "iverilog"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual(len(config.simulators), 1)
            self.assertEqual(config.simulators[0].target, VerificationTarget.COCOTB)
            self.assertEqual(config.simulators[0].name, "icarus")
            self.assertEqual(config.simulators[0].command, "iverilog")

    def test_config_loads_formal_tool_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config_path.write_text(
                """
[paths]
repo_root = "."

[[formal_tools]]
name = "symbiyosys"
command = "sby"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual(config.formal_tools, (FormalToolConfig(name="symbiyosys", command="sby"),))

    def test_write_config_preserves_formal_tool_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config = replace(default_config(repo), formal_tools=(FormalToolConfig(name="symbiyosys", command="sby"),))

            write_config(config, config_path)
            loaded = load_config(config_path)

            self.assertEqual(loaded.formal_tools, (FormalToolConfig(name="symbiyosys", command="sby"),))
            self.assertIn("[[formal_tools]]", config_path.read_text(encoding="utf-8"))

    def test_config_loads_and_writes_generator_plugins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config_path.write_text(
                """
[paths]
repo_root = "."

[plugins]
generator_backends = ["company_uvm"]
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)
            self.assertEqual(config.generator_plugins, ("company_uvm",))

            write_config(config, config_path)
            text = config_path.read_text(encoding="utf-8")
            self.assertIn("[plugins]", text)
            self.assertIn('generator_backends = "company_uvm"', text.replace("[", "").replace("]", ""))

    def test_config_round_trips_p1_protocol_coverage_security_execution_and_plugins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config = replace(
                default_config(repo),
                protocol_profiles=(ProtocolProfile("command", "req_ack", "_req", "_ack", ("_payload",)),),
                adapter_plugins=(AdapterPluginConfig("report_exporter", "company_report", 1),),
                coverage_policy=CoveragePolicy(80.0, 70.0, 60.0, 50.0),
                audit_enabled=True,
                redact_patterns=(r"token=[^ ]+",),
                max_parallel_modules=4,
            )

            write_config(config, config_path)
            loaded = load_config(config_path)

            self.assertEqual(loaded.protocol_profiles, config.protocol_profiles)
            self.assertEqual(loaded.adapter_plugins, config.adapter_plugins)
            self.assertEqual(loaded.coverage_policy, config.coverage_policy)
            self.assertEqual(loaded.redact_patterns, config.redact_patterns)
            self.assertEqual(loaded.max_parallel_modules, 4)
            self.assertFalse([item for item in validate_config(loaded) if item.severity == "error"])

    def test_coverage_command_imports_report_and_returns_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            write_config(
                replace(default_config(repo), coverage_policy=CoveragePolicy(line_minimum=80.0)),
                repo / DEFAULT_CONFIG_FILENAME,
            )
            report = repo / "coverage.info"
            report.write_text("SF:rtl/top.sv\nLF:10\nLH:9\nend_of_record\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "coverage", "--input", str(report)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["metrics"]["line"]["percentage"], 90.0)

    def test_coverage_command_returns_one_for_failed_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            write_config(
                replace(default_config(repo), coverage_policy=CoveragePolicy(line_minimum=95.0)),
                repo / DEFAULT_CONFIG_FILENAME,
            )
            report = repo / "coverage.json"
            report.write_text(json.dumps({"metrics": {"line": 90.0}}), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "coverage", "--input", str(report)])

            self.assertEqual(exit_code, 1)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "coverage_gate_failed")

    def test_generate_formal_requires_formal_tool_in_strict_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--strict", "generate", "--target", "formal"])

            self.assertEqual(exit_code, 2)
            self.assertIn("No formal tools configured", output.getvalue())

    def test_run_formal_requires_formal_tool_in_strict_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["--repo-root", str(repo), "--strict", "run", "--target", "formal", "--module", "fifo"]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("No formal tools configured", output.getvalue())

    def test_run_json_reports_missing_simulator(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "--json", "run", "--target", "cocotb", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["command"], "run")
            self.assertEqual(payload["error"]["code"], "missing_simulator")

    def test_run_formal_reports_configured_tool_and_missing_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                """
[paths]
repo_root = "."

[[formal_tools]]
name = "symbiyosys"
command = "sby"
""".strip(),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "formal", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("formal_tool=symbiyosys", output.getvalue())
            self.assertIn("summary=", output.getvalue())
            summary_path = repo / ".dv-platform" / "runs" / "formal" / "fifo" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing_artifacts")

    def test_run_formal_executes_configured_tool(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            tool_script = repo / "fake_sby.py"
            tool_script.write_text(
                "from pathlib import Path\nimport sys\nprint('formal cli ok')\nprint(Path(sys.argv[-1]).name)\nprint('DONE (PASS, rc=0)')\n",
                encoding="utf-8",
            )
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                f"""
[paths]
repo_root = "."

[[formal_tools]]
name = "symbiyosys"
command = "{sys.executable} {tool_script}"
""".strip(),
                encoding="utf-8",
            )
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            _write_project_manifest(load_config(repo / DEFAULT_CONFIG_FILENAME), repo / "rtl" / "fifo.sv")
            _write_valid_formal_artifacts(generated_dir, "fifo")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "formal", "--module", "fifo"])

            self.assertEqual(exit_code, 0)
            self.assertIn("formal_tool=symbiyosys", output.getvalue())
            summary_path = repo / ".dv-platform" / "runs" / "formal" / "fifo" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["stdout_tail"], ["formal cli ok", "fifo.sby", "DONE (PASS, rc=0)"])

    def test_run_reports_missing_simulator_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("No simulator configured for target cocotb", output.getvalue())

    def test_run_rejects_ambiguous_simulator_configuration(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                """
[paths]
repo_root = "."

[[simulators]]
target = "cocotb"
name = "first"
command = "first-sim"

[[simulators]]
target = "cocotb"
name = "second"
command = "second-sim"
""".strip(),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("selection is ambiguous", output.getvalue())

    def test_run_reports_configured_simulator_and_missing_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                """
[paths]
repo_root = "."

[[simulators]]
target = "cocotb"
name = "icarus"
command = "iverilog"
""".strip(),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("simulator=icarus", output.getvalue())
            self.assertIn("summary=", output.getvalue())
            summary_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing_artifacts")

    def test_run_all_reports_missing_generated_modules(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                """
[paths]
repo_root = "."

[[simulators]]
target = "cocotb"
name = "fake"
command = "fake-sim"
""".strip(),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--all"])

            self.assertEqual(exit_code, 2)
            self.assertIn("No generated modules found", output.getvalue())

    def test_run_all_executes_generated_modules_and_writes_aggregate_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            simulator_script = repo / "fake_sim.py"
            simulator_script.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "module = Path(sys.argv[-1]).name\n"
                "run_dir = Path(__file__).parent / '.dv-platform/runs/simulation/cocotb' / module\n"
                "run_dir.mkdir(parents=True, exist_ok=True)\n"
                "if module != 'bad':\n"
                "    (run_dir / 'results.xml').write_text('<testsuite><testcase name=\"passes\"/></testsuite>')\n"
                "print(module)\n"
                "raise SystemExit(3 if module == 'bad' else 0)\n",
                encoding="utf-8",
            )
            (repo / DEFAULT_CONFIG_FILENAME).write_text(
                f"""
[paths]
repo_root = "."

[[simulators]]
target = "cocotb"
name = "fake"
command = "{sys.executable} {simulator_script}"
""".strip(),
                encoding="utf-8",
            )
            modules_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules"
            _write_project_manifest(load_config(repo / DEFAULT_CONFIG_FILENAME), repo / "rtl" / "fifo.sv")
            _write_valid_cocotb_artifacts(modules_dir / "good", "good")
            _write_valid_cocotb_artifacts(modules_dir / "bad", "bad")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--all"])

            self.assertEqual(exit_code, 3)
            text = output.getvalue()
            self.assertIn("modules=bad,good", text)
            self.assertIn("aggregate_summary=", text)

            aggregate_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "summary.json"
            aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
            self.assertEqual(aggregate["status"], "failed")
            self.assertEqual(aggregate["total"], 2)
            self.assertEqual(aggregate["passed"], 1)
            self.assertEqual(aggregate["failed"], 1)
            self.assertEqual([item["module"] for item in aggregate["modules"]], ["bad", "good"])

            output = io.StringIO()
            with redirect_stdout(output):
                json_exit_code = main(["--repo-root", str(repo), "--json", "run", "--target", "cocotb", "--all"])

            self.assertEqual(json_exit_code, 3)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "run")
            self.assertEqual(payload["data"]["modules"], ["bad", "good"])
            self.assertEqual(payload["data"]["return_code"], 3)
            self.assertEqual(payload["data"]["runner"]["family"], "simulator")

    def test_analyze_rtl_runs_configured_verilator_and_writes_normalized_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top(input clk); endmodule\n", encoding="utf-8")
            (repo / "rtl" / "files.f").write_text("top.sv\n", encoding="utf-8")
            fake_verilator = repo / "fake_verilator.py"
            fake_verilator.write_text(
                """#!/usr/bin/env python3
import pathlib
import sys

if "--version" in sys.argv:
    print("Verilator 5.999 test")
    raise SystemExit(0)

calls = pathlib.Path(__file__).with_name("verilator-calls.txt")
calls.write_text(str(int(calls.read_text()) + 1) if calls.exists() else "1")
mdir = pathlib.Path(sys.argv[sys.argv.index("--Mdir") + 1])
mdir.mkdir(parents=True, exist_ok=True)
(mdir / "Vtop.xml").write_text(
    '<verilator_xml><module name="top"><var name="clk" dir="input" /></module></verilator_xml>',
    encoding="utf-8",
)
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                        "--verilator-executable",
                        f"{sys.executable} {fake_verilator}",
                    ]
                )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("dry_run=False", text)
            self.assertIn("verilator_return_code=0", text)
            self.assertIn("verilator_version=Verilator 5.999 test", text)
            self.assertIn("normalized_modules=1", text)

            facts = json.loads((repo / ".dv-platform" / "rtl-facts" / "modules.json").read_text(encoding="utf-8"))
            self.assertEqual(facts["verilator_version"], "Verilator 5.999 test")
            self.assertEqual(facts["modules"][0]["name"], "top")
            self.assertEqual(facts["modules"][0]["clocks"], ["clk"])

            cached_output = io.StringIO()
            with redirect_stdout(cached_output):
                cached_exit = main(["--repo-root", str(repo), "analyze-rtl"])

            self.assertEqual(cached_exit, 0)
            self.assertIn("cache_hit=true", cached_output.getvalue())
            self.assertEqual((repo / "verilator-calls.txt").read_text(), "1")

            (repo / "rtl" / "top.sv").write_text("module top(input clk, input rst); endmodule\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                changed_exit = main(["--repo-root", str(repo), "analyze-rtl"])
            self.assertEqual(changed_exit, 0)
            self.assertEqual((repo / "verilator-calls.txt").read_text(), "2")

    def test_analyze_rtl_enforces_report_and_required_slang_policy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for mode, expected_exit in (("report", 0), ("required", 2)):
                repo = root / mode
                (repo / "rtl").mkdir(parents=True)
                (repo / "rtl" / "top.sv").write_text("module top(input clk); endmodule\n", encoding="utf-8")
                (repo / "rtl" / "files.f").write_text("top.sv\n", encoding="utf-8")
                fake_verilator = repo / "fake_verilator.py"
                fake_verilator.write_text(
                    """import pathlib
import sys

if "--version" in sys.argv:
    print("Verilator 5.020 test")
    raise SystemExit(0)
mdir = pathlib.Path(sys.argv[sys.argv.index("--Mdir") + 1])
mdir.mkdir(parents=True, exist_ok=True)
(mdir / "Vtop.xml").write_text(
    '<verilator_xml><module name="top"><var name="clk" dir="input" /></module></verilator_xml>',
    encoding="utf-8",
)
""",
                    encoding="utf-8",
                )
                with redirect_stdout(io.StringIO()):
                    init_exit = main(
                        [
                            "--repo-root",
                            str(repo),
                            "init",
                            "--rtl-filelist",
                            "rtl/files.f",
                            "--top-module",
                            "top",
                            "--verilator-executable",
                            f"{sys.executable} {fake_verilator}",
                            "--slang-executable",
                            str(repo / "missing-slang"),
                            "--semantic-crosscheck",
                            mode,
                        ]
                    )
                self.assertEqual(init_exit, 0)
                config = load_config(repo / DEFAULT_CONFIG_FILENAME)
                self.assertEqual(config.semantic_crosscheck, mode)
                self.assertEqual(config.slang_executable, str(repo / "missing-slang"))

                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = main(["--repo-root", str(repo), "analyze-rtl"])

                self.assertEqual(exit_code, expected_exit)
                result_path = repo / ".dv-platform" / "semantic-crosscheck" / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                self.assertEqual(result["status"], "unavailable")
                self.assertFalse(result["passed"])
                self.assertTrue((repo / ".dv-platform" / "slang" / "diagnostics.json").is_file())
                self.assertTrue((repo / ".dv-platform" / "rtl-facts" / "modules.json").is_file())
                if mode == "report":
                    self.assertIn("semantic_crosscheck_status=unavailable", output.getvalue())
                else:
                    self.assertIn("does not satisfy the configured policy", output.getvalue())

    def test_required_crosscheck_blocks_planning_without_passing_artifact(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init", "--semantic-crosscheck", "required"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            write_normalized_rtl_facts(config, (), "Verilator 5.020")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "plan"])

            self.assertEqual(exit_code, 2)
            self.assertIn("requires a passing Slang cross-check", output.getvalue())

    def test_analyze_rtl_runs_both_frontends_and_caches_passing_crosscheck(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            source = repo / "rtl" / "top.sv"
            source.write_text("module top(input clk); endmodule\n", encoding="utf-8")
            (repo / "rtl" / "files.f").write_text("top.sv\n", encoding="utf-8")
            fake_verilator = repo / "fake_verilator.py"
            fake_verilator.write_text(
                """import pathlib
import sys
if "--version" in sys.argv:
    print("Verilator 5.020 test")
    raise SystemExit(0)
mdir = pathlib.Path(sys.argv[sys.argv.index("--Mdir") + 1])
mdir.mkdir(parents=True, exist_ok=True)
(mdir / "Vtop.xml").write_text(
    '<verilator_xml><module name="top"><var name="clk" dir="input" /></module></verilator_xml>',
    encoding="utf-8",
)
""",
                encoding="utf-8",
            )
            fake_slang = repo / "fake_slang.py"
            fake_slang.write_text(
                """import json
import pathlib
import sys
if "--version" in sys.argv:
    print("slang 11.0.0 test")
    raise SystemExit(0)
calls = pathlib.Path(__file__).with_name("slang-calls.txt")
calls.write_text(str(int(calls.read_text()) + 1) if calls.exists() else "1")
output = pathlib.Path(sys.argv[sys.argv.index("--ast-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "design": {"members": [{
        "kind": "InstanceBody",
        "name": "top",
        "source_file": "top.sv",
        "members": [{
            "kind": "Port",
            "name": "clk",
            "direction": "In",
            "type": {"kind": "ScalarType", "isSigned": False},
        }],
    }]},
}), encoding="utf-8")
""",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                        "--verilator-executable",
                        f"{sys.executable} {fake_verilator}",
                        "--slang-executable",
                        f"{sys.executable} {fake_slang}",
                        "--semantic-crosscheck",
                        "required",
                    ]
                )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl"])

            self.assertEqual(exit_code, 0)
            self.assertIn("semantic_crosscheck_status=passed", output.getvalue())
            result_path = repo / ".dv-platform" / "semantic-crosscheck" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(result["passed"])
            self.assertEqual(result["reference"]["version"], "slang 11.0.0 test")
            command = json.loads((repo / ".dv-platform" / "slang" / "slang-command.json").read_text())
            self.assertIn(str(source), command)
            self.assertIn("top", command)

            with redirect_stdout(io.StringIO()):
                cached_exit = main(["--repo-root", str(repo), "analyze-rtl"])
            self.assertEqual(cached_exit, 0)
            self.assertEqual((repo / "slang-calls.txt").read_text(), "1")

    def test_analyze_rtl_crosschecks_every_parameter_sweep_point(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text(
                "module top #(parameter int WIDTH = 8) (input logic clk); endmodule\n",
                encoding="utf-8",
            )
            (repo / "rtl" / "files.f").write_text("top.sv\n", encoding="utf-8")
            fake_verilator = repo / "fake_verilator.py"
            fake_verilator.write_text(
                """import pathlib
import sys
if "--version" in sys.argv:
    print("Verilator 5.020 test")
    raise SystemExit(0)
width = next((item.split("=", 1)[1] for item in sys.argv if item.startswith("-GWIDTH=")), "8")
mdir = pathlib.Path(sys.argv[sys.argv.index("--Mdir") + 1])
mdir.mkdir(parents=True, exist_ok=True)
(mdir / "Vtop.xml").write_text(
    '<verilator_xml><module name="top"><var name="WIDTH" param="true"><const name="32\\\'d' + width +
    '" /></var><var name="clk" dir="input" /></module></verilator_xml>',
    encoding="utf-8",
)
""",
                encoding="utf-8",
            )
            fake_slang = repo / "fake_slang.py"
            fake_slang.write_text(
                """import json
import pathlib
import sys
if "--version" in sys.argv:
    print("slang 11.0.0 test")
    raise SystemExit(0)
width = sys.argv[sys.argv.index("-G") + 1].split("=", 1)[1]
calls = pathlib.Path(__file__).with_name("slang-sweep-calls.txt")
with calls.open("a", encoding="utf-8") as stream:
    stream.write(width + "\\n")
output = pathlib.Path(sys.argv[sys.argv.index("--ast-json") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "design": {"members": [{
        "kind": "InstanceBody",
        "name": "top",
        "members": [
            {"kind": "Parameter", "name": "WIDTH", "value": width},
            {"kind": "Port", "name": "clk", "direction": "In", "type": {"kind": "ScalarType"}},
        ],
    }]},
}), encoding="utf-8")
""",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                init_exit = main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                        "--parameter-sweep",
                        "WIDTH=8",
                        "--parameter-sweep",
                        "WIDTH=16",
                        "--verilator-executable",
                        f"{sys.executable} {fake_verilator}",
                        "--slang-executable",
                        f"{sys.executable} {fake_slang}",
                        "--semantic-crosscheck",
                        "required",
                    ]
                )
            self.assertEqual(init_exit, 0)

            analyze_output = io.StringIO()
            with redirect_stdout(analyze_output):
                analyze_exit = main(["--repo-root", str(repo), "analyze-rtl"])

            result_path = repo / ".dv-platform" / "semantic-crosscheck" / "result.json"
            self.assertEqual(
                analyze_exit,
                0,
                analyze_output.getvalue() + (result_path.read_text(encoding="utf-8") if result_path.is_file() else ""),
            )
            self.assertEqual((repo / "slang-sweep-calls.txt").read_text(encoding="utf-8").splitlines(), ["8", "16"])
            self.assertEqual(len(tuple((repo / ".dv-platform" / "sweeps").glob("*/slang/ast.json"))), 2)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["checked_modules"]), 2)

    def test_analyze_rtl_writes_machine_readable_verilator_failure_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            (repo / "rtl" / "files.f").write_text("top.sv\n", encoding="utf-8")
            fake_verilator = repo / "fake_verilator.py"
            fake_verilator.write_text(
                """#!/usr/bin/env python3
import sys

if "--version" in sys.argv:
    print("Verilator 5.999 test")
    raise SystemExit(0)

print("bad rtl", file=sys.stderr)
raise SystemExit(7)
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                        "--verilator-executable",
                        f"{sys.executable} {fake_verilator}",
                    ]
                )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl"])

            self.assertEqual(exit_code, 7)
            summary_path = repo / ".dv-platform" / "runs" / "analyze-rtl" / "verilator-failure.json"
            self.assertIn(f"verilator_failure_summary={summary_path}", output.getvalue())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["return_code"], 7)
            self.assertEqual(summary["verilator_version"], "Verilator 5.999 test")
            self.assertEqual(summary["stderr_tail"], ["bad rtl"])


def _prepare_generated_cocotb_state(repo: Path) -> Path:
    with redirect_stdout(io.StringIO()):
        main(["--repo-root", str(repo), "init"])
    config = load_config(repo / DEFAULT_CONFIG_FILENAME)
    modules = normalize_verilator_xml((FIXTURES_ROOT / "verilator" / "simple_counter" / "Vsimple_counter.xml",))
    write_normalized_rtl_facts(config, modules, "Verilator 5.999 test")
    _write_project_manifest(config, repo / "rtl" / "simple_counter.sv")
    with redirect_stdout(io.StringIO()):
        main(["--repo-root", str(repo), "plan", "--target", "cocotb"])
        main(["--repo-root", str(repo), "generate", "--target", "cocotb"])
    return (
        repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "simple_counter" / "provenance.json"
    )


def _write_valid_formal_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    harness_path = generated_dir / f"formal_{module}.sv"
    harness_path.write_text(
        "module formal_" + module + "; endmodule\n",
        encoding="utf-8",
    )
    sby_path = generated_dir / f"{module}.sby"
    sby_path.write_text("[options]\nmode prove\n", encoding="utf-8")
    harness_trace = _traceability(module, f"formal_{module}_properties")
    sby_trace = _traceability(module, f"formal_{module}_run")
    execution_path = _write_execution_manifest(
        generated_dir,
        module,
        "formal",
        (
            (harness_path.name, "formal_harness", harness_trace[0]["trace_id"]),
            (sby_path.name, "run_script", sby_trace[0]["trace_id"]),
        ),
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": "formal",
                "artifacts": [
                    {
                        "path": f"formal_{module}.sv",
                        "kind": "formal_harness",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(harness_path.read_bytes()).hexdigest(),
                        "size_bytes": harness_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": harness_trace,
                    },
                    {
                        "path": f"{module}.sby",
                        "kind": "run_script",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(sby_path.read_bytes()).hexdigest(),
                        "size_bytes": sby_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": sby_trace,
                    },
                    {
                        "path": execution_path.name,
                        "kind": "report",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(execution_path.read_bytes()).hexdigest(),
                        "size_bytes": execution_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_valid_cocotb_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    test_path = generated_dir / f"test_{module}.py"
    test_path.write_text(
        "import cocotb\n\n@cocotb.test()\nasync def test_" + module + "_smoke(dut):\n    assert dut is not None\n",
        encoding="utf-8",
    )
    traceability = _traceability(module, f"test_{module}_smoke")
    execution_path = _write_execution_manifest(
        generated_dir,
        module,
        "cocotb",
        ((test_path.name, "testbench", traceability[0]["trace_id"]),),
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": "cocotb",
                "artifacts": [
                    {
                        "path": test_path.name,
                        "kind": "testbench",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
                        "size_bytes": test_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": traceability,
                    },
                    {
                        "path": execution_path.name,
                        "kind": "report",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(execution_path.read_bytes()).hexdigest(),
                        "size_bytes": execution_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_project_manifest(config, hdl_path: Path) -> None:
    hdl_path.parent.mkdir(parents=True, exist_ok=True)
    hdl_path.write_text("module fifo; endmodule\n", encoding="utf-8")
    manifest_path = config.work_dir / "project-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"hdl_files": [{"path": str(hdl_path), "language": "systemverilog"}]}) + "\n",
        encoding="utf-8",
    )


def _traceability(module: str, symbol: str) -> list[dict[str, object]]:
    return [
        {
            "trace_id": f"{module}:{symbol}",
            "generated_symbol": symbol,
            "check_indexes": [1],
            "requirement_ids": [f"{module}:requirement"],
            "behavior_ids": [f"{module}:behavior"],
            "claim_ids": [f"{module}:claim"],
            "evidence_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
        }
    ]


def _write_execution_manifest(
    generated_dir: Path,
    module: str,
    target: str,
    files: tuple[tuple[str, str, str], ...],
) -> Path:
    path = generated_dir / "execution-manifest.json"
    repo = generated_dir.parents[4] if target == "formal" else generated_dir.parents[5]
    project_manifest_path = repo / ".dv-platform" / "project-manifest.json"
    project_payload = (
        json.loads(project_manifest_path.read_text(encoding="utf-8")) if project_manifest_path.is_file() else {}
    )
    hdl_files = []
    for item in project_payload.get("hdl_files", []):
        source = Path(item["path"])
        hdl_files.append(
            {
                **item,
                "size_bytes": source.stat().st_size,
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": target,
                "adapter": {"kind": "formal" if target == "formal" else "simulation"},
                "generated_files": [
                    {"path": file_path, "kind": kind, "trace_ids": [trace_id]} for file_path, kind, trace_id in files
                ],
                "project": {
                    "manifest_path": str(project_manifest_path) if project_manifest_path.is_file() else None,
                    "manifest_sha256": (
                        hashlib.sha256(project_manifest_path.read_bytes()).hexdigest()
                        if project_manifest_path.is_file()
                        else None
                    ),
                    "hdl_files": hdl_files,
                    "include_paths": project_payload.get("include_paths", []),
                    "defines": project_payload.get("defines", []),
                    "top_modules": project_payload.get("top_modules", []),
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
