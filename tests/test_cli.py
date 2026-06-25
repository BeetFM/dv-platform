import io
import json
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.cli import build_parser, config_from_args, main
from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, default_config, load_config, write_config
from dv_platform.core.models import FormalToolConfig, VerificationTarget
from dv_platform.analysis.docs import LoadedDocument, chunk_document, write_document_index
from dv_platform.analysis.plan_store import read_plan_records
from dv_platform.analysis.rtl import normalize_verilator_xml, write_normalized_rtl_facts


class CLITests(unittest.TestCase):
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

    def test_command_prints_local_paths(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(
                [
                    "--repo-root",
                    "repo",
                    "--work-dir",
                    "work",
                    "--output-dir",
                    "out",
                    "review",
                ]
            )

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        expected_root = Path("repo").resolve(strict=False)
        self.assertIn("command=review", text)
        self.assertIn(f"repo_root={expected_root}", text)
        self.assertIn(f"work_dir={expected_root / 'work'}", text)
        self.assertIn(f"output_dir={expected_root / 'out'}", text)
        self.assertIn("allow_network=False", text)
        self.assertIn("strict=False", text)
        self.assertIn("ci=False", text)

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
            self.assertEqual(config.top_modules, ("top",))
            self.assertFalse(config.strict)
            self.assertFalse(config.ci)

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
            self.assertEqual(index["schema_version"], 1)
            self.assertGreaterEqual(len(index["chunks"]), 2)

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
            modules = normalize_verilator_xml(
                (Path(__file__).parent / "fixtures" / "verilator" / "simple_counter" / "Vsimple_counter.xml",)
            )
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
            modules = normalize_verilator_xml(
                (Path(__file__).parent / "fixtures" / "verilator" / "simple_counter" / "Vsimple_counter.xml",)
            )
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
            modules = normalize_verilator_xml(
                (Path(__file__).parent / "fixtures" / "verilator" / "simple_counter" / "Vsimple_counter.xml",)
            )
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "cocotb"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "cocotb"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=generate", text)
            self.assertIn("artifacts=1", text)
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

    def test_generate_formal_loads_plans_and_writes_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "init"])
            config = load_config(repo / DEFAULT_CONFIG_FILENAME)
            modules = normalize_verilator_xml(
                (Path(__file__).parent / "fixtures" / "verilator" / "simple_counter" / "Vsimple_counter.xml",)
            )
            write_normalized_rtl_facts(config, modules, "Verilator test")
            with redirect_stdout(io.StringIO()):
                main(["--repo-root", str(repo), "plan", "--target", "formal"])

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "generate", "--target", "formal"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("command=generate", text)
            self.assertIn("artifacts=2", text)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "simple_counter"
            harness = generated_dir / "formal_simple_counter.sv"
            sby = generated_dir / "simple_counter.sby"
            self.assertTrue(harness.is_file())
            self.assertTrue(sby.is_file())
            self.assertIn("module formal_simple_counter;", harness.read_text(encoding="utf-8"))
            self.assertIn("prep -top formal_simple_counter", sby.read_text(encoding="utf-8"))
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
            modules = normalize_verilator_xml(
                (Path(__file__).parent / "fixtures" / "verilator" / "simple_counter" / "Vsimple_counter.xml",)
            )
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
                exit_code = main(["--repo-root", str(repo), "--strict", "run", "--target", "formal", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("No formal tools configured", output.getvalue())

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
                "from pathlib import Path\n"
                "import sys\n"
                "print('formal cli ok')\n"
                "print(Path(sys.argv[-1]).name)\n",
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
            _write_valid_formal_artifacts(generated_dir, "fifo")
            _write_project_manifest(load_config(repo / DEFAULT_CONFIG_FILENAME), repo / "rtl" / "fifo.sv")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "formal", "--module", "fifo"])

            self.assertEqual(exit_code, 0)
            self.assertIn("formal_tool=symbiyosys", output.getvalue())
            summary_path = repo / ".dv-platform" / "runs" / "formal" / "fifo" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["stdout_tail"], ["formal cli ok", "fifo.sby"])

    def test_run_reports_missing_simulator_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "run", "--target", "cocotb", "--module", "fifo"])

            self.assertEqual(exit_code, 2)
            self.assertIn("No simulator configured for target cocotb", output.getvalue())

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
            (modules_dir / "good").mkdir(parents=True)
            (modules_dir / "bad").mkdir(parents=True)

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

def _write_valid_formal_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / f"formal_{module}.sv").write_text(
        "module formal_" + module + "; endmodule\n",
        encoding="utf-8",
    )
    (generated_dir / f"{module}.sby").write_text("[options]\nmode prove\n", encoding="utf-8")
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "module": module,
                "target": "formal",
                "artifacts": [
                    {
                        "path": f"formal_{module}.sv",
                        "kind": "formal_harness",
                        "source_plan_module": module,
                        "provenance_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
                    },
                    {
                        "path": f"{module}.sby",
                        "kind": "run_script",
                        "source_plan_module": module,
                        "provenance_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
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


if __name__ == "__main__":
    unittest.main()
