from pathlib import Path
import unittest

from dv_platform.core.models import (
    ArtifactKind,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators import CocotbGenerator, FormalGenerator, GeneratorRegistry


class DummyBackend:
    target = VerificationTarget.COCOTB

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        return [
            GeneratedArtifact(
                path=Path("tests/cocotb/test_fifo.py"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content="# generated\n",
                source_plan_module=plan.module,
            )
        ]


class GeneratorRegistryTests(unittest.TestCase):
    def test_registry_routes_generation_by_target(self) -> None:
        registry = GeneratorRegistry()
        registry.register(DummyBackend())
        plan = VerificationPlan(module="fifo", targets=(VerificationTarget.COCOTB,))

        artifacts = registry.generate(plan)

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].source_plan_module, "fifo")

    def test_missing_backend_raises_lookup_error(self) -> None:
        registry = GeneratorRegistry()
        plan = VerificationPlan(module="fifo", targets=(VerificationTarget.UVM,))

        with self.assertRaises(LookupError):
            registry.generate(plan)


class CocotbGeneratorTests(unittest.TestCase):
    def test_cocotb_generator_emits_smoke_test_artifact(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vfifo.xml", "module:fifo")
        plan = VerificationPlan(
            module="fifo",
            targets=(VerificationTarget.COCOTB,),
            requirements=("FIFO increments when enable is asserted.",),
            claims=(VerificationClaim("fifo:clock", "fifo", "clock exists", evidence_refs=(ref,)),),
            checks=("Drive declared clock inputs with stable periods.",),
        )

        artifacts = CocotbGenerator().generate(plan)

        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertEqual(artifact.path, Path("test_fifo.py"))
        self.assertEqual(artifact.kind, ArtifactKind.TESTBENCH)
        self.assertEqual(artifact.target, VerificationTarget.COCOTB)
        self.assertEqual(artifact.source_plan_module, "fifo")
        self.assertEqual(artifact.provenance_refs, (ref,))
        self.assertIn("@cocotb.test()", artifact.content)
        self.assertIn("Clock(clock, 10, unit='ns')", artifact.content)
        self.assertIn("FIFO increments when enable is asserted.", artifact.content)

    def test_cocotb_generator_uses_port_evidence_for_reset_and_inputs(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk@a,4,17,4,20")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n@a,5,17,5,22")
        enable_ref = EvidenceRef(
            EvidenceKind.VERILATOR_AST,
            "Vsimple_counter.xml",
            "port:simple_counter.enable_i@a,6,17,6,25",
        )
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o@a,7,30,7,37")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.COCOTB,),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref, enable_ref),
                ),
            ),
        )

        artifact = CocotbGenerator().generate(plan)[0]

        self.assertEqual(artifact.provenance_refs, (clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("clock = _maybe_signal(dut, 'clk')", artifact.content)
        self.assertIn("reset = _maybe_signal(dut, 'rst_n')", artifact.content)
        self.assertIn("reset.value = 0", artifact.content)
        self.assertIn("reset.value = 1", artifact.content)
        self.assertIn("for name in ('enable_i',):", artifact.content)
        self.assertIn("_drive_if_present(dut, name, 1)", artifact.content)
        self.assertIn("for name in ('count_o',):", artifact.content)
        self.assertIn("_assert_resolvable(dut, name)", artifact.content)


class FormalGeneratorTests(unittest.TestCase):
    def test_formal_generator_emits_harness_and_sby_artifacts(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk@a,4,17,4,20")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n@a,5,17,5,22")
        enable_ref = EvidenceRef(
            EvidenceKind.VERILATOR_AST,
            "Vsimple_counter.xml",
            "port:simple_counter.enable_i@a,6,17,6,25",
        )
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o@a,7,30,7,37")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.FORMAL,),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref, enable_ref),
                ),
            ),
        )

        artifacts = FormalGenerator().generate(plan)

        self.assertEqual(len(artifacts), 2)
        harness, sby = artifacts
        self.assertEqual(harness.path, Path("formal_simple_counter.sv"))
        self.assertEqual(harness.kind, ArtifactKind.FORMAL_HARNESS)
        self.assertEqual(harness.target, VerificationTarget.FORMAL)
        self.assertEqual(harness.provenance_refs, (clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("module formal_simple_counter;", harness.content)
        self.assertIn("(* gclk *) reg clk;", harness.content)
        self.assertNotIn("clk = $anyseq", harness.content)
        self.assertIn("simple_counter dut", harness.content)
        self.assertIn(".enable_i(enable_i)", harness.content)
        self.assertIn(".count_o()", harness.content)
        self.assertIn("assume(rst_n == 1'b0);", harness.content)
        self.assertIn("cover(rst_n == 1'b1 && enable_i);", harness.content)
        self.assertEqual(sby.path, Path("simple_counter.sby"))
        self.assertEqual(sby.kind, ArtifactKind.RUN_SCRIPT)
        self.assertIn("prep -top formal_simple_counter", sby.content)


if __name__ == "__main__":
    unittest.main()
