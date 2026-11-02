import csv
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.enterprise.equivalence import _logical_netlist
from dv_platform.enterprise.layout import parse_drc_report
from dv_platform.enterprise.native import run_native
from dv_platform.enterprise.power import current_density_bound, read_em_current
from dv_platform.physical_design import evaluate_physical_candidate, physical_requirements
from tests.ai.test_physical_design import analysis


class NativeVerificationTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_a_fresh_native_report_is_required_and_logged(self):
        output = self.root / "report.json"
        output.write_text("stale")
        with self.assertRaises(ValueError):
            run_native((sys.executable, "-c", "pass"), self.root, "stale", expected=(output.name,))
        self.assertFalse(output.exists())
        receipt = json.loads((self.root / "stale.receipt.json").read_text())
        self.assertEqual(receipt["status"], "error")
        result = run_native(
            (sys.executable, "-c", "open('report.json','w').write('{}')"), self.root, "fresh", expected=(output.name,)
        )
        self.assertEqual(result["status"], "passed")
        self.assertIn(output.name, result["artifacts"])

    def test_zero_exit_tool_errors_and_empty_results_are_rejected(self):
        for code in ("print('Error: invalid input')", "open('report.json','w').close()"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                run_native((sys.executable, "-c", code), self.root, "bad", expected=("report.json",))

    def test_timeout_and_memory_pressure_leave_failed_receipts(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_native((sys.executable, "-c", "import time;time.sleep(20)"), self.root, "timeout", timeout=0.05)
        self.assertEqual(json.loads((self.root / "timeout.receipt.json").read_text())["status"], "error")
        with patch("dv_platform.enterprise.native.Path.read_text", return_value="MemAvailable: 1 kB\n"):
            with self.assertRaisesRegex(RuntimeError, "memory reserve"):
                run_native((sys.executable, "-c", "import time;time.sleep(20)"), self.root, "pressure")

    def test_outputs_cannot_alias_external_or_linked_files(self):
        original = self.root / "original"
        original.write_text("preserve")
        (self.root / "linked").symlink_to(original)
        for expected in (("linked",), ("../escape",)):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                run_native((sys.executable, "-c", "pass"), self.root, "bad-output", expected=expected)
        self.assertEqual(original.read_text(), "preserve")
        for name, timeout in (("../unsafe", 1), ("safe", 0), ("safe", 86401)):
            with self.assertRaises(ValueError):
                run_native((sys.executable,), self.root, name, timeout=timeout)

    def test_only_disconnected_known_physical_cells_can_be_excluded_from_proof(self):
        source, target = self.root / "source.v", self.root / "logical.v"
        source.write_text(
            "module cpu_top(input a,output q); assign q=a;\n"
            "sky130_fd_sc_hd__tapvpwrvgnd_1 physical_tap ();\n"
            "sky130_fd_sc_hd__fill_4 physical_fill ();\nendmodule\n"
        )
        excluded = _logical_netlist(source, target)
        self.assertEqual(sum(excluded.values()), 2)
        self.assertIn("assign q=a", target.read_text())
        source.write_text(source.read_text().replace("physical_tap ()", "physical_tap (.Q(q))"))
        with self.assertRaisesRegex(ValueError, "logical connections"):
            _logical_netlist(source, target)
        source.write_text("module cpu_top; arbitrary_unknown_cell inst(); endmodule\n")
        self.assertEqual(_logical_netlist(source, target), {})
        self.assertIn("arbitrary_unknown_cell", target.read_text())

    def test_drc_requires_a_complete_native_database(self):
        path = self.root / "drc.rdb"
        path.write_text("<report-database><cells/><items><item/><item/></items></report-database>")
        self.assertEqual(parse_drc_report(path), 2)
        path.write_text("<report-database><cells/><items/></report-database>")
        self.assertEqual(parse_drc_report(path), 0)
        path.write_text("<report-database><cells/></report-database>")
        with self.assertRaises(ValueError):
            parse_drc_report(path)

    def em_report(self, current="0.0001", *, header=True):
        path = self.root / "em.csv"
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "Node0 Layer",
                    "Node0 X location",
                    "Node0 Y location",
                    "Node1 Layer",
                    "Node1 X location",
                    "Node1 Y location",
                    "Current",
                ]
                if header
                else ["unexpected"]
            )
            if current is not None:
                writer.writerow(["met1", "0", "0", "met2", "0", "0", current])
        return path

    def test_em_parsing_checks_units_structure_and_finiteness(self):
        self.assertEqual(read_em_current(self.em_report("-0.0001")), {"max_current_a": 0.0001, "segments": 1})
        for current, header in (("nan", True), (None, True), ("1", False)):
            with self.subTest(current=current, header=header), self.assertRaises(ValueError):
                read_em_current(self.em_report(current, header=header))

    def test_em_density_uses_a_conservative_cross_section_including_vias(self):
        geometry = {"minimum_width_um": {"met1": 0.48, "met4": 1.6}, "via_count": 2, "minimum_via_cut_area_um2": 0.0225}
        policy = {"metal_thickness_um": {"met1": 0.3, "met4": 0.8}}
        self.assertAlmostEqual(current_density_bound(geometry, {"max_current_a": 0.001}, policy), 0.001 / 0.0225)
        with self.assertRaises(FileNotFoundError):
            current_density_bound(geometry, {"max_current_a": 0.001}, {"metal_thickness_um": {}})


class ScenarioAcceptanceTests(TestCase):
    def baseline(self):
        baseline = analysis()
        baseline["production_limits"] = {
            "area_max_um2": None,
            "power_max_watts": None,
            "setup_margin_ns": 0,
            "hold_margin_ns": 0,
        }
        baseline["metrics"].update(
            {
                "scenario:tt_nom:hold_wns_ns": -0.05,
                "scenario:ff_min:hold_wns_ns": -0.01,
                "scenario:tt_nom:setup_wns_ns": -0.03,
            }
        )
        return baseline

    def test_a_hidden_corner_regression_is_rejected_even_when_worst_slack_improves(self):
        baseline = self.baseline()
        candidate = deepcopy(baseline)
        candidate["metrics"]["scenario:tt_nom:hold_wns_ns"] = -0.02
        candidate["metrics"]["scenario:ff_min:hold_wns_ns"] = -0.015
        candidate["metrics"]["setup_wns_ns"] = -0.02
        result = evaluate_physical_candidate(baseline, baseline, candidate)
        self.assertFalse(result["selected"])
        self.assertIn("scenario:ff_min:hold_wns_ns", result["regressions"])

    def test_approved_budgets_replace_the_demo_growth_allowance(self):
        baseline = self.baseline()
        self.assertNotIn("area_um2", physical_requirements(baseline)["metrics"])
        baseline["production_limits"].update(area_max_um2=700, power_max_watts=0.5, setup_margin_ns=0.1)
        requirements = physical_requirements(baseline)["metrics"]
        self.assertEqual(requirements["area_um2"]["target"], 700)
        self.assertEqual(requirements["scenario:tt_nom:setup_wns_ns"]["target"], 0.1)
