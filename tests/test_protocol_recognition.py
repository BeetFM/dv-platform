import unittest
from pathlib import Path

from dv_platform.analysis.protocols import recognize_control_plane_source


class ProtocolRecognitionTests(unittest.TestCase):
    fixture_dir = Path(__file__).parent / "fixtures" / "rtl"

    def _read(self, name: str) -> str:
        return (self.fixture_dir / name).read_text(encoding="utf-8")

    def test_axi4_lite_golden_fixture(self) -> None:
        protocols = recognize_control_plane_source(self._read("axi4_lite_slave.sv"), "axi4_lite_slave", "axi.xml")
        self.assertEqual([protocol.name for protocol in protocols], ["AXI4-Lite"])
        self.assertEqual({channel.name for channel in protocols[0].channels}, {"AW", "W", "B", "AR", "R"})

    def test_apb4_golden_fixture(self) -> None:
        protocols = recognize_control_plane_source(self._read("apb4_slave.sv"), "apb4_slave", "apb.xml")
        self.assertEqual([protocol.name for protocol in protocols], ["APB4"])
        self.assertEqual(protocols[0].channels[0].transfer_condition, "PSEL && PENABLE && PREADY")

    def test_partial_ready_valid_is_not_a_control_plane_match(self) -> None:
        self.assertEqual(recognize_control_plane_source(self._read("not_a_protocol.sv")), ())

    def test_source_bound_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "input bound"):
            recognize_control_plane_source("x" * 1_000_001)


if __name__ == "__main__":
    unittest.main()
