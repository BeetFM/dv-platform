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
from dv_platform.generators import CocotbGenerator, GeneratorRegistry


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
        self.assertIn("Clock(clock, 10, units='ns')", artifact.content)
        self.assertIn("FIFO increments when enable is asserted.", artifact.content)


if __name__ == "__main__":
    unittest.main()
