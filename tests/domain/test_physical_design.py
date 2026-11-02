import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.physical_design import METRICS, load_physical_project, read_physical_analysis, tcl_string


def project_fixture(root):
    project = {
        "schema_version": 1,
        "design": "top",
        "flow": "flow.tcl",
        "inputs": ["flow.tcl", "constraints.sdc", "cells.lib"],
        "constraints": ["constraints.sdc"],
        "libraries": ["cells.lib"],
        "parasitics": "results/route.spef",
    }
    for name in project["inputs"]:
        (root / name).write_text("fixture\n")
    manifest = root / "project.json"
    manifest.write_text(json.dumps(project))
    return manifest, project


def native_metrics():
    metrics = {"PD::" + key: 0 for key in METRICS}
    metrics.update(
        {
            "flow__errors__count": 0,
            "PD::setup_wns_ns": -0.03,
            "PD::setup_tns_ns": -0.2,
            "PD::hold_wns_ns": 0.04,
            "PD::area_um2": 600,
            "PD::routed": 1,
            "PD::constraints_ok": 1,
            "PD::instance_count": 100,
            "PD::view_count": 1,
            "PD::clock_count": 1,
            "PD::clock/0/name": "core",
            "PD::clock/0/period_ns": 0.485,
        }
    )
    for mode in ("setup", "hold"):
        prefix = f"PD::path/{mode}"
        metrics.update(
            {
                prefix + "/count": 1,
                prefix + "/0/point_count": 1,
                prefix + "/0/point_total_count": 2,
                prefix + "/0/startpoint": "reg/Q",
                prefix + "/0/endpoint": "resp[15]",
                prefix + "/0/slack_ns": -0.03 if mode == "setup" else 0.04,
                prefix + "/0/arrival_ns": 0.1,
                prefix + "/0/required_arrival_ns": 0.07 if mode == "setup" else 0.06,
                prefix + "/0/point/0/pin": "reg/Q",
                prefix + "/0/point/0/arrival_ns": 0.1,
            }
        )
    return metrics


class PhysicalDesignTests(TestCase):
    def test_manifest_requires_explicit_inputs_and_rejects_paths_and_artifact_collisions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, project = project_fixture(root)
            self.assertEqual(load_physical_project(path), project)
            for changes in (
                {"schema_version": True},
                {"unknown": "value"},
                {"flow": "../escape.tcl"},
                {"parasitics": "/tmp/stale.spef"},
                {"parasitics": "cells.lib"},
                {"inputs": ["flow.tcl", "cells.lib"]},
                {"inputs": project["inputs"] + ["pd-power.json"]},
                {"inputs": project["inputs"] + ["sta-driver.tcl"]},
                {"libraries": ["a/../cells.lib"]},
                {"constraints": ["constraints.sdc", "constraints.sdc"]},
            ):
                path.write_text(json.dumps({**project, **changes}))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_physical_project(path)

    def test_input_symlinks_and_missing_assets_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, _ = project_fixture(root)
            library = root / "cells.lib"
            library.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                load_physical_project(path)
            library.symlink_to(root / "constraints.sdc")
            with self.assertRaisesRegex(ValueError, "linked"):
                load_physical_project(path)

    def test_native_analysis_preserves_failing_metrics_and_path_truncation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pd-metrics.json"
            path.write_text(json.dumps(native_metrics()))
            path.with_name("pd-power.json").write_text(json.dumps({"Total": {"total": 0.0024}}))
            measured = read_physical_analysis(path)
            self.assertFalse(measured["timing_closed"])
            self.assertEqual(measured["failures"], ["setup_wns_ns", "setup_tns_ns"])
            self.assertEqual(measured["metrics"]["power_watts"], 0.0024)
            self.assertEqual(measured["paths"][0]["evidence_id"], "setup:0")
            self.assertTrue(measured["paths"][0]["points_truncated"])
            self.assertEqual(measured["clocks"], {"core": 0.485})

    def test_analysis_rejects_nonfinite_incomplete_unconstrained_and_multiple_views(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pd-metrics.json"
            power = path.with_name("pd-power.json")
            power.write_text(json.dumps({"Total": {"total": 0.0024}}))
            for key, value in (
                ("PD::setup_wns_ns", "nan"),
                ("PD::setup_wns_ns", 10**400),
                ("PD::hold_wns_ns", True),
                ("PD::view_count", 2),
                ("PD::clock_count", 0),
                ("PD::instance_count", 0),
                ("PD::drc_violations", 0.5),
                ("PD::setup_tns_ns", 0.1),
                ("PD::path/setup/count", 6),
                ("PD::path/hold/0/point_count", 65),
                ("PD::path/setup/0/required_arrival_ns", 2),
                ("flow__errors__count", 1),
            ):
                metrics = deepcopy(native_metrics())
                metrics[key] = value
                path.write_text(json.dumps(metrics))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    read_physical_analysis(path)
            path.write_text(json.dumps(native_metrics()))
            for invalid in ({}, {"Total": {}}, {"Total": {"total": -1}}, {"Total": {"total": "inf"}}):
                power.write_text(json.dumps(invalid))
                with self.subTest(power=invalid), self.assertRaises(ValueError):
                    read_physical_analysis(path)

    def test_multiple_implementation_views_require_the_exact_declared_count(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pd-metrics.json"
            metrics = native_metrics()
            metrics["PD::view_count"] = 3
            path.write_text(json.dumps(metrics))
            path.with_name("pd-power.json").write_text(json.dumps({"Total": {"total": 0.0024}}))
            self.assertEqual(read_physical_analysis(path, expected_view_count=3)["metrics"]["view_count"], 3)
            for count in (1, 2, 0, 129, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    read_physical_analysis(path, expected_view_count=count)

    def test_tcl_strings_quote_substitution_and_command_characters(self):
        self.assertEqual(tcl_string('a[$x];"b\\c'), '"a\\[\\$x\\];\\"b\\\\c"')
