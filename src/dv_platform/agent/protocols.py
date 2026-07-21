"""Typed control-plane protocol and register models."""

from __future__ import annotations

from dataclasses import dataclass

from dv_platform.core.models import EvidenceRef


@dataclass(frozen=True)
class ProtocolChannel:
    name: str
    signals: tuple[str, ...]
    direction: str
    transfer_condition: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


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

    def validate(self, evidence_ids: set[str]) -> None:
        refs = self.evidence_refs + tuple(ref for channel in self.channels for ref in channel.evidence_refs)
        missing = [ref for ref in refs if ref.source_id not in evidence_ids and ref.locator not in evidence_ids]
        if missing:
            raise ValueError("protocol model contains evidence outside task context")


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
    )


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
    )
