from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.core.models import (
    ArtifactKind,
    EvidenceKind,
    EvidenceRef,
    GeneratedArtifact,
    RTLPort,
    VerificationBehavior,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators import (
    CocotbGenerator,
    FormalGenerator,
    GeneratorRegistry,
    SystemVerilogGenerator,
    UvmGenerator,
    VerilogGenerator,
    VhdlGenerator,
    load_generator_plugins,
)


class FakeEntryPoint:
    name = "dummy_cocotb"

    def load(self):
        return DummyBackend


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

    def test_load_generator_plugins_requires_explicit_enabled_name(self) -> None:
        registry = GeneratorRegistry()

        loaded = load_generator_plugins(registry, ("dummy_cocotb",), (FakeEntryPoint(),))

        self.assertEqual(loaded, ("dummy_cocotb",))
        self.assertIsInstance(registry.get(VerificationTarget.COCOTB), DummyBackend)

    def test_load_generator_plugins_rejects_missing_enabled_plugin(self) -> None:
        registry = GeneratorRegistry()

        with self.assertRaisesRegex(LookupError, "not found"):
            load_generator_plugins(registry, ("missing",), ())


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
            checks=(
                "Verify rst_n drives count_o to its documented reset value.",
                "Verify count_o increments when enable_i is asserted.",
                "Verify count_o remains stable when enable_i is inactive.",
            ),
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
        self.assertIn("_assert_signal_int(dut, 'count_o', 0)", artifact.content)
        self.assertIn("_drive_if_present(dut, 'enable_i', 1)", artifact.content)
        self.assertIn("assert after == before + 1", artifact.content)
        self.assertIn("_drive_if_present(dut, 'enable_i', 0)", artifact.content)
        self.assertIn("assert after == before", artifact.content)

    def test_cocotb_generator_uses_structured_behaviors_without_requirement_text(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        behavior_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "procedure:simple_counter.alwaysff")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.COCOTB,),
            behaviors=(
                VerificationBehavior(
                    behavior_id="simple_counter:behavior:1:1",
                    scope="simple_counter",
                    kind="reset_to_constant",
                    target="count_o",
                    control="rst_n",
                    value="0",
                    evidence_refs=(behavior_ref,),
                ),
                VerificationBehavior(
                    behavior_id="simple_counter:behavior:1:2",
                    scope="simple_counter",
                    kind="increment",
                    target="count_o",
                    control="enable_i",
                    source="count_o",
                    evidence_refs=(behavior_ref,),
                ),
            ),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        artifact = CocotbGenerator().generate(plan)[0]

        self.assertEqual(artifact.provenance_refs, (behavior_ref, clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("_assert_signal_int(dut, 'count_o', 0)", artifact.content)
        self.assertIn("_drive_if_present(dut, 'enable_i', 1)", artifact.content)
        self.assertIn("assert after == before + 1", artifact.content)

    def test_cocotb_generator_uses_structured_port_directions_without_suffixes(self) -> None:
        behavior_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcounter.xml", "procedure:counter.alwaysff")
        plan = VerificationPlan(
            module="counter",
            targets=(VerificationTarget.COCOTB,),
            ports=(
                RTLPort(name="clk", direction="input"),
                RTLPort(name="rst_n", direction="input"),
                RTLPort(name="en", direction="input", width=1),
                RTLPort(name="count", direction="output", width=8),
            ),
            behaviors=(
                VerificationBehavior(
                    behavior_id="counter:behavior:1:1",
                    scope="counter",
                    kind="increment",
                    target="count",
                    control="en",
                    source="count",
                    evidence_refs=(behavior_ref,),
                ),
            ),
        )

        artifact = CocotbGenerator().generate(plan)[0]

        self.assertIn("for name in ('en',):", artifact.content)
        self.assertIn("for name in ('count',):", artifact.content)
        self.assertIn("_drive_if_present(dut, 'en', 1)", artifact.content)
        self.assertIn("assert after == before + 1", artifact.content)


class FormalGeneratorTests(unittest.TestCase):
    def test_formal_generator_emits_harness_and_sby_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "Vsimple_counter.xml"
            xml_path.write_text(
                """<?xml version="1.0" ?>
<verilator_xml>
  <netlist>
    <module name="simple_counter" origName="simple_counter">
      <var name="count_o" origName="count_o" dir="output" dtype_id="4"/>
    </module>
    <typetable>
      <basicdtype id="4" name="logic" left="7" right="0"/>
    </typetable>
  </netlist>
</verilator_xml>
""",
                encoding="utf-8",
            )
            clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk@a,4,17,4,20")
            rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n@a,5,17,5,22")
            enable_ref = EvidenceRef(
                EvidenceKind.VERILATOR_AST,
                "Vsimple_counter.xml",
                "port:simple_counter.enable_i@a,6,17,6,25",
            )
            count_ref = EvidenceRef(
                EvidenceKind.VERILATOR_AST,
                str(xml_path),
                "port:simple_counter.count_o@a,7,30,7,37",
            )
            plan = VerificationPlan(
                module="simple_counter",
                targets=(VerificationTarget.FORMAL,),
                requirements=(
                    "rst_n clears count_o to zero.",
                    "count_o increments when enable_i is asserted.",
                    "count_o holds when enable_i is low.",
                ),
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
        self.assertIn("wire [7:0] count_o;", harness.content)
        self.assertNotIn("clk = $anyseq", harness.content)
        self.assertIn("simple_counter dut", harness.content)
        self.assertIn(".enable_i(enable_i)", harness.content)
        self.assertIn(".count_o(count_o)", harness.content)
        self.assertIn("assume(rst_n == 1'b0);", harness.content)
        self.assertIn("if (!$initstate && $past(rst_n == 1'b0)) begin", harness.content)
        self.assertIn("assert(count_o == '0);", harness.content)
        self.assertIn("&& $past(enable_i)) begin", harness.content)
        self.assertIn("assert(count_o == $past(count_o) + 1'b1);", harness.content)
        self.assertIn("&& !$past(enable_i)) begin", harness.content)
        self.assertIn("assert(count_o == $past(count_o));", harness.content)
        self.assertIn("cover(rst_n == 1'b1 && enable_i);", harness.content)
        self.assertEqual(sby.path, Path("simple_counter.sby"))
        self.assertEqual(sby.kind, ArtifactKind.RUN_SCRIPT)
        self.assertIn("prep -top formal_simple_counter", sby.content)

    def test_formal_generator_falls_back_to_scalar_output_when_width_evidence_is_missing(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "missing.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "missing.xml", "port:simple_counter.rst_n")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "missing.xml", "port:simple_counter.count_o")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.FORMAL,),
            requirements=("rst_n clears count_o to zero.",),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, count_ref),
                ),
            ),
        )

        harness = FormalGenerator().generate(plan)[0]

        self.assertIn("wire count_o;", harness.content)

    def test_formal_generator_uses_structured_behaviors_without_requirement_text(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        behavior_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "procedure:simple_counter.alwaysff")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.FORMAL,),
            behaviors=(
                VerificationBehavior(
                    behavior_id="simple_counter:behavior:1:1",
                    scope="simple_counter",
                    kind="reset_to_constant",
                    target="count_o",
                    control="rst_n",
                    value="0",
                    evidence_refs=(behavior_ref,),
                ),
                VerificationBehavior(
                    behavior_id="simple_counter:behavior:1:2",
                    scope="simple_counter",
                    kind="increment",
                    target="count_o",
                    control="enable_i",
                    source="count_o",
                    evidence_refs=(behavior_ref,),
                ),
            ),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        harness = FormalGenerator().generate(plan)[0]

        self.assertIn("assert(count_o == '0);", harness.content)
        self.assertIn("assert(count_o == $past(count_o) + 1'b1);", harness.content)

    def test_formal_generator_uses_structured_port_directions_and_widths_without_suffixes(self) -> None:
        behavior_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcounter.xml", "procedure:counter.alwaysff")
        plan = VerificationPlan(
            module="counter",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort(name="clk", direction="input"),
                RTLPort(name="rst_n", direction="input"),
                RTLPort(name="en", direction="input", width=1),
                RTLPort(name="count", direction="output", width=8, signed=True),
            ),
            behaviors=(
                VerificationBehavior(
                    behavior_id="counter:behavior:1:1",
                    scope="counter",
                    kind="increment",
                    target="count",
                    control="en",
                    source="count",
                    evidence_refs=(behavior_ref,),
                ),
            ),
        )

        harness = FormalGenerator().generate(plan)[0]

        self.assertIn("wire signed [7:0] count;", harness.content)
        self.assertIn(".en(en)", harness.content)
        self.assertIn(".count(count)", harness.content)
        self.assertIn("assert(count == $past(count) + 1'b1);", harness.content)


class SystemVerilogGeneratorTests(unittest.TestCase):
    def test_systemverilog_generator_emits_testbench_scaffold(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.SYSTEMVERILOG,),
            checks=("Verify count_o increments when enable_i is asserted.",),
            requirements=("The simple_counter increments count_o when enable_i is asserted.",),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        artifact = SystemVerilogGenerator().generate(plan)[0]

        self.assertEqual(artifact.path, Path("tb_simple_counter.sv"))
        self.assertEqual(artifact.kind, ArtifactKind.TESTBENCH)
        self.assertEqual(artifact.target, VerificationTarget.SYSTEMVERILOG)
        self.assertEqual(artifact.provenance_refs, (clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("module tb_simple_counter;", artifact.content)
        self.assertIn("simple_counter dut", artifact.content)
        self.assertIn(".enable_i(enable_i)", artifact.content)
        self.assertIn("always #5 clk = ~clk;", artifact.content)
        self.assertIn("rst_n = 1'b0;", artifact.content)
        self.assertIn("rst_n = 1'b1;", artifact.content)
        self.assertIn("Verify count_o increments", artifact.content)


class VerilogGeneratorTests(unittest.TestCase):
    def test_verilog_generator_emits_testbench_scaffold(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.VERILOG,),
            checks=("Verify count_o increments when enable_i is asserted.",),
            requirements=("The simple_counter increments count_o when enable_i is asserted.",),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        artifact = VerilogGenerator().generate(plan)[0]

        self.assertEqual(artifact.path, Path("tb_simple_counter.v"))
        self.assertEqual(artifact.kind, ArtifactKind.TESTBENCH)
        self.assertEqual(artifact.target, VerificationTarget.VERILOG)
        self.assertEqual(artifact.provenance_refs, (clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("module tb_simple_counter;", artifact.content)
        self.assertIn("reg clk;", artifact.content)
        self.assertIn("reg enable_i;", artifact.content)
        self.assertIn("wire count_o;", artifact.content)
        self.assertIn("always #5 clk = ~clk;", artifact.content)
        self.assertIn("rst_n = 1'b0;", artifact.content)
        self.assertIn("rst_n = 1'b1;", artifact.content)


class VhdlGeneratorTests(unittest.TestCase):
    def test_vhdl_generator_emits_testbench_scaffold(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.VHDL,),
            checks=("Verify count_o increments when enable_i is asserted.",),
            requirements=("The simple_counter increments count_o when enable_i is asserted.",),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        artifact = VhdlGenerator().generate(plan)[0]

        self.assertEqual(artifact.path, Path("tb_simple_counter.vhd"))
        self.assertEqual(artifact.kind, ArtifactKind.TESTBENCH)
        self.assertEqual(artifact.target, VerificationTarget.VHDL)
        self.assertEqual(artifact.provenance_refs, (clk_ref, rst_ref, enable_ref, count_ref))
        self.assertIn("entity tb_simple_counter is", artifact.content)
        self.assertIn("dut: entity work.simple_counter", artifact.content)
        self.assertIn("enable_i => enable_i", artifact.content)
        self.assertIn("signal clk : std_logic := '0';", artifact.content)
        self.assertIn("signal count_o : std_logic;", artifact.content)
        self.assertIn("rst_n <= '0';", artifact.content)
        self.assertIn("rst_n <= '1';", artifact.content)


class UvmGeneratorTests(unittest.TestCase):
    def test_uvm_generator_emits_conservative_scaffold(self) -> None:
        clk_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.clk")
        rst_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n")
        enable_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i")
        count_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o")
        plan = VerificationPlan(
            module="simple_counter",
            targets=(VerificationTarget.UVM,),
            requirements=("The simple_counter increments count_o when enable_i is asserted.",),
            claims=(
                VerificationClaim(
                    "simple_counter:ports",
                    "simple_counter",
                    "ports exist",
                    evidence_refs=(clk_ref, rst_ref, enable_ref, count_ref),
                ),
            ),
        )

        artifacts = UvmGenerator().generate(plan)

        self.assertEqual(tuple(artifact.path for artifact in artifacts), (
            Path("simple_counter_pkg.sv"),
            Path("simple_counter_if.sv"),
            Path("tb_simple_counter_uvm.sv"),
            Path("README.md"),
        ))
        self.assertTrue(all(artifact.target == VerificationTarget.UVM for artifact in artifacts))
        self.assertIn("class simple_counter_test extends uvm_test", artifacts[0].content)
        self.assertIn("interface simple_counter_if(input logic clk);", artifacts[1].content)
        self.assertIn("logic enable_i;", artifacts[1].content)
        self.assertIn("run_test(\"simple_counter_test\")", artifacts[2].content)
        self.assertIn("Advanced UVM generation is blocked", artifacts[3].content)


if __name__ == "__main__":
    unittest.main()
