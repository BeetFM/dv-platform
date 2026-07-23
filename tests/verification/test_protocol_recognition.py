import unittest

from dv_platform.analysis.protocols import recognize_apb4, recognize_axi4_lite, recognize_control_plane_source
from dv_platform.core.models import RTLModule, RTLPort
from tests.support.paths import FIXTURES_ROOT


class ProtocolRecognitionTests(unittest.TestCase):
    fixture_dir = FIXTURES_ROOT / "rtl"

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

    def test_apb4_accepts_normalized_scalar_ports_without_explicit_width(self) -> None:
        inputs = ("psel", "penable", "pwrite", "paddr", "pwdata", "pstrb")
        outputs = ("prdata", "pready", "pslverr")
        widths = {"paddr": 32, "pwdata": 32, "pstrb": 4, "prdata": 32}
        module = RTLModule(
            "apb",
            port_details=tuple(RTLPort(name, "input", width=widths.get(name)) for name in inputs)
            + tuple(RTLPort(name, "output", width=widths.get(name)) for name in outputs),
        )

        model = recognize_apb4(module)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.unsupported_semantics, ())

    def test_axi4_lite_requires_payloads_and_rejects_incompatible_widths(self) -> None:
        inputs = ("awaddr", "awvalid", "wdata", "wstrb", "wvalid", "bready", "araddr", "arvalid", "rready")
        outputs = ("awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid")
        widths = {"awaddr": 4, "araddr": 8, "wdata": 16, "wstrb": 1, "bresp": 1, "rdata": 8, "rresp": 3}
        module = RTLModule(
            "axi",
            port_details=tuple(RTLPort(name, "input", width=widths.get(name)) for name in inputs)
            + tuple(RTLPort(name, "output", width=widths.get(name)) for name in outputs),
        )

        model = recognize_axi4_lite(module)

        self.assertIsNotNone(model)
        assert model is not None
        self.assertGreaterEqual(len(model.unsupported_semantics), 4)
        without_strobe = RTLModule(
            "axi",
            port_details=tuple(port for port in module.port_details if port.name != "wstrb"),
        )
        self.assertIsNone(recognize_axi4_lite(without_strobe))

    def test_partial_ready_valid_is_not_a_control_plane_match(self) -> None:
        self.assertEqual(recognize_control_plane_source(self._read("not_a_protocol.sv")), ())

    def test_source_bound_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "input bound"):
            recognize_control_plane_source("x" * 1_000_001)


if __name__ == "__main__":
    unittest.main()
