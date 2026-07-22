import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.vhdl import VHDLNormalizationError, normalize_vhdl_sources
from dv_platform.core.models import EvidenceKind, VerificationTarget

FIXTURE = Path(__file__).parent / "fixtures" / "rtl" / "parameterized_counter.vhd"


class VHDLNormalizationTests(unittest.TestCase):
    def test_normalizes_entity_generic_architecture_and_control_domain(self) -> None:
        modules = normalize_vhdl_sources(
            (FIXTURE,),
            parameter_overrides=("WIDTH=12",),
            top_modules=("parameterized_counter",),
        )

        self.assertEqual(len(modules), 1)
        module = modules[0]
        self.assertEqual(module.name, "parameterized_counter")
        self.assertEqual(module.original_name, "parameterized_counter")
        self.assertEqual(module.elaborated_name, "rtl")
        self.assertEqual(module.design_unit_kind, "entity")
        self.assertEqual(module.parameter_details[0].default_value, "12")
        self.assertEqual(
            {port.name: port.width for port in module.port_details},
            {
                "clk": 1,
                "rst_n": 1,
                "enable": 1,
                "count_o": 12,
            },
        )
        self.assertEqual(module.clocks, ("clk",))
        self.assertEqual(module.resets, ("rst_n",))
        self.assertTrue(module.reset_details[0].active_low)
        self.assertEqual(len(module.control_domains), 1)
        self.assertTrue(module.control_domains[0].asynchronous_reset)
        self.assertEqual(module.control_domains[0].clock, "clk")
        self.assertEqual(module.control_domains[0].reset, "rst_n")
        self.assertEqual(module.assignment_details[0].lhs_signals, ("count_o",))
        self.assertTrue(module.port_details[-1].source_location.endswith(":13"))
        self.assertTrue(module.procedural_block_details[0].source_location.endswith(":20"))
        self.assertTrue(module.assignment_details[0].source_location.endswith(":31"))
        self.assertEqual({item.kind for item in module.semantic_features}, {"vhdl_entity", "vhdl_architecture"})
        self.assertTrue(all(item.supports_target(VerificationTarget.VHDL) for item in module.semantic_features))
        self.assertEqual({ref.kind for ref in module.ast_refs}, {EvidenceKind.VHDL_SOURCE})
        self.assertTrue(any(ref.locator.startswith("port:parameterized_counter.count_o@") for ref in module.ast_refs))

    def test_generic_override_changes_identity_and_width_deterministically(self) -> None:
        first = normalize_vhdl_sources((FIXTURE,), parameter_overrides=("WIDTH=5",), identity_suffix="sweep_a")[0]
        second = normalize_vhdl_sources((FIXTURE,), parameter_overrides=("WIDTH=5",), identity_suffix="sweep_a")[0]
        wider = normalize_vhdl_sources((FIXTURE,), parameter_overrides=("WIDTH=9",), identity_suffix="sweep_b")[0]

        self.assertEqual(first, second)
        self.assertEqual(first.name, "parameterized_counter__sweep_a")
        self.assertNotEqual(first.specialization_id, wider.specialization_id)
        self.assertEqual(first.port_details[-1].width, 5)
        self.assertEqual(wider.port_details[-1].width, 9)

    def test_rejects_unknown_generic_and_ambiguous_architecture(self) -> None:
        with self.assertRaisesRegex(VHDLNormalizationError, "does not match"):
            normalize_vhdl_sources((FIXTURE,), parameter_overrides=("DEPTH=4",))

        with TemporaryDirectory() as directory:
            duplicate = Path(directory) / "ambiguous.vhd"
            duplicate.write_text(
                FIXTURE.read_text(encoding="utf-8")
                + "\narchitecture alternate of parameterized_counter is\nbegin\nend architecture alternate;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VHDLNormalizationError, "multiple architectures"):
                normalize_vhdl_sources((duplicate,))

    def test_rejects_unresolved_or_unconstrained_interface_type(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "unsupported.vhd"
            source.write_text(
                "entity unsupported is port (data : in std_logic_vector); end entity;\n"
                "architecture rtl of unsupported is begin end architecture rtl;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VHDLNormalizationError, "unconstrained"):
                normalize_vhdl_sources((source,))


if __name__ == "__main__":
    unittest.main()
