import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.bindings import load_cross_language_bindings, validate_cross_language_bindings
from dv_platform.core.models import RTLModule, RTLParameter, RTLPort


class CrossLanguageBindingTests(unittest.TestCase):
    def test_explicit_binding_round_trip_and_ambiguity_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            binding = {
                "instance": "u_core",
                "parent_language": "systemverilog",
                "parent_unit": "top",
                "child_language": "vhdl",
                "child_unit": "core",
                "architecture": "rtl",
                "library": "work",
                "port_map": {"clk": "clk", "data": "data"},
                "generic_map": {"WIDTH": 32},
            }
            path.write_text(json.dumps({"schema_version": 1, "bindings": [binding]}), encoding="utf-8")
            loaded = load_cross_language_bindings(path)
            self.assertEqual(loaded[0].architecture, "rtl")
            path.write_text(json.dumps({"schema_version": 1, "bindings": [binding, binding]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_cross_language_bindings(path)

    def test_binding_reconciles_units_ports_generics_and_architecture(self) -> None:
        modules = (
            RTLModule(
                name="top",
                original_name="top",
                port_details=(RTLPort("clk", "input"), RTLPort("data", "input", width=32)),
            ),
            RTLModule(
                name="core",
                original_name="core",
                elaborated_name="rtl",
                port_details=(RTLPort("clk", "in"), RTLPort("data", "in", width=32)),
                parameter_details=(RTLParameter("WIDTH", default_value="32"),),
            ),
        )
        binding = {
            "instance": "u_core",
            "parent_language": "systemverilog",
            "parent_unit": "top",
            "child_language": "vhdl",
            "child_unit": "core",
            "architecture": "rtl",
            "library": "work",
            "port_map": {"clk": "clk", "data": "data"},
            "generic_map": {"WIDTH": 32},
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(json.dumps({"schema_version": 1, "bindings": [binding]}), encoding="utf-8")
            validate_cross_language_bindings(load_cross_language_bindings(path), modules)


if __name__ == "__main__":
    unittest.main()
