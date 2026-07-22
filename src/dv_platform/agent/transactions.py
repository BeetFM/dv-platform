"""Deterministic reference models for accepted production-protocol traces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dv_platform.agent.protocols import protocol_profile


class ProtocolTraceError(ValueError):
    """Raised when an accepted transaction trace violates its profile."""


@dataclass(frozen=True)
class ProtocolBeat:
    """One accepted channel event in cycle order."""

    channel: str
    cycle: int
    fields: tuple[tuple[str, int], ...] = ()

    def values(self) -> dict[str, int]:
        return dict(self.fields)


@dataclass(frozen=True)
class ProtocolTraceResult:
    profile_id: str
    accepted: int
    completed: int
    maximum_outstanding: int
    coverage: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "profile_id": self.profile_id,
            "accepted": self.accepted,
            "completed": self.completed,
            "maximum_outstanding": self.maximum_outstanding,
            "coverage": list(self.coverage),
            "status": "passed",
        }


def validate_protocol_trace_file(path: Path) -> ProtocolTraceResult:
    """Decode and validate a public protocol-trace v1 JSON document."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ProtocolTraceError("unsupported protocol trace schema")
    raw_beats = value.get("beats")
    if not isinstance(raw_beats, list):
        raise ProtocolTraceError("protocol trace beats must be an array")
    beats: list[ProtocolBeat] = []
    for raw in raw_beats:
        if not isinstance(raw, dict) or not isinstance(raw.get("fields", {}), dict):
            raise ProtocolTraceError("protocol trace beat is invalid")
        fields = raw.get("fields", {})
        assert isinstance(fields, dict)
        if any(not isinstance(item, int) or isinstance(item, bool) for item in fields.values()):
            raise ProtocolTraceError("protocol trace field values must be integers")
        beats.append(
            ProtocolBeat(
                str(raw.get("channel", "")),
                int(raw.get("cycle", -1)),
                tuple(sorted((str(name), item) for name, item in fields.items())),
            )
        )
    return validate_protocol_trace(str(value.get("profile_id", "")), tuple(beats))


def validate_protocol_trace(profile_id: str, beats: tuple[ProtocolBeat, ...]) -> ProtocolTraceResult:
    """Validate accepted events against one immutable profile reference model."""

    profile = protocol_profile(profile_id)
    if any(beat.cycle < 0 for beat in beats) or any(
        right.cycle < left.cycle for left, right in zip(beats, beats[1:], strict=False)
    ):
        raise ProtocolTraceError("trace cycles must be non-negative and monotonic")
    if profile_id in {"axi4-1.0", "axi4-lite-1.0"}:
        return _axi(profile_id, beats, profile.maximum_outstanding, profile.maximum_burst_length)
    if profile_id == "axi4-stream-1.0":
        return _packet_stream(
            profile_id,
            beats,
            "t",
            "tlast",
            "tkeep",
            "tstrb",
            "tid",
            "tdest",
            profile.maximum_burst_length,
        )
    if profile_id == "wishbone-b4-1.0":
        return _wishbone(beats, profile.maximum_outstanding)
    if profile_id == "avalon-mm-1.0":
        return _avalon_mm(beats, profile.maximum_outstanding, profile.maximum_burst_length)
    if profile_id == "avalon-st-1.0":
        return _packet_stream(
            profile_id,
            beats,
            "stream",
            "endofpacket",
            "empty",
            None,
            "channel",
            None,
            profile.maximum_burst_length,
        )
    if profile_id == "ahb-1.0":
        return _ahb(beats, profile.maximum_burst_length)
    if profile_id == "tilelink-ul-uh-1.0":
        return _tilelink(beats, profile.maximum_outstanding)
    raise ProtocolTraceError(f"no reference model for {profile_id}")


def _axi(profile_id: str, beats: tuple[ProtocolBeat, ...], limit: int, burst_limit: int) -> ProtocolTraceResult:
    lite = profile_id == "axi4-lite-1.0"
    writes: list[dict[str, int]] = []
    reads: dict[int, list[dict[str, int]]] = {}
    write_ids: dict[int, list[dict[str, int]]] = {}
    completed = 0
    maximum = 0
    coverage: set[str] = set()
    for beat in beats:
        value = beat.values()
        channel = beat.channel.lower()
        if channel == "aw":
            transaction = _axi_address(value, "aw", lite, burst_limit)
            writes.append(transaction)
            write_ids.setdefault(transaction["id"], []).append(transaction)
            coverage.update(("write", f"burst:{transaction['burst']}", f"length:{transaction['beats']}"))
        elif channel == "w":
            pending = next((item for item in writes if item["seen"] < item["beats"]), None)
            if pending is None:
                raise ProtocolTraceError("AXI W beat has no accepted AW transaction")
            strobe = value.get("wstrb", 1)
            if strobe <= 0:
                raise ProtocolTraceError("AXI WSTRB must select at least one lane")
            if not lite and strobe.bit_count() > 1 << pending["size"]:
                raise ProtocolTraceError("AXI WSTRB selects more bytes than the accepted transfer size")
            pending["seen"] += 1
            expected_last = pending["seen"] == pending["beats"]
            if bool(value.get("wlast", int(lite))) != expected_last:
                raise ProtocolTraceError("AXI WLAST does not match the accepted burst length")
            coverage.add("byte_enable")
        elif channel == "b":
            identity = value.get("bid", 0)
            queue = write_ids.get(identity, [])
            if not queue or queue[0]["seen"] != queue[0]["beats"]:
                raise ProtocolTraceError("AXI B response is early, duplicated, or has an unknown ID")
            queue.pop(0)
            completed += 1
            coverage.add(f"response:{value.get('bresp', 0)}")
        elif channel == "ar":
            transaction = _axi_address(value, "ar", lite, burst_limit)
            reads.setdefault(transaction["id"], []).append(transaction)
            coverage.update(("read", f"burst:{transaction['burst']}", f"length:{transaction['beats']}"))
        elif channel == "r":
            identity = value.get("rid", 0)
            queue = reads.get(identity, [])
            if not queue:
                raise ProtocolTraceError("AXI R response has an unknown ID or was duplicated")
            transaction = queue[0]
            transaction["seen"] += 1
            expected_last = transaction["seen"] == transaction["beats"]
            if bool(value.get("rlast", int(lite))) != expected_last:
                raise ProtocolTraceError("AXI RLAST does not match the accepted burst length")
            if expected_last:
                queue.pop(0)
                completed += 1
            coverage.add(f"response:{value.get('rresp', 0)}")
        else:
            raise ProtocolTraceError(f"unsupported AXI trace channel: {beat.channel}")
        outstanding = sum(len(queue) for queue in write_ids.values()) + sum(len(queue) for queue in reads.values())
        maximum = max(maximum, outstanding)
        if outstanding > limit:
            raise ProtocolTraceError("AXI outstanding transaction bound exceeded")
    if any(item["seen"] != item["beats"] for item in writes) or any(write_ids.values()) or any(reads.values()):
        raise ProtocolTraceError("AXI trace ended with incomplete transactions")
    return ProtocolTraceResult(profile_id, len(beats), completed, maximum, tuple(sorted(coverage)))


def _axi_address(value: dict[str, int], prefix: str, lite: bool, burst_limit: int) -> dict[str, int]:
    address = value.get(prefix + "addr", 0)
    length = 1 if lite else value.get(prefix + "len", 0) + 1
    size = value.get(prefix + "size", 0)
    burst = 1 if lite else value.get(prefix + "burst", 1)
    if length < 1 or length > burst_limit or burst not in {0, 1, 2}:
        raise ProtocolTraceError("AXI burst shape or length is invalid")
    if burst == 2 and length not in {2, 4, 8, 16}:
        raise ProtocolTraceError("AXI WRAP burst length must be 2, 4, 8, or 16")
    if (address & 0xFFF) + (length << size) > 4096:
        raise ProtocolTraceError("AXI burst crosses a 4-KiB boundary")
    return {
        "id": value.get(prefix + "id", 0),
        "beats": length,
        "seen": 0,
        "burst": burst,
        "size": size,
        "address": address,
    }


def _packet_stream(
    profile_id: str,
    beats: tuple[ProtocolBeat, ...],
    channel: str,
    last_name: str,
    final_mask: str,
    strobe_name: str | None,
    route_name: str,
    destination_name: str | None,
    maximum_packet_length: int,
) -> ProtocolTraceResult:
    packet_open = False
    route: tuple[int, int] | None = None
    packets = 0
    length = 0
    coverage: set[str] = set()
    for beat in beats:
        if beat.channel.lower() != channel:
            raise ProtocolTraceError(f"unexpected packet-stream channel: {beat.channel}")
        value = beat.values()
        if profile_id == "avalon-st-1.0":
            start = bool(value.get("startofpacket", 0))
            if start == packet_open:
                raise ProtocolTraceError("Avalon-ST SOP is missing or repeated")
        elif not packet_open:
            start = True
        else:
            start = False
        current_route = (value.get(route_name, 0), value.get(destination_name, 0) if destination_name else 0)
        if start:
            packet_open = True
            route = current_route
            length = 0
        if not packet_open or current_route != route:
            raise ProtocolTraceError("packet routing changed before end-of-packet")
        length += 1
        if length > maximum_packet_length:
            raise ProtocolTraceError("packet length exceeds the configured profile bound")
        last = bool(value.get(last_name, 0))
        mask = value.get(final_mask, 1 if profile_id == "axi4-stream-1.0" else 0)
        if profile_id == "axi4-stream-1.0":
            if mask == 0 or (strobe_name and value.get(strobe_name, mask) & ~mask):
                raise ProtocolTraceError("AXI4-Stream TKEEP/TSTRB is illegal")
        elif not last and mask:
            raise ProtocolTraceError("Avalon-ST empty is legal only on EOP")
        if last:
            packets += 1
            packet_open = False
            coverage.update((f"packet_length:{length}", f"route:{current_route[0]}:{current_route[1]}"))
            if mask not in {0, 1}:
                coverage.add("sparse_final_beat")
    if packet_open:
        raise ProtocolTraceError("packet trace ended without a final beat")
    return ProtocolTraceResult(profile_id, len(beats), packets, 1 if beats else 0, tuple(sorted(coverage)))


def _wishbone(beats: tuple[ProtocolBeat, ...], limit: int) -> ProtocolTraceResult:
    pending: list[dict[str, int]] = []
    completed = 0
    maximum = 0
    coverage: set[str] = set()
    for beat in beats:
        value = beat.values()
        if beat.channel.lower() == "request":
            if not value.get("cyc", 1) or not value.get("stb", 1) or value.get("stall", 0):
                raise ProtocolTraceError("Wishbone request trace contains an unaccepted transfer")
            cti, bte = value.get("cti", 0), value.get("bte", 0)
            if cti not in {0, 1, 2, 7} or bte not in {0, 1, 2, 3}:
                raise ProtocolTraceError("Wishbone CTI/BTE is invalid")
            if value.get("we", 0) and value.get("sel", 1) <= 0:
                raise ProtocolTraceError("Wishbone write request has an empty SEL mask")
            pending.append(value)
            maximum = max(maximum, len(pending))
            if len(pending) > limit:
                raise ProtocolTraceError("Wishbone outstanding request bound exceeded")
            coverage.add(f"cti:{cti}")
        elif beat.channel.lower() == "response":
            responses = sum(bool(value.get(name, 0)) for name in ("ack", "err", "rty"))
            if not pending or responses != 1:
                raise ProtocolTraceError("Wishbone response is missing, overlapping, or duplicated")
            pending.pop(0)
            completed += 1
            coverage.add(next(name for name in ("ack", "err", "rty") if value.get(name, 0)))
        else:
            raise ProtocolTraceError(f"unsupported Wishbone trace channel: {beat.channel}")
    if pending:
        raise ProtocolTraceError("Wishbone trace ended with pending requests")
    return ProtocolTraceResult("wishbone-b4-1.0", len(beats), completed, maximum, tuple(sorted(coverage)))


def _avalon_mm(beats: tuple[ProtocolBeat, ...], limit: int, burst_limit: int) -> ProtocolTraceResult:
    reads: list[int] = []
    writes = 0
    completed = 0
    maximum = 0
    coverage: set[str] = set()
    for beat in beats:
        value = beat.values()
        channel = beat.channel.lower()
        if channel == "command":
            if bool(value.get("read")) == bool(value.get("write")) or value.get("waitrequest", 0):
                raise ProtocolTraceError("Avalon-MM command is not an accepted exclusive read/write")
            burst = value.get("burstcount", 1)
            if not 1 <= burst <= burst_limit:
                raise ProtocolTraceError("Avalon-MM burstcount is invalid")
            if value.get("read"):
                reads.append(burst)
            else:
                if value.get("byteenable", 1) <= 0:
                    raise ProtocolTraceError("Avalon-MM write command has an empty byteenable mask")
                if value.get("response_required", 1):
                    writes += 1
                else:
                    completed += 1
                    coverage.add("write_response:disabled")
            maximum = max(maximum, len(reads) + writes)
            if maximum > limit:
                raise ProtocolTraceError("Avalon-MM pending transaction bound exceeded")
            coverage.add(f"burstcount:{burst}")
        elif channel == "read_response":
            if not reads:
                raise ProtocolTraceError("Avalon-MM read response is early or duplicated")
            reads[0] -= 1
            if reads[0] == 0:
                reads.pop(0)
                completed += 1
            coverage.add(f"response:{value.get('response', 0)}")
        elif channel == "write_response":
            if writes <= 0:
                raise ProtocolTraceError("Avalon-MM write response is early or duplicated")
            writes -= 1
            completed += 1
            coverage.add(f"response:{value.get('response', 0)}")
        else:
            raise ProtocolTraceError(f"unsupported Avalon-MM trace channel: {beat.channel}")
    if reads or writes:
        raise ProtocolTraceError("Avalon-MM trace ended with pending transactions")
    return ProtocolTraceResult("avalon-mm-1.0", len(beats), completed, maximum, tuple(sorted(coverage)))


def _ahb(beats: tuple[ProtocolBeat, ...], burst_limit: int) -> ProtocolTraceResult:
    completed = 0
    coverage: set[str] = set()
    previous_address: int | None = None
    for beat in beats:
        if beat.channel.lower() != "transfer":
            raise ProtocolTraceError(f"unsupported AHB trace channel: {beat.channel}")
        value = beat.values()
        if not value.get("hsel", 1) or value.get("htrans", 0) & 2 == 0 or not value.get("hready", 1):
            raise ProtocolTraceError("AHB trace contains an unaccepted IDLE/BUSY/wait transfer")
        burst = value.get("hburst", 0)
        if burst not in range(8):
            raise ProtocolTraceError("AHB HBURST is invalid")
        address = value.get("haddr", 0)
        step = 1 << value.get("hsize", 0)
        if (
            value.get("htrans") == 3
            and previous_address is not None
            and abs(address - previous_address) > step * burst_limit
        ):
            raise ProtocolTraceError("AHB sequential burst address is discontinuous")
        previous_address = address
        completed += 1
        coverage.update((f"burst:{burst}", f"response:{value.get('hresp', 0)}"))
    return ProtocolTraceResult("ahb-1.0", len(beats), completed, 1 if beats else 0, tuple(sorted(coverage)))


def _tilelink(beats: tuple[ProtocolBeat, ...], limit: int) -> ProtocolTraceResult:
    pending: dict[int, list[dict[str, int]]] = {}
    completed = 0
    maximum = 0
    coverage: set[str] = set()
    for beat in beats:
        value = beat.values()
        channel = beat.channel.upper()
        if channel == "A":
            source = value.get("a_source", 0)
            transaction = dict(value)
            transaction["beats"] = value.get("a_beats", 1)
            transaction["seen"] = 0
            if transaction["beats"] < 1 or transaction["beats"] > 256:
                raise ProtocolTraceError("TileLink multibeat request length is invalid")
            pending.setdefault(source, []).append(transaction)
            maximum = max(maximum, sum(len(queue) for queue in pending.values()))
            if maximum > limit:
                raise ProtocolTraceError("TileLink outstanding source bound exceeded")
            coverage.update((f"opcode:{value.get('a_opcode', 0)}", f"size:{value.get('a_size', 0)}"))
        elif channel == "D":
            source = value.get("d_source", 0)
            queue = pending.get(source, [])
            if not queue:
                raise ProtocolTraceError("TileLink D response has an unknown source or was reordered")
            request = queue.pop(0)
            if value.get("d_size", request.get("a_size", 0)) != request.get("a_size", 0):
                raise ProtocolTraceError("TileLink response size does not match its A request")
            request["seen"] += 1
            expected_last = request["seen"] == request["beats"]
            if bool(value.get("d_last", 1)) != expected_last:
                raise ProtocolTraceError("TileLink D multibeat completion does not match the request length")
            if not expected_last:
                queue.insert(0, request)
            else:
                completed += 1
            coverage.update((f"denied:{value.get('d_denied', 0)}", f"corrupt:{value.get('d_corrupt', 0)}"))
        else:
            raise ProtocolTraceError(f"unsupported TileLink trace channel: {beat.channel}")
    if any(pending.values()):
        raise ProtocolTraceError("TileLink trace ended with pending source IDs")
    return ProtocolTraceResult("tilelink-ul-uh-1.0", len(beats), completed, maximum, tuple(sorted(coverage)))
