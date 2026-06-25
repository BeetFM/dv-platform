import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.rtl import RTL_FACTS_SCHEMA_VERSION, normalize_verilator_xml, read_normalized_rtl_facts, write_normalized_rtl_facts
from dv_platform.core.config import default_config


FIXTURES = Path(__file__).parent / "fixtures"


class RTLAnalysisTests(unittest.TestCase):
    def test_normalize_verilator_xml_fixture_extracts_module_ports_and_evidence(self) -> None:
        xml_path = FIXTURES / "verilator" / "simple_counter" / "Vsimple_counter.xml"

        modules = normalize_verilator_xml((xml_path,))

        self.assertEqual(len(modules), 1)
        module = modules[0]
        self.assertEqual(module.name, "simple_counter")
        self.assertEqual(module.ports, ("clk", "rst_n", "enable_i", "count_o"))
        self.assertEqual(module.parameters, ("WIDTH",))
        self.assertEqual(module.clocks, ("clk",))
        self.assertEqual(module.resets, ("rst_n",))
        self.assertEqual(module.instances, ("u_limit:limit_checker",))
        self.assertEqual(module.continuous_assignments, ("contassign:@a,7,30,7,37",))
        self.assertEqual(module.procedural_blocks, ("alwaysff:@a,9,5,14,8",))
        self.assertEqual(module.assertions, ("assert:@a,12,13,12,32",))
        self.assertEqual(module.covers, ("cover:@a,13,13,13,31",))
        self.assertEqual(module.ast_refs[0].source_id, str(xml_path))
        self.assertEqual(module.ast_refs[0].locator, "module:simple_counter@a,1,1,15,10")
        self.assertIn(
            "port:simple_counter.clk@a,4,17,4,20",
            tuple(ref.locator for ref in module.ast_refs),
        )
        self.assertIn(
            "parameter:simple_counter.WIDTH@a,2,19,2,24",
            tuple(ref.locator for ref in module.ast_refs),
        )
        self.assertIn(
            "instance:simple_counter.u_limit@a,8,5,8,17",
            tuple(ref.locator for ref in module.ast_refs),
        )

    def test_normalize_verilator_xml_extracts_module_ports_and_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vfifo.xml"
            xml_path.write_text(
                """
<verilator_xml>
  <netlist>
    <module name="fifo">
      <var name="clk" dir="input" />
      <var name="rst_n" dir="input" />
      <var name="data_i" dir="input" />
      <var name="data_o" dir="output" />
    </module>
  </netlist>
</verilator_xml>
""".strip(),
                encoding="utf-8",
            )

            modules = normalize_verilator_xml((xml_path,))

            self.assertEqual(len(modules), 1)
            module = modules[0]
            self.assertEqual(module.name, "fifo")
            self.assertEqual(module.ports, ("clk", "rst_n", "data_i", "data_o"))
            self.assertEqual(module.clocks, ("clk",))
            self.assertEqual(module.resets, ("rst_n",))
            self.assertEqual(module.ast_refs[0].locator, "module:fifo")

    def test_write_normalized_rtl_facts_persists_modules(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            xml_path = repo / "Vtop.xml"
            xml_path.write_text(
                '<verilator_xml><module name="top"><var name="clk" dir="input" /></module></verilator_xml>',
                encoding="utf-8",
            )
            modules = normalize_verilator_xml((xml_path,))

            facts_path = write_normalized_rtl_facts(default_config(repo), modules)

            payload = json.loads(facts_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], RTL_FACTS_SCHEMA_VERSION)
            self.assertEqual(payload["min_reader_schema_version"], 1)
            self.assertEqual(payload["modules"][0]["name"], "top")
            self.assertEqual(payload["modules"][0]["clocks"], ["clk"])
            self.assertEqual(payload["modules"][0]["continuous_assignments"], [])
            self.assertEqual(payload["modules"][0]["procedural_blocks"], [])

    def test_read_normalized_rtl_facts_round_trips_modules(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            modules = normalize_verilator_xml((FIXTURES / "verilator" / "simple_counter" / "Vsimple_counter.xml",))

            write_normalized_rtl_facts(config, modules, "Verilator test")
            loaded = read_normalized_rtl_facts(config)

            self.assertEqual(loaded, modules)


if __name__ == "__main__":
    unittest.main()
