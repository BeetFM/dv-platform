import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform import sky130
from dv_platform.physical_design import file_digest, load_physical_project
from dv_platform.signoff import load_requirements, read_document, requirements_gaps


class Sky130PreparationTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def fake_pdk(self):
        root = self.root / "pdk"
        for name, relative in sky130.PDK_ASSETS.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("met1 X 0.23 0.46\nmet1 Y 0.17 0.34\n" if name.endswith("tracks.info") else name)
        return root

    def test_project_materializes_all_inputs_and_leaves_real_limits_unsigned(self):
        pdk = self.fake_pdk()
        reference = self.root / "source.v"
        reference.write_text("module cpu_top; endmodule\n")
        tools = {name: {"version": "synthetic", "sha256": "0" * 64} for name in ("openroad", "sta", "yosys")}
        with patch.object(sky130, "tool_fingerprints", return_value=tools):
            path = sky130.create_project(
                self.root / "project",
                pdk,
                design="cpu_top",
                reference=reference,
                mapped=reference,
                source_files={"original.v": reference},
            )
        lock = read_document(path.parent / "technology-lock.json")
        expected = {name: file_digest(pdk / relative) for name, relative in sky130.PDK_ASSETS.items()}
        with patch("dv_platform.signoff._pinned_sky130_files", return_value=expected):
            project = load_physical_project(path)
            policy = load_requirements(path.parent / "requirements.json", project)
        self.assertEqual(len(project["scenarios"]), 9)
        self.assertIsNone(policy["signature"])
        self.assertIn("boundary_constraints", requirements_gaps(policy, project))
        self.assertIn("power_supply_sources", requirements_gaps(policy, project))
        self.assertIsNone(policy["limits"]["area_max_um2"])
        self.assertEqual(lock["tools"], tools)
        self.assertIn("source/original.v", project["inputs"])
        self.assertEqual((path.parent / "source/original.v").read_bytes(), reference.read_bytes())
        self.assertEqual((path.parent / "tracks.tcl").read_text().count("make_tracks"), 1)
        self.assertEqual(set(lock["files"]), {*sky130.PDK_ASSETS, "tracks.tcl", "technology/fill.json"})
        with self.assertRaises(FileExistsError):
            sky130.create_project(path.parent, pdk, design="cpu_top", reference=reference, mapped=reference)

    def test_missing_or_escaping_pdk_asset_is_not_accepted(self):
        pdk = self.fake_pdk()
        asset = pdk / next(iter(sky130.PDK_ASSETS.values()))
        asset.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            sky130.materialize_technology(pdk, self.root / "output")
        outside = self.root / "outside.lef"
        outside.write_text("outside")
        asset.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            sky130.materialize_technology(pdk, self.root / "output")

    def test_project_preparation_rejects_injected_designs_and_escaping_copy_targets(self):
        for design, sources in (("cpu;exec bad", {}), ("cpu_top", {"../../outside": self.root / "source.v"})):
            with self.subTest(design=design, sources=sources), self.assertRaises(ValueError):
                sky130.create_project(
                    self.root / "unsafe",
                    self.root / "pdk",
                    design=design,
                    reference=self.root / "source.v",
                    mapped=self.root / "source.v",
                    source_files=sources,
                )
        self.assertFalse((self.root / "unsafe").exists())

    def test_both_track_axes_and_positive_pitch_are_required(self):
        path = self.root / "technology/tracks.info"
        path.parent.mkdir()
        for content in ("met1 X 0 0\n", "met1 Z 0 1\n", "met1 X 0 1\n"):
            path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                sky130._write_flow_assets(self.root)

    def test_fingerprints_detect_binary_changes_and_missing_tools(self):
        binary = self.root / "tool"
        binary.write_bytes(b"synthetic test executable")
        result = subprocess.CompletedProcess([], 0, stdout="fixture 1.0\nmore details", stderr="")
        with (
            patch.object(sky130.shutil, "which", return_value=str(binary)),
            patch.object(sky130.subprocess, "run", return_value=result),
        ):
            tools = sky130.tool_fingerprints()
        self.assertEqual(len(tools), 6)
        self.assertEqual(tools["magic"]["version"], "fixture 1.0")
        (self.root / "lock.json").write_text(json.dumps({"tools": tools}))
        with patch.object(sky130.shutil, "which", return_value=str(binary)):
            sky130.validate_tool_fingerprints(self.root, {"technology_lock": "lock.json"}, ("magic",))
            binary.write_bytes(b"changed executable")
            with self.assertRaisesRegex(ValueError, "differs"):
                sky130.validate_tool_fingerprints(self.root, {"technology_lock": "lock.json"}, ("magic",))
        with patch.object(sky130.shutil, "which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                sky130.validate_tool_fingerprints(self.root, {"technology_lock": "lock.json"}, ("magic",))
            with self.assertRaisesRegex(ValueError, "requires openroad"):
                sky130.tool_fingerprints()

        def required_only(name):
            return str(binary) if name in {"openroad", "sta", "yosys"} else None

        with (
            patch.object(sky130.shutil, "which", side_effect=required_only),
            patch.object(sky130.subprocess, "run", return_value=result),
        ):
            self.assertEqual(set(sky130.tool_fingerprints()), {"openroad", "sta", "yosys"})
        result.stdout = ""
        with (
            patch.object(sky130.shutil, "which", return_value=str(binary)),
            patch.object(sky130.subprocess, "run", return_value=result),
        ):
            with self.assertRaisesRegex(ValueError, "identity"):
                sky130.tool_fingerprints()

    def test_snapshot_includes_dirty_sources_and_does_not_modify_checkout(self):
        source = self.root / "cpu"
        source.mkdir()
        for name in ("Makefile", "tools.lock.json", "rtl/top/cpu_top.sv", "third_party/memory.v", "synth/cpu.py"):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("local dirty source " + name)
        with patch.object(sky130.subprocess, "check_output", return_value="a" * 40):
            snapshot = sky130.snapshot_cpu(source, self.root / "snapshot")
        self.assertEqual(snapshot["scope"], "cpu_block")
        self.assertEqual(snapshot["base_revision"], "a" * 40)
        for name, expected in snapshot["source_sha256"].items():
            self.assertEqual(file_digest(source / name), expected)
            self.assertEqual(file_digest(self.root / "snapshot" / name), expected)
