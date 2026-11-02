import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from dv_platform.core.config import default_config
from dv_platform.enterprise import cpu, equivalence, native, signoff
from dv_platform.physical_design import file_digest, tcl_string, write_document
from dv_platform.product import CapabilityDeniedError
from dv_platform.signoff import read_document
from tests.ai.test_physical_design import analysis
from tests.support.entitlements import issue_test_entitlement
from tests.support.signoff import passing_checks, project_v2, run_fixture


class SignoffWorkflowTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path, self.project, self.policy = project_v2(self.root / "project")
        pin = patch(
            "dv_platform.signoff._pinned_sky130_files",
            return_value=read_document(self.path.parent / "technology-lock.json")["files"],
        )
        pin.start()
        self.addCleanup(pin.stop)
        self.config = replace(
            default_config(self.root),
            product=issue_test_entitlement(self.root, ("cli.enterprise", "adapter.enterprise")),
        )

    def test_check_binds_source_and_measurements_and_preserves_unknown_requirements(self):
        run = run_fixture(self.root, self.path, self.project)
        with (
            patch.object(signoff, "verify_current_workflow"),
            patch.object(signoff, "_native_checks", return_value=passing_checks()),
        ):
            result = signoff.check_release(self.config, self.path, run)
        self.assertFalse(result["signoff_approved"])
        self.assertFalse(result["engineering_ready"])
        self.assertIn("area_max_um2", result["requirements_gaps"])
        index = read_document(self.config.work_dir / "signoff/latest.json")
        self.assertEqual(file_digest(self.config.work_dir / index["release"]), index["sha256"])
        (run.parent / "baseline/reference.v").write_text("tampered after measurement")
        with patch.object(signoff, "_native_checks") as checks, self.assertRaisesRegex(ValueError, "digest"):
            signoff.check_release(self.config, self.path, run)
        checks.assert_not_called()

    def test_checks_cannot_change_measured_artifacts_or_write_release_outside_work(self):
        run = run_fixture(self.root, self.path, self.project)

        def mutate(*args):
            (run.parent / "baseline/native.log").write_text("changed during verification")
            return passing_checks()

        with (
            patch.object(signoff, "verify_current_workflow"),
            patch.object(signoff, "_native_checks", side_effect=mutate),
        ):
            with self.assertRaisesRegex(ValueError, "digest"):
                signoff.check_release(self.config, self.path, run)
        (run.parent / "baseline/native.log").write_text("synthetic test artifact\n")
        with (
            patch.object(signoff, "verify_current_workflow"),
            patch.object(signoff, "_native_checks", return_value=passing_checks()),
        ):
            with self.assertRaisesRegex(ValueError, "configured work"):
                signoff.check_release(self.config, self.path, run, output=self.root / "outside")

    def test_native_checks_run_independently_and_incomplete_checks_stay_unknown(self):
        measured = analysis()
        measured["scenarios"] = {s["name"]: {"activity_coverage_percent": 0} for s in self.project["scenarios"]}
        with (
            patch.object(signoff, "prove_equivalence", return_value={"status": "passed"}) as proof,
            patch.object(signoff, "stream_layout", return_value=["results/design.gds"]),
            patch.object(signoff, "klayout_drc", return_value={"violations": 0}),
            patch.object(
                signoff, "magic_extract", return_value={"complete": True, "drc_violations": 1, "antenna_violations": 0}
            ),
            patch.object(signoff, "netgen_lvs", return_value={"matched_uniquely": True}) as lvs,
            patch.object(signoff, "density_check", side_effect=RuntimeError("unsupported window")),
            patch.object(signoff, "electrical_connectivity", return_value={"checked_power_pins": 4, "violations": 0}),
            patch.object(signoff, "analyze_power", side_effect=FileNotFoundError("supply sources missing")),
        ):
            checks = signoff._native_checks(self.path.parent, self.project, self.policy, measured, None)
        self.assertEqual(proof.call_count, 2)
        self.assertEqual(checks["drc_magic"]["status"], "failed")
        self.assertEqual(checks["antenna"]["status"], "passed")
        self.assertEqual(checks["lvs"]["status"], "passed")
        lvs.assert_called_once()
        for name in ("requirements", "density", "power_grid", "ir_drop", "em", "activity"):
            self.assertEqual(checks[name]["status"], "unknown", name)
        self.assertEqual(checks["timing"]["status"], "failed")

    def test_export_failure_blocks_all_dependent_layout_checks(self):
        measured = analysis()
        measured["scenarios"] = {"view": {"activity_coverage_percent": 99}}
        with (
            patch.object(signoff, "_equivalence_checks"),
            patch.object(signoff, "_power_checks"),
            patch.object(signoff, "stream_layout", side_effect=ValueError("unresolved layout cell")),
            patch.object(signoff, "magic_extract") as magic,
        ):
            checks = signoff._native_checks(self.path.parent, self.project, self.policy, measured, None)
        for name in ("drc_magic", "drc_klayout", "lvs", "antenna", "density"):
            self.assertEqual(checks[name]["status"], "failed", name)
            self.assertIn("unresolved layout cell", checks[name]["reason"])
        magic.assert_not_called()

    def test_power_limits_and_incomplete_thickness_remain_separate_gates(self):
        geometry = {"violations": 0, "minimum_width_um": {"met1": 0.5}, "via_count": 0}
        self.policy["limits"].update(ir_drop_max_v=0.01, em_max_current_density_a_um2=0.001)
        stage = self.root / "verification"
        stage.mkdir()
        for thickness, em_state in (({}, "unknown"), ({"met1": 1}, "failed")):
            checks = {}
            self.policy["metal_thickness_um"] = thickness
            with (
                patch.object(signoff, "electrical_connectivity", return_value=geometry),
                patch.object(signoff, "analyze_power", return_value={"worst_ir_drop_v": 0.02, "max_current_a": 0.002}),
            ):
                signoff._power_checks(self.path.parent, self.project, self.policy, stage, checks)
            self.assertEqual(checks["ir_drop"]["status"], "failed")
            self.assertEqual(checks["em"]["status"], em_state)
        self.assertEqual(signoff._limit_check("native", "value", 1, None, ["report"])["status"], "unknown")

    def test_entitlement_is_checked_before_any_native_work_or_input_loading(self):
        config = replace(self.config, product=replace(self.config.product, entitlement_path=self.root / "missing"))
        with patch.object(signoff, "load_physical_project") as load, self.assertRaises(CapabilityDeniedError):
            signoff.check_release(config, self.path, self.root / "missing-run")
        load.assert_not_called()

    def test_equivalence_resource_budget_is_bounded_and_reaches_both_native_proofs(self):
        with patch.object(signoff, "_check_release") as check:
            for invalid in (True, 255, 262145, 4096.5):
                with self.subTest(memory=invalid), self.assertRaisesRegex(ValueError, "memory budget"):
                    signoff.check_release(
                        self.config, self.path, self.root / "missing-run", equivalence_memory_mb=invalid
                    )
            check.assert_not_called()
        run = run_fixture(self.root, self.path, self.project)
        with (
            patch.object(signoff, "verify_current_workflow"),
            patch.object(signoff, "_native_checks", return_value=passing_checks()) as checks,
        ):
            result = signoff.check_release(self.config, self.path, run, equivalence_memory_mb=8192)
        self.assertEqual(checks.call_args.args[-1], 8192)
        self.assertFalse(result["signoff_approved"])
        with patch.object(signoff, "prove_equivalence", return_value={"status": "passed"}) as proof:
            results = {}
            signoff._equivalence_checks(self.path.parent, self.project, self.root / "proofs", results, 8192)
        self.assertEqual(proof.call_count, 2)
        self.assertTrue(all(call.kwargs["memory_mb"] == 8192 for call in proof.call_args_list))

    def test_signoff_cli_forwards_requested_equivalence_memory(self):
        from dv_platform.enterprise.cli import build_parser

        args = build_parser().parse_args(
            [
                "signoff",
                "check",
                "--project",
                str(self.path),
                "--run",
                "run.json",
                "--equivalence-memory-mb",
                "8192",
            ]
        )
        with patch.object(signoff, "check_release", return_value={"engineering_ready": False}) as check:
            self.assertFalse(signoff.dispatch_signoff(args, self.config)[1])
        self.assertEqual(check.call_args.kwargs["equivalence_memory_mb"], 8192)

    def test_status_ci_requires_production_approval_and_arguments_are_required(self):
        args = SimpleNamespace(action="status", trust_policy=None, release=None, policy="ci")
        with patch.object(signoff, "collect_signoff_status", return_value={"signoff_approved": False}):
            self.assertFalse(signoff.dispatch_signoff(args, self.config)[1])
            args.policy = "report"
            self.assertTrue(signoff.dispatch_signoff(args, self.config)[1])
        for action in ("check", "characterize", "import-approval"):
            args = SimpleNamespace(
                action=action, trust_policy=None, release=None, project=None, run=None, approval=None
            )
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "requires"):
                signoff.dispatch_signoff(args, self.config)

    def test_characterization_includes_replayed_proposal_and_keeps_approval_false(self):
        measured = analysis()
        measured["scenarios"] = {"functional": {"clocks": measured["clocks"]}}
        measured["directory"] = str(self.root / "case")
        run = {"output": str(self.root / "run"), "status": "timing_open", "best": measured}
        with (
            patch.object(signoff, "run_physical_optimization", return_value=run),
            patch.object(signoff, "replay_period_proposal", return_value={"status": "replayed"}),
        ):
            result = signoff.characterize(self.config, self.path)
        self.assertEqual(result["period_exploration"]["status"], "replayed")
        self.assertFalse(result["engineering_ready"])
        self.assertFalse(result["signoff_approved"])
        self.assertEqual(result["status"], "characterized")

    def test_native_tool_failures_have_evidence_and_do_not_become_passes(self):
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "partial.log").write_text("partial result")
        for error, expected in (
            (subprocess.TimeoutExpired("native", 1), "unknown"),
            (RuntimeError("memory pressure"), "unknown"),
            (ValueError("bad report"), "failed"),
        ):

            def action(error=error):
                raise error

            result = signoff._perform(self.root, stage, "test", "tool", action)
            self.assertEqual(result["status"], expected)
            self.assertIn("stage/partial.log", result["artifacts"])

    def test_workflow_snapshot_detects_code_changes(self):
        source = self.root / "source.py"
        source.write_text("original workflow")
        with patch.object(native, "_workflow_sources", return_value={"source.py": source}):
            snapshot = native.snapshot_workflow(self.root / "workflow")
            native.verify_current_workflow(snapshot)
            source.write_text("changed workflow")
            with self.assertRaisesRegex(ValueError, "changed after"):
                native.verify_current_workflow(snapshot)

    def test_workflow_archive_includes_drivers_and_pins(self):
        snapshot = native.snapshot_workflow(self.root / "actual-workflow")
        native.verify_current_workflow(snapshot)
        for name in (
            "physical_design.tcl",
            "sky130_flow.tcl",
            "sky130-pin.json",
            "enterprise/equivalence.py",
            "ai/physical_design.py",
            "enterprise/timing.py",
        ):
            self.assertIn(name, snapshot)


class CpuPreparationTests(TestCase):
    def test_native_coarse_mapping_preserves_state_correspondence_for_induction(self):
        yosys = shutil.which("yosys")
        if yosys is None or shutil.which("prlimit") is None:
            self.skipTest("native Yosys and prlimit are required")
        source = self.work / "rtl/top/cpu_top.sv"
        source.write_text(
            "module cpu_top(input clk,en,output y); reg [11:0] state; "
            "always @(posedge clk) if(en) state<=state+1'b1; assign y=state[11]; endmodule\n"
        )
        self.metadata["source_sha256"]["rtl/top/cpu_top.sv"] = file_digest(source)
        write_document(self.work / "source-snapshot.json", self.metadata)
        optimized = self.work / "build/cpu/optimized.il"
        optimized.parent.mkdir(parents=True)
        native.run_native(
            (
                yosys,
                "-Q",
                "-T",
                "-p",
                f"read_verilog -sv {tcl_string(str(source))}; proc; write_rtlil {tcl_string(str(optimized))}",
            ),
            self.work,
            "fixture",
            timeout=30,
            expected=("build/cpu/optimized.il",),
        )
        write_document(
            self.work / "cpu-synthesis.receipt.json",
            {
                "status": "passed",
                "artifacts": {"build/cpu/optimized.il": file_digest(optimized)},
            },
        )

        def execute(command, work, name, **kwargs):
            if name == "cpu-map-coarse":
                return native.run_native(command, work, name, timeout=30, expected=kwargs["expected"])
            for filename in kwargs["expected"]:
                (work / filename).write_text("synthetic downstream output")
            return {"status": "passed", "artifacts": {n: file_digest(work / n) for n in kwargs["expected"]}}

        with patch.object(cpu, "run_native", side_effect=execute), patch.object(cpu, "create_project"):
            cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        native.run_native(
            (yosys, "-Q", "-T", "-p", "read_rtlil mapped-coarse.il; write_verilog -noattr coarse.v"),
            self.work,
            "coarse-export",
            timeout=30,
            expected=("coarse.v",),
        )
        proof = equivalence.prove_equivalence(
            source, self.work / "coarse.v", [], "cpu_top", self.root / "proof", timeout=30
        )
        self.assertEqual(proof["status"], "passed")

    def test_native_mapping_guard_accepts_parameterized_hierarchy_but_rejects_generic_logic(self):
        yosys = shutil.which("yosys")
        if yosys is None:
            self.skipTest("native Yosys is not installed")
        guards = "\n".join(
            line
            for line in cpu._mapping_script(self.root / "input.il", self.root / "cells.lib").splitlines()
            if line.startswith(("check ", "select -assert"))
        )
        source = self.root / "hierarchy.v"
        for expression, expected in (("a", 0), ("a & b", 1)):
            with self.subTest(expression=expression):
                source.write_text(
                    "module \\$paramod_child (input a,b, output y); assign y=" + expression + "; endmodule\n"
                    "module top(input a,b, output y); \\$paramod_child u(a,b,y); endmodule\n"
                )
                result = subprocess.run(
                    [yosys, "-Q", "-T", "-p", f"read_verilog {source}; hierarchy -check -top top; {guards}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "prepared"
        self.work = self.output / "source"
        self.work.mkdir(parents=True)
        source = self.work / "rtl/top/cpu_top.sv"
        source.parent.mkdir(parents=True)
        source.write_text("immutable local CPU source")
        self.metadata = {"source_sha256": {"rtl/top/cpu_top.sv": file_digest(source)}}
        write_document(self.work / "source-snapshot.json", self.metadata)
        self.pdk = self.root / "pdk"
        library = self.pdk / "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
        library.parent.mkdir(parents=True)
        library.write_text("synthetic test Liberty")

    def test_resource_failure_records_stage_and_resume_verifies_inputs(self):
        with patch.object(cpu, "run_native", side_effect=RuntimeError("memory reserve reached")):
            with self.assertRaisesRegex(RuntimeError, "memory"):
                cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        record = read_document(self.output / "preparation.json")
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["stage"], "synthesis")
        self.assertFalse(record["signoff_approved"])
        (self.work / "rtl/top/cpu_top.sv").write_text("changed snapshot")
        with patch.object(cpu, "run_native") as run, self.assertRaisesRegex(ValueError, "digest"):
            cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        run.assert_not_called()
        with self.assertRaises(ValueError):
            cpu.prepare_cpu_project(self.root, self.pdk, self.output, memory_mb=1)

    def test_mapping_reuses_verified_synthesis_and_records_exact_mapping(self):
        expected = "build/cpu/optimized.il"
        (self.work / expected).parent.mkdir(parents=True)
        (self.work / expected).write_text("synthetic generic RTLIL")
        write_document(
            self.work / "cpu-synthesis.receipt.json",
            {"status": "passed", "artifacts": {expected: file_digest(self.work / expected)}},
        )

        def execute(command, work, name, **kwargs):
            self.assertIn("--as=6442450944", command)
            for output in kwargs["expected"]:
                (work / output).write_text("synthetic mapped netlist")
            return {"status": "passed", "artifacts": {name: file_digest(work / name) for name in kwargs["expected"]}}

        tool = self.root / "fixture-yosys"
        tool.write_text("synthetic executable")

        with (
            patch.object(cpu, "run_native", side_effect=execute) as run,
            patch.object(cpu.shutil, "which", return_value=str(tool)),
            patch.object(cpu, "create_project", return_value=self.output / "project/project.json") as create,
        ):
            path = cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        self.assertEqual(run.call_count, 4)
        self.assertEqual(path, self.output / "project/project.json")
        self.assertEqual(
            create.call_args.kwargs["source_metadata"]["mapped_sha256"], file_digest(self.work / "mapped.v")
        )
        record = read_document(self.output / "preparation.json")
        self.assertEqual(record["status"], "prepared")
        self.assertEqual(record["stage"], "complete")
        script = (self.work / "cpu-mapping.ys").read_text()
        self.assertIn("check -mapped -assert", script)
        self.assertIn("dfflibmap", script)
        self.assertIn("-noshare", (self.work / "cpu-map-coarse.ys").read_text())
        self.assertIn("memory_map", (self.work / "cpu-map-memory.ys").read_text())
        self.assertIn("techmap -extern\ntechmap\n", (self.work / "cpu-map-fine.ys").read_text())
        self.assertIn("flatten N:$extern:*", (self.work / "cpu-map-fine.ys").read_text())
        self.assertIn("tools/mapping-statistics.json", create.call_args.kwargs["source_files"])
        with (
            patch.object(cpu, "run_native") as resumed,
            patch.object(cpu.shutil, "which", return_value=str(tool)),
            patch.object(cpu, "create_project", return_value=self.output / "project/project.json"),
        ):
            cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        resumed.assert_not_called()
        tool.write_text("changed synthetic executable")
        with (
            patch.object(cpu, "run_native", side_effect=execute) as changed_tool,
            patch.object(cpu.shutil, "which", return_value=str(tool)),
            patch.object(cpu, "create_project", return_value=self.output / "project/project.json"),
        ):
            cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        self.assertEqual(changed_tool.call_count, 4)
        (self.work / "mapped-coarse.il").write_text("changed checkpoint")
        with (
            patch.object(cpu, "run_native") as run,
            patch.object(cpu.shutil, "which", return_value=str(tool)),
            self.assertRaisesRegex(ValueError, "digest"),
        ):
            cpu.prepare_cpu_project(self.root / "unused", self.pdk, self.output, resume=True)
        run.assert_not_called()


class EquivalenceProtocolTests(TestCase):
    def test_native_ports_only_proof_ignores_changed_internal_meanings_but_checks_outputs(self):
        if shutil.which("yosys") is None or shutil.which("prlimit") is None:
            self.skipTest("native Yosys and prlimit are required")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.v"
            reference.write_text("module cpu_top(input a,b,output q); wire t=a; assign q=t^b; endmodule\n")
            candidate = root / "candidate.v"
            candidate.write_text("module cpu_top(input a,b,output q); wire t=b; assign q=t^a; endmodule\n")
            result = equivalence.prove_equivalence(
                reference, candidate, [], "cpu_top", root / "positive", ports_only=True, timeout=30
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["comparison_scope"], "ports")
            candidate.write_text("module cpu_top(input a,b,output q); wire t=b; assign q=t|a; endmodule\n")
            with self.assertRaisesRegex(ValueError, "native equivalence failed"):
                equivalence.prove_equivalence(
                    reference, candidate, [], "cpu_top", root / "negative", ports_only=True, timeout=30
                )
            self.assertIn("unproven $equiv", (root / "negative/equivalence.stderr.log").read_text())

    def test_native_structural_validation_is_required_before_proof(self):
        if shutil.which("yosys") is None or shutil.which("prlimit") is None:
            self.skipTest("native Yosys and prlimit are required")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.v"
            invalid.write_text("module cpu_top(input a,output y); assign y=~y; endmodule\n")
            output = root / "proof"
            with self.assertRaisesRegex(ValueError, "native validate-gold failed"):
                equivalence.prove_equivalence(invalid, invalid, [], "cpu_top", output, timeout=30)
            self.assertEqual(read_document(output / "prepare-gold.receipt.json")["status"], "passed")
            self.assertEqual(read_document(output / "validate-gold.receipt.json")["status"], "error")
            self.assertFalse((output / "equivalence.json").exists())
            self.assertFalse((output / "proof.json").exists())

    def test_native_hierarchical_clock_models_reject_changed_edge(self):
        if shutil.which("yosys") is None or shutil.which("prlimit") is None:
            self.skipTest("native Yosys and prlimit are required")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = (
                "(* keep_hierarchy *) module leaf(input clk,d,output reg q); always @(posedge clk) q<=d; endmodule\n"
                "module cpu_top(input clk,d,output q); (* keep_hierarchy *) leaf u(clk,d,q); endmodule\n"
            )
            reference = root / "reference.v"
            reference.write_text(source)
            result = equivalence.prove_equivalence(reference, reference, [], "cpu_top", root / "positive", timeout=30)
            self.assertEqual(result["status"], "passed")
            changed = root / "changed.v"
            changed.write_text(source.replace("posedge", "negedge"))
            with self.assertRaisesRegex(ValueError, "native equivalence failed"):
                equivalence.prove_equivalence(reference, changed, [], "cpu_top", root / "negative", timeout=30)

    def test_proof_requires_all_obligations_and_records_original_and_normalized_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.v"
            reference.write_text("module cpu_top(input a,output q);assign q=a;endmodule\n")
            gate = root / "gate.v"
            gate.write_text(reference.read_text() + "sky130_fd_sc_hd__fill_1 fill ();\n")
            library = root / "cells.lib"
            library.write_text("synthetic test Liberty")

            def execute(command, work, *args, **kwargs):
                for name in kwargs["expected"]:
                    (work / name).write_text('{"modules":{"equiv":{}}}' if name.endswith(".json") else "native model")
                return {
                    "status": "passed",
                    "artifacts": {name: file_digest(work / name) for name in kwargs["expected"]},
                }

            with (
                patch.object(equivalence, "run_native", side_effect=execute) as native_run,
                patch.object(equivalence.shutil, "which", side_effect=lambda n: n),
            ):
                result = equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "proof")
            self.assertEqual(result["reference_sha256"], file_digest(reference))
            self.assertEqual(result["candidate_sha256"], file_digest(gate))
            self.assertEqual(result["excluded_disconnected_physical_cells"][1], {"sky130_fd_sc_hd__fill_1": 1})
            self.assertEqual(native_run.call_count, 5)
            self.assertEqual(
                [call.args[2] for call in native_run.call_args_list],
                [
                    "prepare-gold",
                    "validate-gold",
                    "prepare-gate",
                    "validate-gate",
                    "equivalence",
                ],
            )
            script = "\n".join(path.read_text() for path in (root / "proof").glob("*.ys"))
            for required in (
                "check -assert",
                "select -assert-none a:blackbox",
                "select -assert-min 1 t:$equiv",
                "equiv_status -assert",
                "equiv_induct",
            ):
                self.assertIn(required, script)
            with patch.object(equivalence.shutil, "which", return_value=None), self.assertRaises(ValueError):
                equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "no-tool")
            with self.assertRaises(ValueError):
                equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "bad-limit", memory_mb=1)
            with self.assertRaises(ValueError):
                equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "bad-timeout", timeout=0)
            with (
                patch.object(equivalence, "run_native", side_effect=execute) as timed_run,
                patch.object(equivalence.shutil, "which", side_effect=lambda n: n),
                patch.object(equivalence, "_monotonic", side_effect=[0, 1, 2, 4000]),
                self.assertRaises(subprocess.TimeoutExpired),
            ):
                equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "timeout")
            self.assertEqual(timed_run.call_count, 2)
            self.assertFalse((root / "timeout/proof.json").exists())

            def mutate(command, work, *args, **kwargs):
                receipt = execute(command, work, *args, **kwargs)
                gate.write_text("changed during execution")
                return receipt

            with (
                patch.object(equivalence, "run_native", side_effect=mutate),
                patch.object(equivalence.shutil, "which", side_effect=lambda n: n),
                self.assertRaisesRegex(ValueError, "inputs changed"),
            ):
                equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / "mutated")
            self.assertFalse((root / "mutated/proof.json").exists())
            gate.write_text(reference.read_text())
            for stage in ("prepare-gate", "equivalence"):
                with self.subTest(stage=stage):

                    def alter_model(command, work, name, stage=stage, **kwargs):
                        receipt = execute(command, work, name, **kwargs)
                        if name == stage:
                            (work / "gold.il").write_text("modified prepared model")
                        return receipt

                    with (
                        patch.object(equivalence, "run_native", side_effect=alter_model),
                        patch.object(equivalence.shutil, "which", side_effect=lambda n: n),
                        self.assertRaisesRegex(ValueError, "inputs changed"),
                    ):
                        equivalence.prove_equivalence(reference, gate, [library], "cpu_top", root / stage)
                    self.assertFalse((root / stage / "proof.json").exists())
            for filename, stage in (("gold.v", "prepare-gold"), ("validate-gold.ys", "validate-gold")):
                with self.subTest(filename=filename):

                    def alter_input(command, work, name, filename=filename, stage=stage, **kwargs):
                        receipt = execute(command, work, name, **kwargs)
                        if name == stage:
                            (work / filename).write_text("modified stage input")
                        return receipt

                    with (
                        patch.object(equivalence, "run_native", side_effect=alter_input),
                        patch.object(equivalence.shutil, "which", side_effect=lambda n: n),
                        self.assertRaisesRegex(ValueError, "inputs changed"),
                    ):
                        equivalence.prove_equivalence(
                            reference, gate, [library], "cpu_top", root / f"changed-{filename}"
                        )
                    self.assertFalse((root / f"changed-{filename}" / "proof.json").exists())
