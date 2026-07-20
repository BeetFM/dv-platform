import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.rtl import normalize_verilator_xml, read_normalized_rtl_facts, write_normalized_rtl_facts
from dv_platform.core.config import default_config
from dv_platform.core.models import VerificationTarget
from dv_platform.generators.systemverilog import SystemVerilogGenerator


class VerilatorProtocolIntegrationTests(unittest.TestCase):
    def test_normalized_verilator_ports_reach_plan_store_and_generator(self) -> None:
        xml = """<verilator_xml><netlist><module name="axi" origName="axi">
        <var name="aclk" dir="input"/><var name="aresetn" dir="input"/>
        <var name="awaddr" dir="input"/><var name="awvalid" dir="input"/><var name="awready" dir="output"/>
        <var name="wdata" dir="input"/><var name="wvalid" dir="input"/><var name="wready" dir="output"/>
        <var name="bresp" dir="output"/><var name="bvalid" dir="output"/><var name="bready" dir="input"/>
        <var name="araddr" dir="input"/><var name="arvalid" dir="input"/><var name="arready" dir="output"/>
        <var name="rdata" dir="output"/><var name="rresp" dir="output"/><var name="rvalid" dir="output"/><var name="rready" dir="input"/>
        </module></netlist></verilator_xml>"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "Vaxi.xml"
            xml_path.write_text(xml, encoding="utf-8")
            config = default_config(root)
            modules = normalize_verilator_xml((xml_path,))
            self.assertEqual([item.name for item in modules[0].protocol_models], ["AXI4-Lite"])
            self.assertEqual(modules[0].protocol_models[0].clock_domain, "aclk")
            self.assertEqual(modules[0].protocol_models[0].reset_domain, "aresetn")
            self.assertIn(("awaddr", "awaddr"), modules[0].protocol_models[0].signal_bindings)
            write_normalized_rtl_facts(config, modules, "Verilator 5.0")
            loaded = read_normalized_rtl_facts(config)
            plan = create_initial_plan(loaded[0], (VerificationTarget.SYSTEMVERILOG,))
            self.assertEqual([item.name for item in plan.protocol_models], ["AXI4-Lite"])
            write_plan_outputs(config, (plan,))
            persisted = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            self.assertEqual(persisted.protocol_models, plan.protocol_models)
            artifact = SystemVerilogGenerator().generate(persisted)[0]
            self.assertIn("protocol=AXI4-Lite", artifact.content)
            self.assertIn("AXI4-Lite", artifact.traceability[0].protocol_ids)


if __name__ == "__main__":
    unittest.main()
