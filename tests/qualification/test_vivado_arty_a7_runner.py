import importlib.util
import unittest
from pathlib import Path

from dv_platform.boards.arty_a7 import ARTY_A7_PROFILES

_PATH = Path(__file__).resolve().parents[2] / "scripts/qualification/vivado_arty_a7.py"
_SPEC = importlib.util.spec_from_file_location("vivado_arty_a7", _PATH)
assert _SPEC and _SPEC.loader
_RUNNER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RUNNER)


class VivadoArtyA7RunnerTests(unittest.TestCase):
    def test_active_constraints_are_closed_to_fixture_ports(self):
        source = b"\n".join(
            [
                f"#set_property -dict {{ PACKAGE_PIN A1 IOSTANDARD LVCMOS33 }} [get_ports {{ {port} }}];".encode()
                for port in sorted(_RUNNER._PORTS)
            ]
            + [b"#set_property -dict { PACKAGE_PIN B1 IOSTANDARD LVCMOS33 } [get_ports { attacker }];"]
        )
        active = _RUNNER._active_constraints(source)
        self.assertNotIn("attacker", active)
        self.assertFalse(any(line.startswith("#") for line in active.splitlines()))

    def test_tcl_pins_part_and_fails_on_drc_or_timing(self):
        for profile_id, profile in ARTY_A7_PROFILES.items():
            if profile_id not in _RUNNER._XDC_NAMES:
                continue
            tcl = _RUNNER._tcl(profile_id)
            self.assertIn(profile.device, tcl)
            self.assertIn("negative setup slack", tcl)
            self.assertIn("enabled DRC errors remain", tcl)
            self.assertIn("write_bitstream", tcl)


if __name__ == "__main__":
    unittest.main()
