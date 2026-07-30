import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.transactions import (
    ProtocolBeat,
    ProtocolTraceError,
    validate_protocol_trace,
    validate_protocol_trace_file,
)


def beat(channel_name: str, cycle: int, **fields: int) -> ProtocolBeat:
    return ProtocolBeat(channel_name, cycle, tuple(sorted(fields.items())))


class ProtocolTransactionModelTests(unittest.TestCase):
    def test_axi4_bursts_ids_ordering_and_boundaries(self) -> None:
        good = (
            beat("AW", 0, awid=1, awaddr=0x100, awlen=1, awsize=2, awburst=1),
            beat("W", 1, wstrb=0xF, wlast=0),
            beat("W", 2, wstrb=0xF, wlast=1),
            beat("B", 3, bid=1, bresp=0),
            beat("AR", 4, arid=2, araddr=0x200, arlen=1, arsize=2, arburst=2),
            beat("R", 5, rid=2, rlast=0, rresp=0),
            beat("R", 6, rid=2, rlast=1, rresp=0),
        )
        result = validate_protocol_trace("axi4-1.0", good)
        self.assertEqual(result.completed, 2)
        for mutation in (
            (beat("AW", 0, awaddr=0xFFF, awlen=1, awsize=2, awburst=1),),
            good[:2] + (beat("W", 2, wstrb=0xF, wlast=0),) + good[3:],
            good[:3] + (beat("B", 3, bid=7),) + good[4:],
            (
                beat("AW", 0, awaddr=0x100, awlen=0, awsize=0, awburst=1),
                beat("W", 1, wstrb=0x3, wlast=1),
                beat("B", 2),
            ),
            (beat("AW", 0, awaddr=0x100, awlen=2, awsize=2, awburst=2),),
            good[:-1],
        ):
            with self.assertRaises(ProtocolTraceError):
                validate_protocol_trace("axi4-1.0", mutation)

    def test_packet_stream_models_kill_framing_routing_and_mask_mutations(self) -> None:
        axi = (beat("T", 0, tid=1, tdest=2, tkeep=0xF), beat("T", 1, tid=1, tdest=2, tkeep=3, tlast=1))
        self.assertEqual(validate_protocol_trace("axi4-stream-1.0", axi).completed, 1)
        with self.assertRaises(ProtocolTraceError):
            validate_protocol_trace("axi4-stream-1.0", (beat("T", 0, tkeep=0, tlast=1),))
        with self.assertRaises(ProtocolTraceError):
            validate_protocol_trace("axi4-stream-1.0", (beat("T", 0, tkeep=1, tstrb=2, tlast=1),))
        with self.assertRaises(ProtocolTraceError):
            validate_protocol_trace(
                "axi4-stream-1.0",
                (beat("T", 0, tid=1), beat("T", 1, tid=2, tlast=1)),
            )
        avalon = (
            beat("stream", 0, startofpacket=1, channel=3),
            beat("stream", 1, endofpacket=1, channel=3, empty=2),
        )
        self.assertEqual(validate_protocol_trace("avalon-st-1.0", avalon).completed, 1)
        with self.assertRaises(ProtocolTraceError):
            validate_protocol_trace("avalon-st-1.0", avalon[:-1])
        with self.assertRaises(ProtocolTraceError):
            validate_protocol_trace(
                "avalon-st-1.0",
                (beat("stream", 0, startofpacket=1, empty=1), beat("stream", 1, endofpacket=1)),
            )

    def test_wishbone_avalon_mm_ahb_and_tilelink_response_models(self) -> None:
        cases = {
            "wishbone-b4-1.0": (beat("request", 0, cyc=1, stb=1, cti=0), beat("response", 1, ack=1)),
            "avalon-mm-1.0": (
                beat("command", 0, read=1, burstcount=2),
                beat("read_response", 1),
                beat("read_response", 2),
            ),
            "ahb-1.0": (beat("transfer", 0, hsel=1, htrans=2, hready=1, hburst=0),),
            "tilelink-ul-uh-1.0": (beat("A", 0, a_source=3, a_opcode=4, a_size=2), beat("D", 1, d_source=3, d_size=2)),
        }
        for profile, trace in cases.items():
            with self.subTest(profile=profile):
                self.assertGreater(validate_protocol_trace(profile, trace).completed, 0)
        response_free_write = (beat("command", 0, write=1, response_required=0),)
        self.assertEqual(validate_protocol_trace("avalon-mm-1.0", response_free_write).completed, 1)
        tile_multibeat = (
            beat("A", 0, a_source=2, a_size=2, a_beats=2),
            beat("D", 1, d_source=2, d_size=2, d_last=0),
            beat("D", 2, d_source=2, d_size=2, d_last=1),
        )
        self.assertEqual(validate_protocol_trace("tilelink-ul-uh-1.0", tile_multibeat).completed, 1)
        bad = {
            "wishbone-b4-1.0": (beat("request", 0), beat("response", 1, ack=1, err=1)),
            "avalon-mm-1.0": (beat("command", 0, read=1, write=1),),
            "ahb-1.0": (beat("transfer", 0, htrans=0),),
            "tilelink-ul-uh-1.0": (beat("A", 0, a_source=1), beat("D", 1, d_source=2)),
        }
        for profile, trace in bad.items():
            with self.subTest(profile=profile):
                with self.assertRaises(ProtocolTraceError):
                    validate_protocol_trace(profile, trace)
        for profile, trace in (
            (
                "wishbone-b4-1.0",
                (beat("request", 0, cyc=1, stb=1, we=1, sel=0), beat("response", 1, ack=1)),
            ),
            (
                "wishbone-b4-1.0",
                (beat("request", 0, cyc=1, stb=1, cti=3), beat("response", 1, ack=1)),
            ),
            (
                "avalon-mm-1.0",
                (beat("command", 0, write=1, byteenable=0, response_required=0),),
            ),
            (
                "avalon-mm-1.0",
                (beat("command", 0, read=1, burstcount=257),),
            ),
            (
                "tilelink-ul-uh-1.0",
                (beat("A", 0, a_source=1, a_beats=2), beat("D", 1, d_source=1, d_last=1)),
            ),
        ):
            with self.subTest(profile=profile, trace=trace):
                with self.assertRaises(ProtocolTraceError):
                    validate_protocol_trace(profile, trace)

    def test_axi4_lite_and_trace_order_fail_closed(self) -> None:
        trace = (beat("AW", 0, awaddr=0), beat("W", 1, wstrb=0xF, wlast=1), beat("B", 2, bresp=0))
        self.assertEqual(validate_protocol_trace("axi4-lite-1.0", trace).completed, 1)
        with self.assertRaisesRegex(ProtocolTraceError, "monotonic"):
            validate_protocol_trace("axi4-lite-1.0", (beat("AW", 2), beat("W", 1)))

    def test_explicit_protocol_extensions_enforce_their_bounded_rules(self) -> None:
        axi = (
            beat("AW", 0, sequence=10),
            beat("AW", 1, sequence=11),
            beat("W", 2, wstrb=1, wlast=1),
            beat("W", 3, wstrb=1, wlast=1),
            beat("B", 4, sequence=10),
            beat("B", 5, sequence=11),
            beat("AR", 6, sequence=20),
            beat("AR", 7, sequence=21),
            beat("R", 8, sequence=20, rlast=1),
            beat("R", 9, sequence=21, rlast=1),
        )
        self.assertEqual(validate_protocol_trace("axi4-lite-two-outstanding-1.0", axi).completed, 4)
        with self.assertRaisesRegex(ProtocolTraceError, "out of sequence"):
            validate_protocol_trace(
                "axi4-lite-two-outstanding-1.0",
                axi[:4] + (beat("B", 4, sequence=11),),
            )

        ahb = tuple(
            beat(
                "transfer",
                index,
                hresetn=1,
                hburst=3,
                htrans=2 if index == 0 else 3,
                hready=1,
                haddr=0x100 + index * 4,
                hsize=2,
            )
            for index in range(4)
        )
        self.assertEqual(validate_protocol_trace("ahb-lite-incr4-1.0", ahb).completed, 4)
        with self.assertRaisesRegex(ProtocolTraceError, "exactly four"):
            validate_protocol_trace("ahb-lite-incr4-1.0", ahb[:3])

        apb = (
            beat("transfer", 0, presetn=1, psel=1, penable=0, pwakeup=1, paddr=4, pstrb=1),
            beat("transfer", 1, presetn=1, psel=1, penable=1, pwakeup=1, pready=0, paddr=4, pstrb=1),
            beat("transfer", 2, presetn=1, psel=1, penable=1, pwakeup=1, pready=1, paddr=4, pstrb=1),
            beat("transfer", 3, presetn=0, pwakeup=0),
        )
        self.assertEqual(validate_protocol_trace("apb5-pwakeup-1.0", apb).completed, 1)
        with self.assertRaisesRegex(ProtocolTraceError, "inactive during reset"):
            validate_protocol_trace("apb5-pwakeup-1.0", (beat("transfer", 0, presetn=0, pwakeup=1),))

    def test_public_trace_file_decodes_exact_integer_events(self) -> None:
        document = {
            "schema_version": 1,
            "profile_id": "wishbone-b4-1.0",
            "beats": [
                {"channel": "request", "cycle": 0, "fields": {"cyc": 1, "stb": 1}},
                {"channel": "response", "cycle": 1, "fields": {"ack": 1}},
            ],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(validate_protocol_trace_file(path).as_dict()["status"], "passed")
            document["beats"][0]["fields"]["cyc"] = True
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ProtocolTraceError, "integers"):
                validate_protocol_trace_file(path)


if __name__ == "__main__":
    unittest.main()
