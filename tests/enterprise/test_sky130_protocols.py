"""Portable checks of the native tool protocols; native qualification runs separately."""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.enterprise import layout, power, timing
from dv_platform.physical_design import write_document
from tests.ai.test_physical_design import analysis
from tests.support.signoff import project_v2


def timing_report(root, stem, *, setup=3.0):
    data = dict.fromkeys(timing.TIMING_FIELDS, 0)
    data.update(setup_wns_ns=setup, hold_wns_ns=0.2, clock_count=1, **{"clock/0/name": "clk", "clock/0/period_ns": 10})
    for mode, slack, arrival, required in (("setup", setup, 7, 7 + setup), ("hold", 0.2, 0.3, 0.1)):
        data.update(
            {
                f"{mode}/count": 1,
                f"{mode}/0/slack_ns": slack,
                f"{mode}/0/arrival_ns": arrival,
                f"{mode}/0/required_arrival_ns": required,
                f"{mode}/0/startpoint": "reg/Q",
                f"{mode}/0/endpoint": "out",
                f"{mode}/0/point_count": 2,
                f"{mode}/0/point_total_count": 2,
                f"{mode}/0/point/0/pin": "reg/Q",
                f"{mode}/0/point/0/arrival_ns": 0,
                f"{mode}/0/point/1/pin": "out",
                f"{mode}/0/point/1/arrival_ns": arrival,
            }
        )
    write_document(root / f"{stem}.json", data)
    write_document(root / f"{stem}.power.json", {"Total": {"total": 0.001}})
    (root / f"{stem}.checks.rpt").write_text("analysis_complete=1\n")
    (root / f"{stem}.activity.rpt").write_text("vcd 98\ninput 1\nunannotated 1\n")
    (root / f"{stem}.sdc").write_text("create_clock -name clk -period 10 [get_ports clk]\n")
    return data


class TimingProtocolTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _, self.project, _ = project_v2(self.root)

    def test_every_view_replays_its_own_library_sdc_and_spef_in_two_engines(self):
        def execute(command, work, stem, **kwargs):
            script = (work / f"{stem}.tcl").read_text()
            view = next(v for v in self.project["scenarios"] if v["name"] in stem)
            self.assertIn(view["libraries"][0], script)
            self.assertIn(view["constraints"][0], script)
            self.assertIn(view["parasitics"], script)
            self.assertEqual("read_db" in script, command[0] == "openroad")
            self.assertEqual("read_verilog" in script, command[0] == "sta")
            self.assertIn("set_propagated_clock", script)
            timing_report(work, stem, setup=3.0 if command[0] == "openroad" else 2.9999995)

        with patch.object(timing, "run_native", side_effect=execute) as native:
            views = timing.analyze_scenarios(self.root, self.project, {"openroad": "openroad", "sta": "sta"})
        self.assertEqual(native.call_count, 18)
        self.assertEqual(len(views), 9)
        self.assertTrue(all(v["metrics"]["setup_wns_ns"] == 2.9999995 for v in views.values()))
        self.assertTrue(all(v["activity_coverage_percent"] == 98 for v in views.values()))
        self.assertEqual(json.loads((self.root / "scenarios.json").read_text()), views)

    def test_replay_disagreement_cannot_be_accepted(self):
        for field in ("setup_wns_ns", "clocks", "resolved_constraints_sha256"):

            def execute(command, work, stem, field=field, **kwargs):
                timing_report(work, stem)
                if command[0] == "sta":
                    if field == "resolved_constraints_sha256":
                        (work / f"{stem}.sdc").write_text("set_false_path -to [all_outputs]\n")
                    else:
                        data = json.loads((work / f"{stem}.json").read_text())
                        data["clock/0/period_ns" if field == "clocks" else field] += 1
                        if field == "setup_wns_ns":
                            data["setup/0/slack_ns"] += 1
                            data["setup/0/required_arrival_ns"] += 1
                        write_document(work / f"{stem}.json", data)

            with self.subTest(field=field), patch.object(timing, "run_native", side_effect=execute):
                with self.assertRaisesRegex(ValueError, "disagrees"):
                    timing.analyze_scenarios(self.root, self.project, {"openroad": "openroad", "sta": "sta"})

    def test_reports_require_bounded_paths_consistent_slack_and_activity_counts(self):
        for field, value in (
            ("clock_count", 0),
            ("setup/count", 6),
            ("hold/count", 0),
            ("setup/0/required_arrival_ns", 100),
            ("clock/0/period_ns", -1),
            ("hold_tns_ns", 1),
            ("setup/0/point_count", 65),
            ("setup/0/point_count", 0),
            ("setup/0/point_total_count", 1),
            ("setup/0/point_total_count", 2.5),
            ("setup/0/point/1/pin", ""),
            ("setup/0/point/1/arrival_ns", "inf"),
        ):
            data = timing_report(self.root, "view")
            data[field] = value
            write_document(self.root / "view.json", data)
            with self.subTest(field=field), self.assertRaises(ValueError):
                timing._read_scenario(self.root, "view", "functional")
        timing_report(self.root, "view")
        (self.root / "view.activity.rpt").write_text("vcd 99\n")
        with self.assertRaisesRegex(ValueError, "activity"):
            timing._read_scenario(self.root, "view", "functional")
        (self.root / "view.activity.rpt").write_text("vcd 0\nunannotated 0\n")
        with self.assertRaises(ValueError):
            timing._read_scenario(self.root, "view", "functional")

    def test_special_checks_and_vcd_are_part_of_the_analysis(self):
        timing_report(self.root, "view")
        (self.root / "view.checks.rpt").write_text("recovery (VIOLATED)\nremoval (VIOLATED)\nanalysis_complete=1\n")
        report = timing._read_scenario(self.root, "view", "functional")
        self.assertEqual(report["metrics"]["special_check_slack"], -2)
        project = deepcopy(self.project)
        project["activity"] = {"file": "activity.vcd", "scope": "tb/cpu", "workload": "test"}
        script = timing._scenario_script(project, project["scenarios"][0], "view", embedded=False)
        self.assertIn('read_vcd -scope "tb/cpu" "activity.vcd"', script)
        with self.assertRaises(ValueError):
            timing._path({}, "functional", "setup", 5)

    def test_scenario_paths_preserve_pin_evidence_and_report_truncation(self):
        data = timing_report(self.root, "view")
        path = timing._read_scenario(self.root, "view", "functional")["paths"][0]
        self.assertEqual([point["pin"] for point in path["points"]], ["reg/Q", "out"])
        self.assertEqual(path["points"][-1]["arrival_ns"], path["arrival_ns"])
        self.assertEqual(path["total_point_count"], 2)
        self.assertFalse(path["points_truncated"])
        data["setup/0/point_total_count"] = 100
        path = timing._path(data, "functional", "setup", 0)
        self.assertTrue(path["points_truncated"])
        self.assertEqual(len(path["points"]), 2)
        del data["setup/0/point/1/pin"]
        with self.assertRaises(ValueError):
            timing._path(data, "functional", "setup", 0)

    def test_rc_extractions_use_separate_native_processes_and_declared_outputs(self):
        def execute(command, work, stem, **kwargs):
            (output,) = kwargs["expected"]
            target = work / output
            target.parent.mkdir(exist_ok=True)
            target.write_text(stem)

        with patch.object(timing, "run_native", side_effect=execute) as native:
            timing._extract_corners(self.root, self.project, "openroad")
        self.assertEqual(native.call_count, 3)
        self.assertEqual(len({c.kwargs["expected"] for c in native.call_args_list}), 3)

    def test_period_exploration_replays_a_proposal_without_changing_the_contract(self):
        measured = analysis()
        measured["clocks"] = {"clk": 100}
        measured["scenarios"] = {
            view["name"]: {"clocks": {"clk": 100}, "metrics": dict.fromkeys(timing.TIMING_FIELDS, 0)}
            for view in self.project["scenarios"]
        }
        for view in measured["scenarios"].values():
            view["metrics"]["setup_wns_ns"] = 95
        before = (self.root / "functional.sdc").read_bytes()

        def replay(work, trial, tools, **kwargs):
            self.assertEqual(kwargs["prefix"], "characterization")
            for view in trial["scenarios"]:
                self.assertTrue(view["constraints"][0].startswith("characterization-period/"))
                script = (work / view["constraints"][0]).read_text()
                self.assertIn("create_clock", script)
                self.assertIn("Clock_waveform", script)
            return measured["scenarios"]

        with patch.object(timing, "analyze_scenarios", side_effect=replay):
            result = timing.replay_period_proposal(
                self.root, self.project, measured, {}, {"setup_margin_ns": 0, "hold_margin_ns": 0}
            )
        self.assertEqual(result["proposed_period_ns"], 5.5)
        self.assertTrue(result["timing_closed"])
        self.assertFalse(result["requirements_changed"])
        self.assertEqual((self.root / "functional.sdc").read_bytes(), before)
        measured["clocks"]["other"] = 20
        self.assertEqual(
            timing.replay_period_proposal(self.root, self.project, measured, {}, {})["status"],
            "requires_engineering_input",
        )

    def test_matrix_metrics_and_paths_replace_typical_only_acceptance(self):
        measured = analysis()
        views = {}
        for index, view in enumerate(self.project["scenarios"]):
            timing_report(self.root, f"view-{index}")
            parsed = timing._read_scenario(self.root, f"view-{index}", view["name"])
            if index == 8:
                parsed["metrics"]["hold_wns_ns"] = -0.1
                parsed["metrics"]["hold_tns_ns"] = -0.1
                parsed["paths"][1]["slack_ns"] = -0.1
            views[view["name"]] = parsed
        with patch.object(timing, "_extract_corners"), patch.object(timing, "analyze_scenarios", return_value=views):
            timing.augment_analysis(measured, self.root, self.project, {"openroad": "openroad"})
        self.assertEqual(measured["metrics"]["view_count"], 9)
        self.assertEqual(measured["metrics"]["hold_wns_ns"], -0.1)
        self.assertFalse(measured["timing_closed"])
        self.assertIn("hold_wns_ns", measured["failures"])
        self.assertEqual(measured["paths"][5]["mode"], "hold")
        self.assertNotEqual(measured["resolved_constraints_sha256"], "unchanged")


class LayoutProtocolTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _, self.project, _ = project_v2(self.root)
        self.stage = self.root / "verification/check"
        self.stage.mkdir(parents=True)
        pin = patch.object(layout, "validate_tool_fingerprints")
        pin.start()
        self.addCleanup(pin.stop)
        tool = patch.object(layout, "_tool", side_effect=lambda name: name)
        tool.start()
        self.addCleanup(tool.stop)

    def test_export_uses_the_pinned_layer_map_and_drc_writes_an_absolute_report(self):
        mapping = self.root / "technology/klayout/sky130A.map"
        mapping.parent.mkdir(parents=True)
        mapping.write_text("met1 NET 68 20\n")

        def execute(command, work, stem, **kwargs):
            if "-drc" in stem:
                report = command[command.index("report=" + str(self.stage / "drc.rdb"))]
                Path(report.split("=", 1)[1]).write_text("<report-database><cells/><items/></report-database>")

        with patch.object(layout, "run_native", side_effect=execute):
            files = layout.stream_layout(self.root, self.project, self.stage)
            self.assertIn(self.project["deliverables"]["gds"], files)
            self.assertEqual(layout.klayout_drc(self.root, self.project, self.stage), {"violations": 0})
        script = (self.stage / "stream.rb").read_text()
        self.assertIn(str(self.stage / "stream.map"), script)
        self.assertEqual(mapping.read_text(), "met1 NET 68 20\n")
        self.assertIn("met3 FILL 70 20", (self.stage / "stream.map").read_text())
        self.assertIn("produce_pins = true", script)
        self.assertIn("produce_labels = true", script)

    def test_magic_requires_complete_nonnegative_counts(self):
        for report in (
            {"complete": True, "drc_violations": 2, "antenna_violations": 0},
            {"complete": False},
            {"complete": True, "drc_violations": -1, "antenna_violations": 0},
        ):

            def execute(*args, report=report, **kwargs):
                write_document(self.stage / "magic.json", report)

            with patch.object(layout, "run_native", side_effect=execute):
                if report.get("drc_violations") == 2:
                    self.assertEqual(layout.magic_extract(self.root, self.project, self.stage), report)
                else:
                    with self.assertRaises(ValueError):
                        layout.magic_extract(self.root, self.project, self.stage)

    def test_lvs_checks_the_final_result_and_rejects_unresolved_cells(self):
        for text, passed in (
            ("Final result: Circuits match uniquely.", True),
            ("Netlists do not match.", False),
            ("black box\nFinal result: Circuits match uniquely.", False),
            ("Netlists match uniquely.\nFinal result: Circuits match uniquely with property errors.", False),
            (
                "Netlists match uniquely with property errors.\nFinal result: Circuits match uniquely.\n"
                "The following cells had property errors:\n sky130_fd_sc_hd__diode_2\n",
                False,
            ),
        ):

            def execute(command, work, stem, text=text, **kwargs):
                if stem.endswith("-cdl"):
                    (self.stage / "reference.cdl").write_text(".SUBCKT cpu_top\n.ENDS\n")
                else:
                    (self.stage / "lvs.log").write_text(text)

            with patch.object(layout, "run_native", side_effect=execute):
                if passed:
                    self.assertTrue(layout.netgen_lvs(self.root, self.project, self.stage)["matched_uniquely"])
                else:
                    with self.assertRaises(ValueError):
                        layout.netgen_lvs(self.root, self.project, self.stage)
        self.assertIn("technology/cells.spice", (self.stage / "reference.spice").read_text())
        self.assertIn("-include_fillers", (self.stage / "reference.tcl").read_text())

    def test_density_uses_the_design_top_and_keeps_unsupported_blocks_inconclusive(self):
        gds = self.root / self.project["deliverables"]["gds"]
        gds.parent.mkdir()
        gds.write_bytes(b"synthetic test GDS")
        for text, error, expected in (
            ("Whole-chip density results:\nDensity results (total tiles = 1)\nERROR: density", False, 1),
            (
                "Whole-chip density results:\nDensity results (total tiles = 1)\n"
                "***Error:  FOM Density < 33%\n***Error:  MET1 Density < 35%\n",
                False,
                2,
            ),
            (
                "Whole-chip density results:\nDensity results (total tiles = 1)\n"
                "failure: local density\neRrOr: whole-chip density\n",
                False,
                2,
            ),
            ("Whole-chip density results:\nDensity results (total tiles = 1)\nMET1 Density: 40%", False, 0),
            ("Layout is < 700um x 700um", True, RuntimeError),
            ("couldn't be read\nLayout is < 700um x 700um", True, ValueError),
            ("partial results", False, ValueError),
        ):

            def execute(command, work, stem, text=text, error=error, **kwargs):
                self.assertEqual(Path(command[-1]).name, "cpu_top.gds")
                self.assertEqual((work / command[-1]).read_bytes(), gds.read_bytes())
                self.assertFalse(kwargs["check_output_errors"])
                (work / f"{stem}.stdout.log").write_text(text)
                if error:
                    raise ValueError("native failure")

            with self.subTest(text=text), patch.object(layout, "run_native", side_effect=execute):
                if isinstance(expected, int):
                    self.assertEqual(layout.density_check(self.root, self.project, self.stage)["violations"], expected)
                else:
                    with self.assertRaises(expected):
                        layout.density_check(self.root, self.project, self.stage)
                self.assertFalse((self.stage / "cpu_top.gds").exists())


class PowerProtocolTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _, self.project, self.policy = project_v2(self.root)
        self.stage = self.root / "verification/power"
        self.stage.mkdir(parents=True)
        for target in ("validate_tool_fingerprints", "shutil.which"):
            mock = (
                patch.object(power, target)
                if "." not in target
                else patch("dv_platform.enterprise.power." + target, return_value="openroad")
            )
            mock.start()
            self.addCleanup(mock.stop)

    def test_erc_requires_actual_inspected_pins_and_valid_violation_counts(self):
        for report in (
            {"checked_power_pins": 4, "violations": 0},
            {"checked_power_pins": 0, "violations": 0},
            {"checked_power_pins": 4, "violations": True},
        ):

            def execute(*args, report=report, **kwargs):
                write_document(self.stage / "electrical.json", report)

            with patch.object(power, "run_native", side_effect=execute):
                if report["checked_power_pins"] and type(report["violations"]) is int:
                    self.assertEqual(power.electrical_connectivity(self.root, self.project, self.stage), report)
                else:
                    with self.assertRaises(ValueError):
                        power.electrical_connectivity(self.root, self.project, self.stage)

    def test_all_scenarios_require_supply_sources_and_complete_current_reports(self):
        with self.assertRaises(FileNotFoundError):
            power.analyze_power(self.root, self.project, self.policy, self.stage)
        self.policy["supplies"] = {
            net: {"voltage": voltage, "sources": net + ".loc"} for net, voltage in (("VPWR", 1.8), ("VGND", 0))
        }
        with self.assertRaisesRegex(ValueError, "immutable"):
            power.analyze_power(self.root, self.project, self.policy, self.stage)
        for supply in self.policy["supplies"].values():
            (self.root / supply["sources"]).write_text(f"10,10,2,{supply['voltage']}\n")
            self.project["inputs"].append(supply["sources"])
        header = "Node0 Layer,Node0 X location,Node0 Y location,Node1 Layer,Node1 X location,Node1 Y location,Current\n"

        def execute(command, work, stem, **kwargs):
            metrics = work / kwargs["expected"][0]
            write_document(
                metrics,
                {
                    "signoff_power_complete": 1,
                    "design_powergrid__drop__worst__net:VPWR__corner:default": 0.001,
                    "design_powergrid__drop__worst__net:VGND__corner:default": 0.002,
                },
            )
            for name in kwargs["expected"][1:]:
                (work / name).write_text(header + "met1,0,0,met2,1,0,0.0001\n")

        with patch.object(power, "run_native", side_effect=execute) as native:
            result = power.analyze_power(self.root, self.project, self.policy, self.stage)
        self.assertEqual(native.call_count, 9)
        self.assertEqual(result["worst_ir_drop_v"], 0.002)
        self.assertEqual(result["em_segments"], 18)
        self.assertEqual(result["max_current_a"], 0.0001)
        for view in self.project["scenarios"]:
            script = (self.stage / view["name"] / "power.tcl").read_text()
            self.assertIn(view["parasitics"], script)
            voltage = {"tt_025C_1v80": "1.8", "ss_100C_1v60": "1.6", "ff_n40C_1v95": "1.95"}[view["pvt"]]
            self.assertIn(f"set_pdnsim_net_voltage -net VPWR -voltage {voltage}", script)

    def test_missing_and_negative_corner_metrics_fail(self):
        for metrics in ({}, {"drop__net:VPWR__corner:default": -1}):
            with self.assertRaises(ValueError):
                power._net_metric(metrics, "drop", "VPWR")

    def test_supply_locations_require_valid_geometry_and_nominal_voltage(self):
        path = self.root / "source.loc"
        for text in ("", "1,2,3\n", "1,2,0,1.8\n", "1,2,3,1.6\n", "nan,2,3,1.8\n"):
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                power._source_locations(path, 1.8)
        path.write_text("1,2,3,1.8\n")
        self.assertEqual(power._source_locations(path, 1.8), [[1, 2, 3]])
