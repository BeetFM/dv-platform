import unittest

from dv_platform.analysis.protocols import recognize_ahb_lite, recognize_control_plane_source
from dv_platform.core.models import RTLModule
from tests.support.paths import FIXTURES_ROOT


class AhbLiteTests(unittest.TestCase):
    fixture = FIXTURES_ROOT / "rtl" / "ahb_lite_slave.sv"

    def test_source_fixture_recognizes_ahb_lite(self) -> None:
        protocols = recognize_control_plane_source(
            self.fixture.read_text(encoding="utf-8"), "ahb_lite_slave", "ahb.xml"
        )
        self.assertEqual([protocol.name for protocol in protocols], ["AHB-Lite"])
        self.assertEqual(protocols[0].version, "3.0")
        self.assertEqual(protocols[0].channels[0].transfer_condition, "HSEL && HTRANS[1] && HREADY")
        self.assertIn(("haddr", "haddr"), protocols[0].signal_bindings)

    def test_partial_ahb_signature_is_rejected(self) -> None:
        self.assertIsNone(recognize_ahb_lite(RTLModule("partial")))


if __name__ == "__main__":
    unittest.main()
