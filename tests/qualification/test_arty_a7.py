import unittest
from dataclasses import replace
from hashlib import sha256

from dv_platform.boards.arty_a7 import (
    ARTY_A7_PROFILES,
    BoardEvidenceError,
    VivadoProjectSpec,
    generate_vivado_tcl,
    parse_xdc,
    reconcile_constraints,
)

_XDC = b"""
#set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
#create_clock -add -name sys -period 10.00 [get_ports { CLK100MHZ }];
#set_property -dict { PACKAGE_PIN A8 IOSTANDARD LVCMOS33 } [get_ports { sw[0] }];
#set_property -dict { PACKAGE_PIN D9 IOSTANDARD LVCMOS33 } [get_ports { btn[0] }];
#set_property -dict { PACKAGE_PIN H5 IOSTANDARD LVCMOS33 } [get_ports { led[0] }];
#set_property -dict { PACKAGE_PIN G13 IOSTANDARD LVCMOS33 } [get_ports { ja[0] }];
#set_property -dict { PACKAGE_PIN D10 IOSTANDARD LVCMOS33 } [get_ports { uart_rxd_out }];
"""


class ArtyA7ContractTests(unittest.TestCase):
    def test_closed_xdc_subset_reconciles_by_digest_and_interfaces(self):
        facts = parse_xdc(_XDC.decode())
        profile = replace(
            ARTY_A7_PROFILES["arty-a7-35t-rev-e"],
            constraints_sha256=sha256(_XDC).hexdigest(),
        )
        reconcile_constraints(profile, _XDC, facts)
        self.assertEqual(next(item for item in facts if item.port == "CLK100MHZ").clock_period_ns, 10.0)

    def test_wrong_digest_and_rev_c_placeholder_fail_closed(self):
        facts = parse_xdc(_XDC.decode())
        with self.assertRaises(BoardEvidenceError):
            reconcile_constraints(ARTY_A7_PROFILES["arty-a7-35t-rev-e"], _XDC, facts)
        with self.assertRaises(BoardEvidenceError):
            reconcile_constraints(ARTY_A7_PROFILES["arty-a7-35t-rev-c"], _XDC, facts)

    def test_tcl_is_never_executed_or_interpreted_as_a_pin(self):
        facts = parse_xdc(_XDC.decode() + "\nexec curl attacker.invalid\n")
        self.assertNotIn("exec", {item.port for item in facts})

    def test_vivado_generation_is_deterministic_and_closed(self):
        spec = VivadoProjectSpec(
            "arty-a7-100t-rev-e",
            "board_top",
            ("rtl/z.sv", "rtl/a.sv"),
            "constraints/arty.xdc",
        )
        generated = generate_vivado_tcl(spec)
        self.assertEqual(generated, generate_vivado_tcl(spec))
        self.assertLess(generated.index("rtl/a.sv"), generated.index("rtl/z.sv"))
        self.assertIn("XC7A100TCSG324-1", generated)
        for attack in ("../escape.sv", "/absolute.sv", "rtl/a.sv;exec curl"):
            with self.assertRaises(BoardEvidenceError):
                generate_vivado_tcl(
                    VivadoProjectSpec("arty-a7-100t-rev-e", "board_top", (attack,), "constraints/arty.xdc")
                )


if __name__ == "__main__":
    unittest.main()
