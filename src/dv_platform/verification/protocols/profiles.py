"""Typed control-plane protocol and register models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dv_platform.domain.models import EvidenceRef, VerificationTarget


@dataclass(frozen=True)
class ProtocolSignal:
    """One canonical signal in a versioned protocol profile."""

    name: str
    channel: str
    direction: str
    width: int | str | None = None
    optional: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProtocolProfile:
    """Shared transaction contract consumed by recognition and generation.

    This is intentionally distinct from ``core.models.ProtocolProfile``, the
    backward-compatible configuration object for suffix-based custom
    handshakes.  A profile here describes protocol semantics, not naming
    heuristics.
    """

    profile_id: str
    protocol: str
    specification_version: str
    roles: tuple[str, ...]
    signals: tuple[ProtocolSignal, ...]
    schema_version: int = 1
    acceptance_rules: tuple[str, ...] = ()
    completion_rules: tuple[str, ...] = ()
    burst_shapes: tuple[str, ...] = ()
    maximum_burst_length: int = 1
    maximum_outstanding: int = 1
    id_policy: str = "none"
    ordering_policy: str = "in_order"
    retry_policy: str = "none"
    error_policy: str = "protocol_defined"
    timeout_cycles: int = 32
    scoreboard_keys: tuple[str, ...] = ("sequence",)
    coverage_bins: tuple[str, ...] = ()
    formal_properties: tuple[str, ...] = ()
    result_traces: tuple[str, ...] = ()
    supported_targets: tuple[VerificationTarget, ...] = ()
    unsupported_semantics: tuple[str, ...] = ()

    @property
    def channels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(signal.channel for signal in self.signals))

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported protocol profile schema version: {self.schema_version}")
        if not self.profile_id or not self.protocol or not self.roles or not self.signals:
            raise ValueError("protocol profile identity, roles, and signals are required")
        if self.maximum_burst_length < 1 or self.maximum_outstanding < 1 or self.timeout_cycles < 1:
            raise ValueError("protocol profile bounds must be positive")
        names = [signal.name for signal in self.signals]
        if len(names) != len(set(names)):
            raise ValueError("protocol profile canonical signals must be unique")
        aliases = [alias.lower() for signal in self.signals for alias in signal.aliases]
        if len(aliases) != len(set(aliases)):
            raise ValueError("protocol profile aliases must bind uniquely")
        if any(signal.direction not in {"manager_to_subordinate", "subordinate_to_manager"} for signal in self.signals):
            raise ValueError("protocol profile signal direction is invalid")


@dataclass(frozen=True)
class ProtocolChannel:
    name: str
    signals: tuple[str, ...]
    direction: str
    transfer_condition: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
    payload_fields: tuple[str, ...] = ()
    completion_condition: str | None = None


@dataclass(frozen=True)
class ProtocolModel:
    name: str
    version: str
    channels: tuple[ProtocolChannel, ...]
    signal_bindings: tuple[tuple[str, str], ...]
    signal_directions: tuple[tuple[str, str], ...] = ()
    clock_domain: str | None = None
    reset_domain: str | None = None
    ordering_rules: tuple[str, ...] = ()
    response_rules: tuple[str, ...] = ()
    error_behavior: str = "unknown"
    confidence: str = "unknown"
    unsupported_semantics: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    profile_id: str | None = None
    instance_id: str | None = None
    role: str = "subordinate"
    maximum_burst_length: int = 1
    maximum_outstanding: int = 1
    timeout_cycles: int = 32
    scoreboard_keys: tuple[str, ...] = ("sequence",)
    coverage_bins: tuple[str, ...] = ()
    formal_properties: tuple[str, ...] = ()
    result_traces: tuple[str, ...] = ()

    def validate(self, evidence_ids: set[str]) -> None:
        if self.maximum_burst_length < 1 or self.maximum_outstanding < 1 or self.timeout_cycles < 1:
            raise ValueError("protocol model bounds must be positive")
        canonical = [name for name, _signal in self.signal_bindings]
        physical = [signal for _name, signal in self.signal_bindings]
        if len(canonical) != len(set(canonical)) or len(physical) != len(set(physical)):
            raise ValueError("protocol model signal bindings must be unique")
        refs = self.evidence_refs + tuple(ref for channel in self.channels for ref in channel.evidence_refs)
        missing = [ref for ref in refs if ref.source_id not in evidence_ids and ref.locator not in evidence_ids]
        if missing:
            raise ValueError("protocol model contains evidence outside task context")


def _signals(
    channels: tuple[tuple[str, tuple[tuple[str, str, int | str | None, bool], ...]], ...],
) -> tuple[ProtocolSignal, ...]:
    return tuple(
        ProtocolSignal(name, channel, direction, width, optional, (name.lower(),))
        for channel, members in channels
        for name, direction, width, optional in members
    )


def production_protocol_profiles() -> tuple[ProtocolProfile, ...]:
    """Return the immutable 1.0 profile catalog in deterministic order."""

    m2s = "manager_to_subordinate"
    s2m = "subordinate_to_manager"
    rv_targets = (
        VerificationTarget.COCOTB,
        VerificationTarget.FORMAL,
        VerificationTarget.SYSTEMVERILOG,
        VerificationTarget.VERILOG,
    )
    stream_targets = (*rv_targets, VerificationTarget.VHDL, VerificationTarget.UVM)
    return (
        ProtocolProfile(
            "axi4-lite-1.0",
            "AXI4-Lite",
            "4.0",
            ("manager", "subordinate"),
            _signals(
                (
                    (
                        "AW",
                        (("awaddr", m2s, "ADDR_WIDTH", False), ("awvalid", m2s, 1, False), ("awready", s2m, 1, False)),
                    ),
                    (
                        "W",
                        (
                            ("wdata", m2s, "DATA_WIDTH", False),
                            ("wstrb", m2s, "DATA_WIDTH/8", False),
                            ("wvalid", m2s, 1, False),
                            ("wready", s2m, 1, False),
                        ),
                    ),
                    ("B", (("bresp", s2m, 2, False), ("bvalid", s2m, 1, False), ("bready", m2s, 1, False))),
                    (
                        "AR",
                        (("araddr", m2s, "ADDR_WIDTH", False), ("arvalid", m2s, 1, False), ("arready", s2m, 1, False)),
                    ),
                    (
                        "R",
                        (
                            ("rdata", s2m, "DATA_WIDTH", False),
                            ("rresp", s2m, 2, False),
                            ("rvalid", s2m, 1, False),
                            ("rready", m2s, 1, False),
                        ),
                    ),
                )
            ),
            acceptance_rules=("VALID && READY",),
            completion_rules=("B handshake", "R handshake"),
            maximum_outstanding=1,
            coverage_bins=("response", "backpressure", "byte_enable"),
            formal_properties=("payload stable while stalled", "accepted request eventually completes"),
            result_traces=("accepted_writes", "write_responses", "accepted_reads", "read_responses"),
            supported_targets=rv_targets,
        ),
        ProtocolProfile(
            "axi4-1.0",
            "AXI4",
            "4.0",
            ("manager", "subordinate"),
            _signals(
                (
                    (
                        "AW",
                        (
                            ("awid", m2s, "ID_WIDTH", False),
                            ("awaddr", m2s, "ADDR_WIDTH", False),
                            ("awlen", m2s, 8, False),
                            ("awsize", m2s, 3, False),
                            ("awburst", m2s, 2, False),
                            ("awvalid", m2s, 1, False),
                            ("awready", s2m, 1, False),
                            ("awlock", m2s, 1, True),
                            ("awcache", m2s, 4, True),
                            ("awprot", m2s, 3, True),
                            ("awqos", m2s, 4, True),
                            ("awregion", m2s, 4, True),
                        ),
                    ),
                    (
                        "W",
                        (
                            ("wdata", m2s, "DATA_WIDTH", False),
                            ("wstrb", m2s, "DATA_WIDTH/8", False),
                            ("wlast", m2s, 1, False),
                            ("wvalid", m2s, 1, False),
                            ("wready", s2m, 1, False),
                        ),
                    ),
                    (
                        "B",
                        (
                            ("bid", s2m, "ID_WIDTH", False),
                            ("bresp", s2m, 2, False),
                            ("bvalid", s2m, 1, False),
                            ("bready", m2s, 1, False),
                        ),
                    ),
                    (
                        "AR",
                        (
                            ("arid", m2s, "ID_WIDTH", False),
                            ("araddr", m2s, "ADDR_WIDTH", False),
                            ("arlen", m2s, 8, False),
                            ("arsize", m2s, 3, False),
                            ("arburst", m2s, 2, False),
                            ("arvalid", m2s, 1, False),
                            ("arready", s2m, 1, False),
                            ("arlock", m2s, 1, True),
                            ("arcache", m2s, 4, True),
                            ("arprot", m2s, 3, True),
                            ("arqos", m2s, 4, True),
                            ("arregion", m2s, 4, True),
                        ),
                    ),
                    (
                        "R",
                        (
                            ("rid", s2m, "ID_WIDTH", False),
                            ("rdata", s2m, "DATA_WIDTH", False),
                            ("rresp", s2m, 2, False),
                            ("rlast", s2m, 1, False),
                            ("rvalid", s2m, 1, False),
                            ("rready", m2s, 1, False),
                        ),
                    ),
                )
            ),
            acceptance_rules=("channel VALID && READY",),
            completion_rules=("B handshake", "R handshake with RLAST"),
            burst_shapes=("FIXED", "INCR", "WRAP"),
            maximum_burst_length=256,
            maximum_outstanding=16,
            id_policy="per-ID",
            ordering_policy="per-ID ordered; cross-ID reordering permitted",
            scoreboard_keys=("id", "address", "beat"),
            coverage_bins=(
                "burst_length",
                "burst_type",
                "outstanding_depth",
                "response",
                "backpressure",
                "byte_enable",
            ),
            formal_properties=("4-KiB boundary", "payload stable while stalled", "per-ID response ordering"),
            result_traces=("address", "id", "beat", "response"),
            supported_targets=(*rv_targets, VerificationTarget.UVM),
        ),
        ProtocolProfile(
            "axi4-stream-1.0",
            "AXI4-Stream",
            "1.0",
            ("source", "sink"),
            _signals(
                (
                    (
                        "T",
                        (
                            ("tvalid", m2s, 1, False),
                            ("tready", s2m, 1, False),
                            ("tdata", m2s, "DATA_WIDTH", False),
                            ("tkeep", m2s, "DATA_WIDTH/8", True),
                            ("tstrb", m2s, "DATA_WIDTH/8", True),
                            ("tlast", m2s, 1, True),
                            ("tid", m2s, "ID_WIDTH", True),
                            ("tdest", m2s, "DEST_WIDTH", True),
                            ("tuser", m2s, "USER_WIDTH", True),
                        ),
                    ),
                )
            ),
            acceptance_rules=("TVALID && TREADY",),
            completion_rules=("accepted beat with TLAST",),
            maximum_burst_length=65536,
            scoreboard_keys=("tid", "tdest", "packet", "beat"),
            coverage_bins=("packet_length", "sparse_final_beat", "backpressure", "tid", "tdest", "tuser"),
            formal_properties=("payload stable while stalled", "TKEEP/TSTRB legal", "packet framing"),
            result_traces=("packet", "beat", "keep", "id", "destination", "user"),
            supported_targets=stream_targets,
        ),
        *_additional_production_profiles(m2s, s2m, rv_targets, stream_targets),
    )


def _additional_production_profiles(
    m2s: str, s2m: str, rv_targets: tuple[VerificationTarget, ...], stream_targets: tuple[VerificationTarget, ...]
) -> tuple[ProtocolProfile, ...]:
    common_stream = ("payload stable while stalled", "accepted request eventually completes")
    return (
        ProtocolProfile(
            "wishbone-b4-1.0",
            "Wishbone B4",
            "B4",
            ("host", "device"),
            _signals(
                (
                    (
                        "cycle",
                        (
                            ("cyc", m2s, 1, False),
                            ("stb", m2s, 1, False),
                            ("we", m2s, 1, False),
                            ("adr", m2s, "ADDR_WIDTH", False),
                            ("dat_w", m2s, "DATA_WIDTH", False),
                            ("sel", m2s, "DATA_WIDTH/8", False),
                            ("ack", s2m, 1, False),
                            ("stall", s2m, 1, True),
                            ("err", s2m, 1, True),
                            ("rty", s2m, 1, True),
                            ("dat_r", s2m, "DATA_WIDTH", False),
                            ("cti", m2s, 3, True),
                            ("bte", m2s, 2, True),
                        ),
                    ),
                )
            ),
            acceptance_rules=("CYC && STB && !STALL",),
            completion_rules=("ACK || ERR || RTY",),
            burst_shapes=("classic", "incrementing", "wrapping"),
            maximum_burst_length=256,
            maximum_outstanding=16,
            retry_policy="RTY",
            scoreboard_keys=("address", "cycle"),
            coverage_bins=("cycle_type", "burst_type", "response", "stall", "byte_enable"),
            formal_properties=common_stream,
            result_traces=("request", "response", "address", "data"),
            supported_targets=stream_targets[:-1],
        ),
        ProtocolProfile(
            "avalon-mm-1.0",
            "Avalon-MM",
            "1.0",
            ("host", "agent"),
            _signals(
                (
                    (
                        "command",
                        (
                            ("read", m2s, 1, False),
                            ("write", m2s, 1, False),
                            ("address", m2s, "ADDR_WIDTH", False),
                            ("writedata", m2s, "DATA_WIDTH", False),
                            ("byteenable", m2s, "DATA_WIDTH/8", False),
                            ("burstcount", m2s, "BURST_WIDTH", True),
                            ("waitrequest", s2m, 1, False),
                        ),
                    ),
                    (
                        "response",
                        (
                            ("readdata", s2m, "DATA_WIDTH", False),
                            ("readdatavalid", s2m, 1, True),
                            ("writeresponsevalid", s2m, 1, True),
                            ("response", s2m, 2, True),
                        ),
                    ),
                )
            ),
            acceptance_rules=("(read || write) && !waitrequest",),
            completion_rules=("readdatavalid", "writeresponsevalid when enabled"),
            maximum_burst_length=256,
            maximum_outstanding=16,
            scoreboard_keys=("address", "sequence"),
            coverage_bins=("burstcount", "pending_reads", "response", "waitrequest", "byte_enable"),
            formal_properties=common_stream,
            result_traces=("command", "response", "address", "data"),
            supported_targets=stream_targets,
        ),
        ProtocolProfile(
            "avalon-st-1.0",
            "Avalon-ST",
            "1.0",
            ("source", "sink"),
            _signals(
                (
                    (
                        "stream",
                        (
                            ("valid", m2s, 1, False),
                            ("ready", s2m, 1, False),
                            ("data", m2s, "DATA_WIDTH", False),
                            ("startofpacket", m2s, 1, True),
                            ("endofpacket", m2s, 1, True),
                            ("empty", m2s, "EMPTY_WIDTH", True),
                            ("channel", m2s, "CHANNEL_WIDTH", True),
                            ("error", m2s, "ERROR_WIDTH", True),
                        ),
                    ),
                )
            ),
            acceptance_rules=("valid && ready",),
            completion_rules=("accepted endofpacket",),
            maximum_burst_length=65536,
            scoreboard_keys=("channel", "packet", "beat"),
            coverage_bins=("packet_length", "empty", "channel", "error", "ready_latency"),
            formal_properties=common_stream,
            result_traces=("packet", "beat", "channel", "error"),
            supported_targets=stream_targets,
        ),
        ProtocolProfile(
            "ahb-1.0",
            "AHB",
            "5.0",
            ("manager", "subordinate"),
            _signals(
                (
                    (
                        "transfer",
                        (
                            ("hsel", m2s, 1, False),
                            ("haddr", m2s, "ADDR_WIDTH", False),
                            ("htrans", m2s, 2, False),
                            ("hwrite", m2s, 1, False),
                            ("hsize", m2s, 3, False),
                            ("hburst", m2s, 3, False),
                            ("hwdata", m2s, "DATA_WIDTH", False),
                            ("hrdata", s2m, "DATA_WIDTH", False),
                            ("hready", s2m, 1, False),
                            ("hresp", s2m, 1, False),
                        ),
                    ),
                )
            ),
            acceptance_rules=("HSEL && HTRANS[1] && HREADY",),
            completion_rules=("HREADY",),
            burst_shapes=("SINGLE", "INCR", "WRAP4", "INCR4", "WRAP8", "INCR8", "WRAP16", "INCR16"),
            maximum_burst_length=256,
            scoreboard_keys=("address", "beat"),
            coverage_bins=("burst_type", "burst_length", "response", "wait_states"),
            formal_properties=common_stream,
            result_traces=("transfer", "beat", "response"),
            supported_targets=rv_targets,
        ),
        ProtocolProfile(
            "tilelink-ul-uh-1.0",
            "TileLink UL/UH",
            "1.8.1",
            ("manager", "subordinate"),
            _signals(
                (
                    (
                        "A",
                        (
                            ("a_valid", m2s, 1, False),
                            ("a_ready", s2m, 1, False),
                            ("a_opcode", m2s, 3, False),
                            ("a_param", m2s, 3, False),
                            ("a_size", m2s, 4, False),
                            ("a_source", m2s, "SOURCE_WIDTH", False),
                            ("a_address", m2s, "ADDR_WIDTH", False),
                            ("a_mask", m2s, "DATA_WIDTH/8", False),
                            ("a_data", m2s, "DATA_WIDTH", False),
                            ("a_corrupt", m2s, 1, True),
                        ),
                    ),
                    (
                        "D",
                        (
                            ("d_valid", s2m, 1, False),
                            ("d_ready", m2s, 1, False),
                            ("d_opcode", s2m, 3, False),
                            ("d_param", s2m, 2, False),
                            ("d_size", s2m, 4, False),
                            ("d_source", s2m, "SOURCE_WIDTH", False),
                            ("d_sink", s2m, "SINK_WIDTH", True),
                            ("d_denied", s2m, 1, False),
                            ("d_data", s2m, "DATA_WIDTH", False),
                            ("d_corrupt", s2m, 1, False),
                        ),
                    ),
                )
            ),
            acceptance_rules=("channel valid && ready",),
            completion_rules=("matching D response",),
            maximum_burst_length=256,
            maximum_outstanding=16,
            id_policy="source ID",
            ordering_policy="ordered for a source ID",
            scoreboard_keys=("source", "opcode", "beat"),
            coverage_bins=("opcode", "size", "source", "denied", "corrupt", "backpressure"),
            formal_properties=common_stream,
            result_traces=("source", "opcode", "beat", "denied", "corrupt"),
            supported_targets=(
                VerificationTarget.COCOTB,
                VerificationTarget.FORMAL,
                VerificationTarget.SYSTEMVERILOG,
                VerificationTarget.UVM,
            ),
        ),
    )


def protocol_profile(profile_id: str) -> ProtocolProfile:
    """Look up a production profile without permitting ambiguous aliases."""

    profiles = {profile.profile_id: profile for profile in production_protocol_profiles()}
    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown protocol profile: {profile_id}") from exc


def protocol_profile_to_json(profile: ProtocolProfile) -> dict[str, object]:
    """Encode a profile using the public v1 schema shape."""

    profile.validate()
    return {
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "protocol": profile.protocol,
        "specification_version": profile.specification_version,
        "roles": list(profile.roles),
        "signals": [
            {
                "name": signal.name,
                "channel": signal.channel,
                "direction": signal.direction,
                "width": signal.width,
                "optional": signal.optional,
                "aliases": list(signal.aliases),
            }
            for signal in profile.signals
        ],
        "acceptance_rules": list(profile.acceptance_rules),
        "completion_rules": list(profile.completion_rules),
        "burst_shapes": list(profile.burst_shapes),
        "maximum_burst_length": profile.maximum_burst_length,
        "maximum_outstanding": profile.maximum_outstanding,
        "id_policy": profile.id_policy,
        "ordering_policy": profile.ordering_policy,
        "retry_policy": profile.retry_policy,
        "error_policy": profile.error_policy,
        "timeout_cycles": profile.timeout_cycles,
        "scoreboard_keys": list(profile.scoreboard_keys),
        "coverage_bins": list(profile.coverage_bins),
        "formal_properties": list(profile.formal_properties),
        "result_traces": list(profile.result_traces),
        "supported_targets": [target.value for target in profile.supported_targets],
        "unsupported_semantics": list(profile.unsupported_semantics),
    }


def protocol_profile_from_json(data: Mapping[str, Any]) -> ProtocolProfile:
    """Decode and validate protocol-profile v1; future versions fail closed."""

    signals = data.get("signals")
    if not isinstance(signals, list):
        raise ValueError("protocol profile signals must be an array")
    try:
        profile = ProtocolProfile(
            profile_id=str(data["profile_id"]),
            protocol=str(data["protocol"]),
            specification_version=str(data["specification_version"]),
            roles=tuple(str(item) for item in data["roles"]),
            signals=tuple(
                ProtocolSignal(
                    name=str(item["name"]),
                    channel=str(item["channel"]),
                    direction=str(item["direction"]),
                    width=item.get("width"),
                    optional=bool(item.get("optional", False)),
                    aliases=tuple(str(alias) for alias in item.get("aliases", ())),
                )
                for item in signals
                if isinstance(item, Mapping)
            ),
            schema_version=int(data.get("schema_version", 1)),
            acceptance_rules=tuple(str(item) for item in data.get("acceptance_rules", ())),
            completion_rules=tuple(str(item) for item in data.get("completion_rules", ())),
            burst_shapes=tuple(str(item) for item in data.get("burst_shapes", ())),
            maximum_burst_length=int(data.get("maximum_burst_length", 1)),
            maximum_outstanding=int(data.get("maximum_outstanding", 1)),
            id_policy=str(data.get("id_policy", "none")),
            ordering_policy=str(data.get("ordering_policy", "in_order")),
            retry_policy=str(data.get("retry_policy", "none")),
            error_policy=str(data.get("error_policy", "protocol_defined")),
            timeout_cycles=int(data.get("timeout_cycles", 32)),
            scoreboard_keys=tuple(str(item) for item in data.get("scoreboard_keys", ("sequence",))),
            coverage_bins=tuple(str(item) for item in data.get("coverage_bins", ())),
            formal_properties=tuple(str(item) for item in data.get("formal_properties", ())),
            result_traces=tuple(str(item) for item in data.get("result_traces", ())),
            supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
            unsupported_semantics=tuple(str(item) for item in data.get("unsupported_semantics", ())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid protocol profile: {exc}") from exc
    if len(profile.signals) != len(signals):
        raise ValueError("protocol profile signal entries must be objects")
    profile.validate()
    return profile


@dataclass(frozen=True)
class RegisterField:
    name: str
    msb: int
    lsb: int
    reset_value: str | None = None
    access: str = "unknown"
    side_effect: str | None = None
    reserved: bool = False
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RegisterModel:
    name: str
    offset: int | None
    width: int
    fields: tuple[RegisterField, ...] = ()
    invalid_address_behavior: str = "unknown"
    byte_enable_behavior: str = "unknown"
    source: str = "unknown"
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def validate(self, evidence_ids: set[str]) -> None:
        if (
            self.width <= 0
            or self.offset is not None
            and self.offset < 0
            or any(field.msb < field.lsb or field.lsb < 0 or field.msb >= self.width for field in self.fields)
        ):
            raise ValueError("invalid register width or field range")
        if self.offset is None or self.source == "unknown":
            raise ValueError("register offset and source are unknown")
        refs = self.evidence_refs + tuple(ref for field in self.fields for ref in field.evidence_refs)
        if not refs:
            raise ValueError("register model requires evidence references")
        if any(ref.source_id not in evidence_ids and ref.locator not in evidence_ids for ref in refs):
            raise ValueError("register model contains evidence outside task context")


@dataclass(frozen=True)
class RegisterConflict:
    register_name: str
    property_name: str
    values: tuple[str, ...]
    reason: str
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def validate(self, evidence_ids: set[str]) -> None:
        if not self.values or not self.evidence_refs:
            raise ValueError("register conflicts require values and evidence")
        if any(ref.source_id not in evidence_ids and ref.locator not in evidence_ids for ref in self.evidence_refs):
            raise ValueError("register conflict contains evidence outside task context")


def axi4_lite_model(bindings: tuple[tuple[str, str], ...], evidence_refs: tuple[EvidenceRef, ...]) -> ProtocolModel:
    bindings = tuple(bindings)
    names = dict(bindings)
    channels = tuple(
        ProtocolChannel(
            channel, tuple(signal for signal in signals if signal in names), "independent", condition, evidence_refs
        )
        for channel, signals, condition in (
            ("AW", ("awvalid", "awready"), "AWVALID && AWREADY"),
            ("W", ("wvalid", "wready"), "WVALID && WREADY"),
            ("B", ("bvalid", "bready"), "BVALID && BREADY"),
            ("AR", ("arvalid", "arready"), "ARVALID && ARREADY"),
            ("R", ("rvalid", "rready"), "RVALID && RREADY"),
        )
    )
    return ProtocolModel(
        "AXI4-Lite",
        "4.0",
        channels,
        bindings,
        ordering_rules=("write address and data channels are independent",),
        response_rules=("write response follows accepted write", "read data follows accepted address"),
        confidence="explicit",
        evidence_refs=evidence_refs,
        profile_id="axi4-lite-1.0",
        scoreboard_keys=("address", "sequence"),
        coverage_bins=("response", "backpressure", "byte_enable"),
        formal_properties=("payload stable while stalled", "accepted request eventually completes"),
        result_traces=("accepted_writes", "write_responses", "accepted_reads", "read_responses"),
    )


def apb4_model(bindings: tuple[tuple[str, str], ...], evidence_refs: tuple[EvidenceRef, ...]) -> ProtocolModel:
    bindings = tuple(bindings)
    return ProtocolModel(
        "APB4",
        "4.0",
        (
            ProtocolChannel(
                "transfer", tuple(dict(bindings)), "master_to_slave", "PSEL && PENABLE && PREADY", evidence_refs
            ),
        ),
        bindings,
        ordering_rules=("setup precedes access",),
        response_rules=("completion requires PREADY",),
        confidence="explicit",
        evidence_refs=evidence_refs,
        profile_id="apb4-legacy",
        scoreboard_keys=("address", "sequence"),
        coverage_bins=("response", "wait_states", "byte_enable"),
        formal_properties=("setup precedes access", "control stable during wait states"),
        result_traces=("transfer", "address", "response"),
    )


for _name, _value in tuple(globals().items()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.agent.protocols"


def ahb_lite_model(bindings: tuple[tuple[str, str], ...], evidence_refs: tuple[EvidenceRef, ...]) -> ProtocolModel:
    """Construct the bounded single-beat AHB-Lite control-plane model."""

    bindings = tuple(bindings)
    names = dict(bindings)
    channels = (
        ProtocolChannel(
            "transfer",
            tuple(signal for signal in ("hsel", "htrans", "hready") if signal in names),
            "master_to_slave",
            "HSEL && HTRANS[1] && HREADY",
            evidence_refs,
        ),
        ProtocolChannel(
            "write_data",
            tuple(signal for signal in ("hwrite", "hwdata") if signal in names),
            "master_to_slave",
            "HSEL && HTRANS[1] && HWRITE && HREADY",
            evidence_refs,
        ),
        ProtocolChannel(
            "read_response",
            tuple(signal for signal in ("hrdata", "hresp") if signal in names),
            "slave_to_master",
            "HSEL && HTRANS[1] && !HWRITE && HREADY",
            evidence_refs,
        ),
    )
    return ProtocolModel(
        "AHB-Lite",
        "3.0",
        channels,
        bindings,
        ordering_rules=("address/control phase precedes data phase", "single master ordering is preserved"),
        response_rules=("transfer completes when HREADY is asserted",),
        error_behavior="HRESP indicates transfer error",
        confidence="explicit",
        evidence_refs=evidence_refs,
        profile_id="ahb-lite-legacy",
        scoreboard_keys=("address", "sequence"),
        coverage_bins=("response", "wait_states"),
        formal_properties=("address/control phase precedes data phase",),
        result_traces=("transfer", "address", "response"),
    )
