from pathlib import Path
import unittest

from dv_platform.core.models import (
    ArtifactKind,
    GeneratedArtifact,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators import GeneratorRegistry


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


if __name__ == "__main__":
    unittest.main()
