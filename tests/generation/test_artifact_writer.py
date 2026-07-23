import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    ArtifactTrace,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    RTLParameter,
    VerificationTarget,
)
from dv_platform.generators import write_generated_artifacts
from dv_platform.generators.artifacts import validate_generated_directory


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
                elaborated_parameters=(RTLParameter("WIDTH", "32'hc", width=32),),
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )

            result = write_generated_artifacts(config, (artifact,))

            expected_artifact = (
                repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo" / "test_fifo.py"
            )
            expected_manifest = expected_artifact.parent / "provenance.json"
            self.assertEqual(
                result.artifact_paths,
                (expected_artifact, expected_artifact.parent / "execution-manifest.json"),
            )
            self.assertEqual(result.provenance_paths, (expected_manifest,))
            self.assertEqual(expected_artifact.read_text(encoding="utf-8"), "# generated\n")

            manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["module"], "fifo")
            self.assertEqual(manifest["target"], "cocotb")
            self.assertEqual(manifest["artifacts"][0]["provenance_refs"][0]["locator"], "module:fifo")
            self.assertEqual(manifest["artifacts"][0]["quality_requirements"][0]["requirement_id"], "test")
            execution = json.loads((expected_artifact.parent / "execution-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(execution["elaborated_parameters"], [{"name": "WIDTH", "value": "32'hc"}])

    def test_write_generated_artifacts_redacts_validator_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(default_config(repo), redact_patterns=(r"token=[^ ]+",))
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="# generated\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )

            with patch(
                "dv_platform.generators.artifacts._validate_module_with_tool",
                return_value={
                    "required": True,
                    "status": "passed",
                    "validator": "company",
                    "command": ["company-validator", "token=secret"],
                },
            ):
                result = write_generated_artifacts(config, (artifact,))

            payload = result.provenance_paths[0].read_text(encoding="utf-8")
            self.assertIn("[REDACTED]", payload)
            self.assertNotIn("secret", payload)

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

    def test_write_generated_artifacts_rejects_module_directory_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            artifact = GeneratedArtifact(
                path=Path("report.txt"),
                kind=ArtifactKind.REPORT,
                target=VerificationTarget.SYSTEMVERILOG,
                content="must stay contained\n",
                source_plan_module="../../outside",
                provenance_refs=(EvidenceRef(EvidenceKind.VERILATOR_AST, "Vbad.xml", "module:bad"),),
            )

            with self.assertRaisesRegex(ValueError, "path separators"):
                write_generated_artifacts(config, (artifact,))

            self.assertFalse((repo / "outside" / "report.txt").exists())

    def test_write_generated_artifacts_replaces_module_and_removes_stale_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            old = GeneratedArtifact(
                path=Path("old.txt"),
                kind=ArtifactKind.REPORT,
                target=VerificationTarget.SYSTEMVERILOG,
                content="old\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )
            new = GeneratedArtifact(
                path=Path("new.txt"),
                kind=ArtifactKind.REPORT,
                target=VerificationTarget.SYSTEMVERILOG,
                content="new\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )

            write_generated_artifacts(config, (old,))
            result = write_generated_artifacts(config, (new,))

            self.assertFalse((result.artifact_paths[0].parent / "old.txt").exists())
            self.assertEqual(result.artifact_paths[0].read_text(encoding="utf-8"), "new\n")
            manifest = json.loads(result.provenance_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(len(manifest["artifacts"][0]["content_sha256"]), 64)

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
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )

            with self.assertRaisesRegex(ValueError, "invalid syntax"):
                write_generated_artifacts(config, (artifact,))

    def test_write_generated_artifacts_rejects_executable_without_quality_requirements(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="@cocotb.test()\nasync def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
            )

            with self.assertRaisesRegex(ValueError, "no quality requirements"):
                write_generated_artifacts(config, (artifact,))

    def test_write_generated_artifacts_rejects_executable_without_plan_traceability(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="async def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
            )

            with self.assertRaisesRegex(ValueError, "no plan traceability"):
                write_generated_artifacts(config, (artifact,))

    def test_execution_manifest_rejects_rtl_changed_after_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            source = repo / "rtl" / "fifo.sv"
            source.parent.mkdir()
            source.write_text("module fifo; endmodule\n", encoding="utf-8")
            project_manifest = config.work_dir / "project-manifest.json"
            project_manifest.parent.mkdir(parents=True)
            project_manifest.write_text(
                json.dumps(
                    {
                        "hdl_files": [{"path": str(source), "language": "systemverilog", "library": None}],
                        "include_paths": [],
                        "defines": [],
                        "top_modules": ["fifo"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="async def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                elaborated_parameters=(RTLParameter("WIDTH", "32'hc", width=32),),
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )
            result = write_generated_artifacts(config, (artifact,))
            generated_dir = result.artifact_paths[0].parent
            validate_generated_directory(VerificationTarget.COCOTB, "fifo", generated_dir)

            source.write_text("module fifo; wire changed; endmodule\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "input changed after generation"):
                validate_generated_directory(VerificationTarget.COCOTB, "fifo", generated_dir)

    def test_execution_manifest_requires_current_project_binding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="async def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                elaborated_parameters=(RTLParameter("WIDTH", "32'hc", width=32),),
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )
            result = write_generated_artifacts(config, (artifact,))

            with self.assertRaisesRegex(ValueError, "not bound to a project manifest"):
                validate_generated_directory(VerificationTarget.COCOTB, "fifo", result.artifact_paths[0].parent)

    def test_strict_generation_requires_project_manifest_binding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = replace(default_config(Path(temp_dir)), strict=True)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="async def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )

            with self.assertRaisesRegex(ValueError, "current project manifest"):
                write_generated_artifacts(config, (artifact,))

    def test_execution_manifest_trace_ids_must_match_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            source = repo / "rtl" / "fifo.sv"
            source.parent.mkdir()
            source.write_text("module fifo; endmodule\n", encoding="utf-8")
            project_manifest = config.work_dir / "project-manifest.json"
            project_manifest.parent.mkdir(parents=True)
            project_manifest.write_text(
                json.dumps({"hdl_files": [{"path": str(source), "language": "systemverilog"}]}) + "\n",
                encoding="utf-8",
            )
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="async def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "fifo", "test_fifo_smoke"),),
            )
            result = write_generated_artifacts(config, (artifact,))
            generated_dir = result.artifact_paths[0].parent
            execution_path = generated_dir / "execution-manifest.json"
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["generated_files"][0]["trace_ids"] = ["fifo:wrong-trace"]
            execution_path.write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            provenance_path = generated_dir / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            manifest_item = next(item for item in provenance["artifacts"] if item["path"] == execution_path.name)
            content = execution_path.read_bytes()
            manifest_item["size_bytes"] = len(content)
            manifest_item["content_sha256"] = hashlib.sha256(content).hexdigest()
            provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "metadata does not match provenance"):
                validate_generated_directory(VerificationTarget.COCOTB, "fifo", generated_dir)

    def test_write_generated_artifacts_rejects_failed_quality_requirements(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
            artifact = GeneratedArtifact(
                path=Path("test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.COCOTB,
                content="@cocotb.test()\nasync def test_fifo_smoke(dut):\n    assert dut is not None\n",
                source_plan_module="fifo",
                provenance_refs=(ref,),
                quality_requirements=(
                    ArtifactQualityRequirement(
                        "structured_ports", "needs ports", False, "plan has no structured ports"
                    ),
                ),
            )

            with self.assertRaisesRegex(ValueError, "failed quality gate"):
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
                quality_requirements=(_quality_requirement(),),
                traceability=(_trace(ref, "simple_counter", "formal_simple_counter_properties"),),
            )

            result = write_generated_artifacts(config, (artifact,))

            expected_artifact = (
                repo
                / "generated"
                / "dv-platform"
                / "formal"
                / "modules"
                / "simple_counter"
                / "formal_simple_counter.sv"
            )
            expected_manifest = expected_artifact.parent / "provenance.json"
            self.assertEqual(
                result.artifact_paths,
                (expected_artifact, expected_artifact.parent / "execution-manifest.json"),
            )
            self.assertEqual(result.provenance_paths, (expected_manifest,))
            manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["target"], "formal")


def _quality_requirement() -> ArtifactQualityRequirement:
    return ArtifactQualityRequirement("test", "test quality gate", True)


def _trace(ref: EvidenceRef, module: str, symbol: str) -> ArtifactTrace:
    return ArtifactTrace(
        trace_id=f"{module}:{symbol}",
        generated_symbol=symbol,
        check_indexes=(1,),
        evidence_refs=(ref,),
    )


if __name__ == "__main__":
    unittest.main()
