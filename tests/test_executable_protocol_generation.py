import unittest
from dataclasses import replace

from dv_platform.agent.protocols import RegisterModel, ahb_lite_model
from dv_platform.core.models import EvidenceKind, EvidenceRef, RTLPort, VerificationPlan, VerificationTarget
from dv_platform.generators.artifacts import validate_generated_artifact
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.systemverilog import SystemVerilogGenerator
from dv_platform.generators.uvm import UvmGenerator
from dv_platform.generators.verilog import VerilogGenerator
from dv_platform.generators.vhdl import VhdlGenerator


class ExecutableProtocolGenerationTests(unittest.TestCase):
    def test_ahb_lite_and_register_accesses_are_executable_snippets(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vahb.xml", "module:ahb"),)
        model = ahb_lite_model(
            ((name, name) for name in ("haddr", "htrans", "hwrite", "hready", "hresp", "hsel", "hwdata", "hrdata")),
            evidence,
        )
        model = replace(
            model,
            clock_domain="hclk",
            signal_directions=tuple(
                (name, "input" if name in {"haddr", "htrans", "hwrite", "hready", "hsel", "hwdata"} else "output")
                for name, _ in model.signal_bindings
            ),
        )
        plan = VerificationPlan(
            "ahb",
            tuple(VerificationTarget),
            ports=tuple(
                RTLPort(name, "input" if direction == "input" else "output")
                for name, direction in {
                    "hclk": "input",
                    "haddr": "input",
                    "htrans": "input",
                    "hwrite": "input",
                    "hready": "input",
                    "hsel": "input",
                    "hwdata": "input",
                    "hrdata": "output",
                    "hresp": "output",
                }.items()
            ),
            protocol_models=(model,),
            register_models=(RegisterModel("CONTROL", 0, 32, source="configuration", evidence_refs=evidence),),
        )
        cocotb = CocotbGenerator().generate(plan)[0].content
        systemverilog = SystemVerilogGenerator().generate(plan)[0].content
        verilog = VerilogGenerator().generate(plan)[0].content
        vhdl = VhdlGenerator().generate(plan)[0].content
        self.assertIn("await _exercise_mapped_protocols", cocotb)
        self.assertIn("haddr", cocotb)
        self.assertIn("assert property", systemverilog)
        self.assertIn("haddr = 0", verilog)
        self.assertIn("wait until rising_edge", vhdl)

    def test_uvm_protocol_generation_fails_closed_without_validator(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "ahb"),)
        model = ahb_lite_model(
            tuple(
                (name, name) for name in ("haddr", "htrans", "hwrite", "hready", "hresp", "hsel", "hwdata", "hrdata")
            ),
            evidence,
        )
        plan = VerificationPlan(
            "ahb", (VerificationTarget.UVM,), ports=(RTLPort("hclk", "input"),), protocol_models=(model,)
        )
        artifact = UvmGenerator().generate(plan)[0]
        with self.assertRaisesRegex(ValueError, "quality gate"):
            validate_generated_artifact(artifact)


if __name__ == "__main__":
    unittest.main()
