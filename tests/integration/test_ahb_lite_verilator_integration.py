import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.rtl import normalize_verilator_xml, read_normalized_rtl_facts, write_normalized_rtl_facts
from dv_platform.core.config import default_config
from dv_platform.core.models import VerificationTarget


class AhbLiteVerilatorIntegrationTests(unittest.TestCase):
    def test_normalized_facts_and_plan_retain_ahb_lite(self) -> None:
        xml = """<verilator_xml><netlist><module name="ahb" origName="ahb">
        <var name="hclk" dir="input"/><var name="hresetn" dir="input"/>
        <var name="haddr" dir="input"/><var name="htrans" dir="input"/><var name="hwrite" dir="input"/>
        <var name="hsel" dir="input"/><var name="hready" dir="input"/><var name="hwdata" dir="input"/>
        <var name="hrdata" dir="output"/><var name="hreadyout" dir="output"/><var name="hresp" dir="output"/>
        </module></netlist></verilator_xml>"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "Vahb.xml"
            xml_path.write_text(xml, encoding="utf-8")
            config = default_config(root)
            modules = normalize_verilator_xml((xml_path,))
            self.assertEqual(modules[0].protocol_models[0].name, "AHB-Lite")
            self.assertEqual(modules[0].protocol_models[0].clock_domain, "hclk")
            self.assertEqual(modules[0].protocol_models[0].reset_domain, "hresetn")
            write_normalized_rtl_facts(config, modules, "Verilator 5.0")
            loaded = read_normalized_rtl_facts(config)
            plan = create_initial_plan(loaded[0], (VerificationTarget.SYSTEMVERILOG,))
            self.assertEqual(plan.protocol_models[0].name, "AHB-Lite")
            self.assertTrue(any("AHB-Lite" in check for check in plan.checks))
            write_plan_outputs(config, (plan,))
            self.assertEqual(
                read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0].protocol_models,
                plan.protocol_models,
            )


if __name__ == "__main__":
    unittest.main()
