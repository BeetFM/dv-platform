import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.rtl import (
    RTL_FACTS_SCHEMA_VERSION,
    classify_verilator_version,
    normalize_verilator_xml,
    read_normalized_rtl_facts,
    write_normalized_rtl_facts,
)
from dv_platform.core.config import default_config
from dv_platform.core.models import ProtocolProfile, VerificationTarget

FIXTURES = Path(__file__).parent / "fixtures"


class RTLAnalysisTests(unittest.TestCase):
    def test_verilator_compatibility_is_explicit_and_fail_closed(self) -> None:
        self.assertEqual(classify_verilator_version("Verilator 5.020")["status"], "supported")
        self.assertEqual(classify_verilator_version("Verilator 4.228")["status"], "unsupported")
        self.assertEqual(classify_verilator_version("Verilator 6.001")["status"], "unsupported")
        self.assertEqual(classify_verilator_version("unknown")["status"], "unknown")

    def test_normalize_verilator_xml_records_source_and_unsupported_case_semantics(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vdecoder.xml"
            xml_path.write_text(
                """<verilator_xml><files><file id="a" filename="rtl/decoder.sv"/></files><netlist>
                <module name="decoder" loc="a,1,1,8,10">
                  <var name="select_i" dir="input" loc="a,2,3,2,11"/>
                  <var name="data_o" dir="output" loc="a,3,3,3,9"/>
                  <alwayscomb loc="a,4,3,7,6"><case loc="a,5,5,6,8"><varref name="select_i"/></case></alwayscomb>
                </module></netlist></verilator_xml>""",
                encoding="utf-8",
            )

            module = normalize_verilator_xml((xml_path,))[0]

            self.assertEqual(module.source, Path("rtl/decoder.sv"))
            self.assertEqual(module.port_details[0].source_location, "a,2,3,2,11")
            self.assertEqual(tuple(feature.kind for feature in module.semantic_features), ("case_statement",))
            self.assertFalse(module.semantic_features[0].generation_supported)
            self.assertIn(
                "semantic-feature:decoder.case_statement@a,5,5,6,8",
                tuple(ref.locator for ref in module.ast_refs),
            )

    def test_normalize_verilator_xml_uses_sensitivity_for_nonstandard_clock_and_reset_names(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vcontrol.xml"
            xml_path.write_text(
                """<verilator_xml><netlist><module name="control" origName="control">
                <var name="phase" dir="input" dtype_id="1"/>
                <var name="clear_n" dir="input" dtype_id="1"/>
                <var name="result" dir="output" dtype_id="1"/>
                <always><sentree>
                  <senitem edgeType="POS"><varref name="phase" dtype_id="1"/></senitem>
                  <senitem edgeType="POS"><varref name="clear_n" dtype_id="1"/></senitem>
                </sentree><if><varref name="clear_n" dtype_id="1"/>
                  <assign><const name="1'h0"/><varref name="result"/></assign>
                </if></always>
                </module></netlist><typetable><basicdtype id="1"/></typetable></verilator_xml>""",
                encoding="utf-8",
            )

            module = normalize_verilator_xml((xml_path,))[0]

            self.assertEqual(module.clocks, ("phase",))
            self.assertEqual(module.clock_details[0].classification, "sensitivity")
            self.assertEqual(module.resets, ("clear_n",))
            self.assertFalse(module.reset_details[0].active_low)
            self.assertEqual(module.reset_details[0].classification, "sensitivity")

    def test_normalize_verilator_xml_extracts_expanded_elaboration_and_protocol_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vstream_top.xml"
            xml_path.write_text(
                """<verilator_xml><files><file id="a" filename="rtl/stream_top.sv"/></files><netlist>
                <module name="stream_top" origName="stream_top" loc="a,1,1,30,10">
                  <var name="WIDTH" param="true" dtype_id="2" loc="a,2,3,2,8"><const name="32'hc"/></var>
                  <var name="clk" dir="input" dtype_id="1" loc="a,4,3,4,6"/>
                  <var name="rst" dir="input" dtype_id="1" loc="a,5,3,5,6"/>
                  <var name="in_valid" dir="input" dtype_id="1" loc="a,6,3,6,11"/>
                  <var name="in_ready" dir="output" dtype_id="1" loc="a,7,3,7,11"/>
                  <var name="in_data" dir="input" dtype_id="3" loc="a,8,3,8,10"/>
                  <var name="out_valid" dir="output" dtype_id="1" loc="a,9,3,9,12"/>
                  <var name="out_ready" dir="input" dtype_id="1" loc="a,10,3,10,12"/>
                  <var name="out_data" dir="output" dtype_id="3" loc="a,11,3,11,11"/>
                  <var name="storage" dtype_id="4" loc="a,13,3,13,10"/>
                  <instance name="u_child" defName="stream_child__Wc" loc="a,14,3,14,10">
                    <port name="data" direction="in" loc="a,15,5,15,9"><varref name="in_data"/></port>
                  </instance>
                  <always loc="a,18,3,28,6"><sentree>
                    <senitem edgeType="POS"><varref name="clk"/></senitem>
                    <senitem edgeType="POS"><varref name="rst"/></senitem>
                  </sentree><if><varref name="rst"/><assigndly><const name="1'h0"/><varref name="out_valid"/></assigndly></if></always>
                </module>
                <module name="stream_child__Wc" origName="stream_child"/>
                </netlist><typetable>
                  <basicdtype id="1" name="logic"/><basicdtype id="2" name="int" left="31" right="0" signed="true"/>
                  <basicdtype id="3" name="logic" left="11" right="0"/>
                  <unpackarraydtype id="4" sub_dtype_id="3"><range><const name="32'sh0"/><const name="32'sh1"/></range></unpackarraydtype>
                </typetable></verilator_xml>""",
                encoding="utf-8",
            )

            modules = normalize_verilator_xml((xml_path,))
            module = next(item for item in modules if item.name == "stream_top")

            self.assertEqual(module.parameter_details[0].name, "WIDTH")
            self.assertEqual(module.parameter_details[0].default_value, "32'hc")
            self.assertEqual(module.parameter_details[0].width, 32)
            self.assertEqual(module.memories[0].name, "storage")
            self.assertEqual(module.memories[0].element_width, 12)
            self.assertEqual(module.memories[0].depth, 2)
            self.assertEqual(module.instance_details[0].module_name, "stream_child")
            self.assertEqual(module.instance_details[0].elaborated_module_name, "stream_child__Wc")
            self.assertEqual(module.instance_details[0].connections[0].signal_refs, ("in_data",))
            self.assertEqual(module.control_domains[0].clock, "clk")
            self.assertEqual(module.control_domains[0].reset, "rst")
            self.assertTrue(module.control_domains[0].asynchronous_reset)
            self.assertEqual(module.procedural_block_details[0].domain_id, "domain_1")
            self.assertEqual(
                tuple((protocol.name, protocol.role, protocol.data) for protocol in module.protocols),
                (("in", "sink", "in_data"), ("out", "source", "out_data")),
            )
            self.assertTrue(
                next(
                    feature for feature in module.semantic_features if feature.kind == "memory_or_unpacked_array"
                ).supports_target(VerificationTarget.COCOTB)
            )

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

    def test_normalize_verilator_xml_classifies_continuous_assignment_signal_refs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vassign.xml"
            xml_path.write_text(
                """
<verilator_xml>
  <netlist>
    <module name="assigner">
      <var name="data_i" dir="input" />
      <var name="enable_i" dir="input" />
      <var name="data_o" dir="output" />
      <contassign fl="a,4,3,4,22">
        <and>
          <varref name="data_i" />
          <varref name="enable_i" />
        </and>
        <varref name="data_o" />
      </contassign>
    </module>
  </netlist>
</verilator_xml>
""".strip(),
                encoding="utf-8",
            )

            module = normalize_verilator_xml((xml_path,))[0]

            self.assertEqual(len(module.assignment_details), 1)
            assignment = module.assignment_details[0]
            self.assertEqual(assignment.lhs_signals, ("data_o",))
            self.assertEqual(assignment.rhs_signals, ("data_i", "enable_i"))
            self.assertEqual(tuple(expression.kind for expression in assignment.expressions), ("and", "varref"))

    def test_normalize_verilator_xml_extracts_procedural_signal_refs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Valways.xml"
            xml_path.write_text(
                """
<verilator_xml>
  <netlist>
    <module name="seq">
      <var name="clk" dir="input" />
      <var name="rst_n" dir="input" />
      <var name="enable_i" dir="input" />
      <var name="count_o" dir="output" />
      <alwaysff fl="a,5,3,12,6">
        <sentree>
          <varref name="clk" />
        </sentree>
        <if>
          <varref name="rst_n" />
          <assign>
            <const value="0" />
            <varref name="count_o" />
          </assign>
          <if>
            <varref name="enable_i" />
            <assign>
              <add>
                <varref name="count_o" />
                <const value="1" />
              </add>
              <varref name="count_o" />
            </assign>
          </if>
        </if>
      </alwaysff>
    </module>
  </netlist>
</verilator_xml>
""".strip(),
                encoding="utf-8",
            )

            module = normalize_verilator_xml((xml_path,))[0]

            self.assertEqual(len(module.procedural_block_details), 1)
            block = module.procedural_block_details[0]
            self.assertEqual(block.kind, "alwaysff")
            self.assertEqual(block.signal_refs, ("clk", "rst_n", "count_o", "enable_i"))
            self.assertEqual(tuple(expression.kind for expression in block.expressions), ("sentree", "if"))
            self.assertEqual(len(block.patterns), 2)
            self.assertEqual(block.patterns[0].kind, "reset_to_constant")
            self.assertEqual(block.patterns[0].target, "count_o")
            self.assertEqual(block.patterns[0].control, "rst_n")
            self.assertEqual(block.patterns[0].value, "0")
            self.assertEqual(block.patterns[1].kind, "increment")
            self.assertEqual(block.patterns[1].target, "count_o")
            self.assertEqual(block.patterns[1].control, "enable_i")

    def test_normalize_verilator_xml_keeps_parameter_specializations_distinct(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vtop.xml"
            xml_path.write_text(
                """<verilator_xml><netlist>
                <module name="top" origName="top">
                  <instance name="u8" defName="worker__W8"/>
                  <instance name="u16" defName="worker__W10"/>
                </module>
                <module name="worker__W8" origName="worker">
                  <var name="WIDTH" param="true"><const name="32'h8"/></var>
                </module>
                <module name="worker__W10" origName="worker">
                  <var name="WIDTH" param="true"><const name="32'h10"/></var>
                </module>
                </netlist></verilator_xml>""",
                encoding="utf-8",
            )

            modules = normalize_verilator_xml((xml_path,))
            workers = tuple(module for module in modules if module.original_name == "worker")
            top = next(module for module in modules if module.name == "top")

            self.assertEqual(len(workers), 2)
            self.assertEqual(len({module.name for module in workers}), 2)
            self.assertTrue(all(module.name.startswith("worker__spec_") for module in workers))
            self.assertEqual({module.elaborated_name for module in workers}, {"worker__W8", "worker__W10"})
            self.assertEqual(len({module.specialization_id for module in workers}), 2)
            self.assertEqual(
                {instance.plan_module_name for instance in top.instance_details},
                {module.name for module in workers},
            )
            self.assertEqual(
                {instance.parameter_bindings[0].value for instance in top.instance_details},
                {"32'h8", "32'h10"},
            )

    def test_normalize_verilator_xml_extracts_memory_types_generate_cdc_and_configured_protocol(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vadvanced.xml"
            xml_path.write_text(
                """<verilator_xml><netlist><module name="advanced" origName="advanced">
                <var name="clk_a" dir="input" dtype_id="1"/><var name="clk_b" dir="input" dtype_id="1"/>
                <var name="data_i" dir="input" dtype_id="2"/><var name="addr" dir="input" dtype_id="3"/>
                <var name="write_en" dir="input" dtype_id="1"/><var name="data_o" dir="output" dtype_id="2"/>
                <var name="cmd_req" dir="input" dtype_id="1"/><var name="cmd_ack" dir="output" dtype_id="1"/>
                <var name="cmd_payload" dir="input" dtype_id="2"/><var name="packet" dtype_id="5"/>
                <var name="storage" dtype_id="4"/><var name="crossing" dtype_id="1"/>
                <var name="sync1" dtype_id="1"/><var name="sync2" dtype_id="1"/>
                <begin name="lanes"><instance name="lanes.0.u_lane" defName="lane"/></begin>
                <alwaysff name="launch"><sentree><senitem edgeType="POS"><varref name="clk_a"/></senitem></sentree>
                  <assigndly><varref name="data_i"/><varref name="crossing"/></assigndly>
                </alwaysff>
                <alwaysff name="capture"><sentree><senitem edgeType="POS"><varref name="clk_b"/></senitem></sentree>
                  <assigndly><varref name="crossing"/><varref name="sync1"/></assigndly>
                  <assigndly><varref name="sync1"/><varref name="sync2"/></assigndly>
                  <if><varref name="write_en"/><assigndly><varref name="data_i"/>
                    <arraysel><varref name="storage"/><varref name="addr"/></arraysel>
                  </assigndly></if>
                </alwaysff>
                <contassign><arraysel><varref name="storage"/><varref name="addr"/></arraysel><varref name="data_o"/></contassign>
                </module><module name="lane" origName="lane"/></netlist><typetable>
                <basicdtype id="1" name="logic"/><basicdtype id="2" name="logic" left="7" right="0"/>
                <basicdtype id="3" name="logic" left="1" right="0"/>
                <unpackarraydtype id="4" sub_dtype_id="2"><range><const name="0"/><const name="3"/></range></unpackarraydtype>
                <structdtype id="5" name="packet_t"><memberdtype name="tag"/><memberdtype name="payload"/></structdtype>
                </typetable></verilator_xml>""",
                encoding="utf-8",
            )
            profile = ProtocolProfile(
                name="command",
                kind="req_ack",
                valid_suffix="_req",
                ready_suffix="_ack",
                data_suffixes=("_payload",),
            )

            module = next(
                module for module in normalize_verilator_xml((xml_path,), (profile,)) if module.name == "advanced"
            )

            self.assertEqual(module.memories[0].address_width, 2)
            self.assertEqual(module.memories[0].read_during_write, "unknown")
            self.assertEqual({access.kind for access in module.memory_accesses}, {"read", "write"})
            write = next(access for access in module.memory_accesses if access.kind == "write")
            self.assertEqual(write.address_signals, ("addr",))
            self.assertEqual(write.data_signals, ("data_i",))
            self.assertEqual(write.enable_signals, ("write_en",))
            self.assertTrue(write.synchronous)
            self.assertEqual(
                next(item for item in module.type_details if item.type_id == "5").members, ("tag", "payload")
            )
            self.assertEqual(module.generate_scopes[0].instance_names, ("lanes.0.u_lane",))
            path = next(path for path in module.cdc_paths if path.signal == "crossing")
            self.assertEqual(path.classification, "synchronizer")
            self.assertEqual(path.synchronizer_stages, 2)
            self.assertTrue(path.safe)
            protocol = next(protocol for protocol in module.protocols if protocol.profile == "command")
            self.assertEqual(protocol.kind, "req_ack")
            self.assertEqual(
                protocol.signal_map, (("request", "cmd_req"), ("acknowledge", "cmd_ack"), ("data", "cmd_payload"))
            )

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
