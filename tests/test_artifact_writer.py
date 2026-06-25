import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.core.config import default_config
from dv_platform.core.models import ArtifactKind, EvidenceKind, EvidenceRef, GeneratedArtifact, VerificationTarget
from dv_platform.generators import write_generated_artifacts


class ArtifactWriterTests(unittest.TestCase):
    def test_write_generated_artifacts_uses_stage6_layout_and_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="# generated\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )

            result = write_generated_artifacts(config, (artifact,))

            expected_artifact = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo" / "test_fifo.py"
            expected_manifest = expected_artifact.parent / "provenance.json"
            self.assertEqual(result.artifact_paths, (expected_artifact,))
            self.assertEqual(result.provenance_paths, (expected_manifest,))
            self.assertEqual(expected_artifact.read_text(encoding="utf-8"), "# generated\n")

            manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["module"], "fifo")
            self.assertEqual(manifest["target"], "cocotb")
            self.assertEqual(manifest["artifacts"][0]["provenance_refs"][0]["locator"], "module:fifo")

    def test_write_generated_artifacts_rejects_path_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("../test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="@cocotb.test()\nasync def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )

            with self.assertRaisesRegex(ValueError, "relative"):
                write_generated_artifacts(config, (artifact,))

    def test_write_generated_artifacts_rejects_invalid_cocotb_syntax(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="def broken(:\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )

            with self.assertRaisesRegex(ValueError, "invalid syntax"):
                write_generated_artifacts(config, (artifact,))

    def test_write_generated_artifacts_requires_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="@cocotb.test()\nasync def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
            )

            with self.assertRaisesRegex(ValueError, "no provenance"):
                write_generated_artifacts(config, (artifact,))

    def test_write_generated_artifacts_uses_formal_layout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "module:simple_counter")
            artifact = GeneratedArtifact(
                path=Path("formal_simple_counter.sv"),
                kind=ArtifactKind.FORMAL_HARNESS,
                target=VerificationTarget.FORMAL,
                content="module formal_simple_counter; endmodule\n",
                source_plan_module="simple_counter",
                provenance_refs=(ref,),
            )

            result = write_generated_artifacts(config, (artifact,))

            expected_artifact = repo / "generated" / "dv-platform" / "formal" / "modules" / "simple_counter" / "formal_simple_counter.sv"
            expected_manifest = expected_artifact.parent / "provenance.json"
            self.assertEqual(result.artifact_paths, (expected_artifact,))
            self.assertEqual(result.provenance_paths, (expected_manifest,))
            manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["target"], "formal")


if __name__ == "__main__":
    unittest.main()
