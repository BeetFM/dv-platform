"""Mapping and final proofs must bracket the fixed physical replay."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.enterprise.rtl_physical import freeze_physical_project, measure_rtl
from dv_platform.physical_design import file_digest, write_document
from dv_platform.signoff import read_document
from tests.domain.test_physical_design import project_fixture
from tests.support.signoff import project_v2

BACKEND = "dv_platform.enterprise.rtl_physical"


class RTLPhysicalTests(TestCase):
    def test_v2_candidate_preserves_baseline_reference_and_raw_source_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template"
            path, manifest, _ = project_v2(template)
            manifest["inputs"].append("mapped.v")
            (template / "mapped.v").write_text("template implementation")
            write_document(path, manifest)
            reference, candidate, doc = (root / name for name in ("baseline.v", "candidate.v", "design.md"))
            reference.write_text("original logical contract")
            candidate.write_text("equivalent rewritten implementation")
            doc.write_text("unchanged engineering intent")
            project = {"design": "cpu_top", "mapping_library": manifest["libraries"][0], "netlist": "mapped.v"}

            def mapping(logical, library, project, workspace, sky130):
                workspace.mkdir()
                (workspace / "mapped.v").write_text("candidate technology mapping")

            with (
                patch(
                    "dv_platform.signoff._pinned_sky130_files",
                    return_value=read_document(template / "technology-lock.json")["files"],
                ),
                patch(f"{BACKEND}._map_netlist", side_effect=mapping),
                patch(
                    f"{BACKEND}.prove_equivalence",
                    return_value={
                        "status": "passed",
                        "candidate_sha256": "mapped",
                        "reference_sha256": "mapped",
                        "libraries_sha256": {"cells.lib": "locked"},
                    },
                ),
                patch(
                    f"{BACKEND}._run_physical_optimization",
                    return_value={"best": {"directory": str(root / "native")}, "output": str(root / "native")},
                ),
            ):
                measure_rtl(
                    object(),
                    project,
                    template,
                    candidate,
                    root / "experiment",
                    reference=reference,
                    rtl_inputs={
                        "baseline/design.v": reference,
                        "selected/design.v": candidate,
                        "baseline/design.md": doc,
                    },
                )
            copied = root / "experiment/project"
            self.assertEqual((copied / "reference.v").read_text(), "original logical contract")
            metadata = read_document(copied / "source-snapshot.json")
            self.assertEqual(metadata["baseline_reference_sha256"], file_digest(reference))
            self.assertEqual(metadata["candidate_logical_sha256"], file_digest(candidate))
            self.assertIn("source-snapshot.json", read_document(copied / "project.json")["inputs"])
            self.assertEqual((copied / "source/rtl-optimization/baseline/design.md").read_text(), doc.read_text())
            self.assertEqual((template / "reference.v").read_text(), "module cpu_top; endmodule\n")

    def test_mapping_and_routed_proof_use_original_contract_and_library(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template"
            template.mkdir()
            manifest_path, manifest = project_fixture(template)
            manifest["inputs"].append("mapped.v")
            (template / "mapped.v").write_text("original mapped netlist")
            write_document(manifest_path, manifest)
            logical = root / "logical.v"
            logical.write_text("module top(input a, output y); assign y=a; endmodule")
            analysis = {"directory": str(root / "native"), "metrics": {"area_um2": 1}}
            project = {"design": "top", "mapping_library": "cells.lib", "netlist": "mapped.v"}

            def mapping(command, work, name, **kwargs):
                self.assertEqual(name, "mapping")
                self.assertIn("--as=6442450944", command)
                self.assertEqual(kwargs["expected"], ("mapped.v",))
                (work / "mapped.v").write_text("new mapped netlist")

            with (
                patch(f"{BACKEND}.shutil.which", side_effect=lambda name: "/tools/" + name),
                patch(f"{BACKEND}.run_native", side_effect=mapping),
                patch(
                    f"{BACKEND}.prove_equivalence",
                    return_value={
                        "status": "passed",
                        "candidate_sha256": "mapped",
                        "reference_sha256": "mapped",
                        "libraries_sha256": {"cells.lib": "locked"},
                    },
                ) as prove,
                patch(
                    f"{BACKEND}._run_physical_optimization",
                    return_value={"best": analysis, "output": str(root / "native")},
                ) as replay,
            ):
                result = measure_rtl(object(), project, template, logical, root / "experiment")
            self.assertEqual(prove.call_count, 2)
            self.assertEqual(prove.call_args_list[0].args[0], logical)
            self.assertEqual(prove.call_args_list[1].args[0], root / "experiment/mapping/mapped.v")
            self.assertEqual(prove.call_args_list[1].args[1], root / "native/pd-export.v")
            self.assertTrue(prove.call_args.kwargs["ports_only"])
            self.assertEqual(replay.call_args.args[-3:], (False, 1, None))
            self.assertEqual(result["final_proof"]["status"], "passed")
            self.assertEqual(result["project"], str(root / "experiment/project/project.json"))
            self.assertEqual((template / "mapped.v").read_text(), "original mapped netlist")
            self.assertEqual((root / "experiment/project/constraints.sdc").read_text(), "fixture\n")
            self.assertIn("clean -purge", (root / "experiment/mapping/map.ys").read_text())

    def test_routed_proof_must_bind_the_same_mapped_checkpoint_and_libraries(self):
        for changed in ("netlist", "library"):
            with self.subTest(changed=changed), TemporaryDirectory() as directory:
                root = Path(directory)
                template = root / "template"
                template.mkdir()
                path, manifest = project_fixture(template)
                manifest["inputs"].append("mapped.v")
                (template / "mapped.v").write_text("mapped input")
                write_document(path, manifest)
                logical = root / "logical.v"
                logical.write_text("logical input")
                project = {"design": "top", "mapping_library": "cells.lib", "netlist": "mapped.v"}
                first = {"status": "passed", "candidate_sha256": "mapped", "libraries_sha256": {"cells.lib": "locked"}}
                last = {"status": "passed", "reference_sha256": "mapped", "libraries_sha256": {"cells.lib": "locked"}}
                if changed == "netlist":
                    last["reference_sha256"] = "different"
                else:
                    last["libraries_sha256"] = {"cells.lib": "different"}

                def mapping(logical, library, project, workspace, sky130):
                    workspace.mkdir()
                    (workspace / "mapped.v").write_text("mapped output")

                with (
                    patch(f"{BACKEND}._map_netlist", side_effect=mapping),
                    patch(f"{BACKEND}.prove_equivalence", side_effect=[first, last]),
                    patch(
                        f"{BACKEND}._run_physical_optimization",
                        return_value={"best": {"directory": str(root / "native")}, "output": str(root / "native")},
                    ),
                    self.assertRaisesRegex(ValueError, "proof chain changed"),
                ):
                    measure_rtl(object(), project, template, logical, root / "experiment")

    def test_failed_mapping_proof_prevents_physical_execution(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template"
            template.mkdir()
            path, manifest = project_fixture(template)
            manifest["inputs"].append("mapped.v")
            (template / "mapped.v").write_text("fixture")
            write_document(path, manifest)
            logical = root / "logical.v"
            logical.write_text("module top; endmodule")
            with (
                patch(f"{BACKEND}.shutil.which", return_value="fixture-tool"),
                patch(f"{BACKEND}.run_native"),
                patch(f"{BACKEND}.prove_equivalence", side_effect=ValueError("mapping differs")),
                patch(f"{BACKEND}._run_physical_optimization") as replay,
                self.assertRaisesRegex(ValueError, "mapping differs"),
            ):
                measure_rtl(
                    object(), {"mapping_library": "cells.lib", "design": "top"}, template, logical, root / "candidate"
                )
            replay.assert_not_called()

    def test_frozen_physical_inputs_have_digest_bound_copies(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, _ = project_fixture(root)
            frozen = root / "frozen"
            hashes = freeze_physical_project(path, frozen)
            self.assertIn("constraints.sdc", hashes)
            (root / "constraints.sdc").write_text("changed original")
            self.assertEqual((frozen / "constraints.sdc").read_text(), "fixture\n")
