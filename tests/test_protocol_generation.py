import unittest

from dv_platform.agent.protocols import ahb_lite_model, axi4_lite_model
from dv_platform.core.models import EvidenceKind, EvidenceRef, RTLPort, VerificationPlan, VerificationTarget
from dv_platform.generators import (
    CocotbGenerator,
    FormalGenerator,
    SystemVerilogGenerator,
    UvmGenerator,
    VerilogGenerator,
    VhdlGenerator,
)


class ProtocolGenerationTests(unittest.TestCase):
    def test_every_target_receives_protocol_mapping_and_trace(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "axi"),)
        plan = VerificationPlan(
            "top",
            tuple(VerificationTarget),
            ports=(RTLPort("clk", "input"), RTLPort("awvalid", "input"), RTLPort("awready", "output")),
            protocol_models=(axi4_lite_model((("awvalid", "awvalid"), ("awready", "awready")), evidence),),
        )
        generators = (
            CocotbGenerator(),
            SystemVerilogGenerator(),
            VerilogGenerator(),
            VhdlGenerator(),
            UvmGenerator(),
            FormalGenerator(),
        )
        for generator in generators:
            with self.subTest(target=generator.target):
                artifacts = generator.generate(plan)
                self.assertTrue(artifacts)
                self.assertTrue(all("protocol=AXI4-Lite" in artifact.content for artifact in artifacts))
                self.assertTrue(
                    all("AXI4-Lite" in trace.protocol_ids for artifact in artifacts for trace in artifact.traceability)
                )

    def test_every_target_receives_ahb_lite_mapping_and_trace(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "ahb"),)
        plan = VerificationPlan(
            "ahb_top",
            tuple(VerificationTarget),
            ports=(RTLPort("hclk", "input"), RTLPort("haddr", "input"), RTLPort("hready", "input")),
            protocol_models=(
                ahb_lite_model(
                    (
                        ("haddr", "haddr"),
                        ("htrans", "htrans"),
                        ("hwrite", "hwrite"),
                        ("hready", "hready"),
                        ("hresp", "hresp"),
                        ("hsel", "hsel"),
                        ("hwdata", "hwdata"),
                        ("hrdata", "hrdata"),
                    ),
                    evidence,
                ),
            ),
        )
        generators = (
            CocotbGenerator(),
            SystemVerilogGenerator(),
            VerilogGenerator(),
            VhdlGenerator(),
            UvmGenerator(),
            FormalGenerator(),
        )
        for generator in generators:
            with self.subTest(target=generator.target):
                artifacts = generator.generate(plan)
                self.assertTrue(all("protocol=AHB-Lite" in artifact.content for artifact in artifacts))
                self.assertTrue(
                    all("AHB-Lite" in trace.protocol_ids for artifact in artifacts for trace in artifact.traceability)
                )


if __name__ == "__main__":
    unittest.main()
