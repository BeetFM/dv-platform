import unittest
from unittest import mock

from dv_platform.core.tool_versions import (
    TOOL_VERSION_POLICIES,
    classify_tool_version,
    formal_dependency_qualifications,
    probe_tool_version,
)


class ToolVersionQualificationTests(unittest.TestCase):
    def test_classifies_every_reference_tool_at_and_outside_its_range(self) -> None:
        banners = {
            "verilator": "Verilator 5.020 2024-01-01",
            "iverilog": "Icarus Verilog version 12.0 (stable)",
            "ghdl": "GHDL 5.0.1-dev",
            "sby": "SBY v0.67",
            "yosys": "Yosys 0.33",
            "z3": "Z3 version 4.8.12 - 64 bit",
        }
        for tool, banner in banners.items():
            with self.subTest(tool=tool):
                result = classify_tool_version(tool, banner)
                self.assertEqual(result["status"], "supported")
                self.assertIsNotNone(result["minimum_tested"])
                self.assertIsNotNone(result["maximum_tested"])

        self.assertEqual(classify_tool_version("iverilog", "Icarus Verilog version 11.0")["status"], "unsupported")
        self.assertEqual(classify_tool_version("vendor-sim", "Vendor 2026.1")["status"], "unqualified")
        self.assertEqual(classify_tool_version("ghdl", "not a version")["status"], "unknown")

    def test_probe_uses_tool_specific_version_switch_without_shell(self) -> None:
        completed = mock.Mock(stdout="", stderr="Icarus Verilog version 12.0 (stable)\n")
        with mock.patch("dv_platform.core.tool_versions.subprocess.run", return_value=completed) as run:
            result = probe_tool_version("/tools/iverilog --unused-runtime-flag")

        self.assertEqual(result["status"], "supported")
        run.assert_called_once_with(
            ("/tools/iverilog", "-V"),
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )

    def test_symbiyosys_records_yosys_and_solver_qualifications(self) -> None:
        with mock.patch(
            "dv_platform.core.tool_versions.probe_tool_version",
            side_effect=lambda command: {"tool": command, "status": "supported"},
        ):
            dependencies = formal_dependency_qualifications("sby -f")

        self.assertEqual([item["tool"] for item in dependencies], ["yosys", "z3"])
        self.assertEqual(set(TOOL_VERSION_POLICIES), {"verilator", "iverilog", "ghdl", "sby", "yosys", "z3"})


if __name__ == "__main__":
    unittest.main()
