"""Shared UVM naming and protocol-selection helpers."""

from __future__ import annotations

from collections.abc import Iterable

from dv_platform.core.models import EvidenceRef, RTLProtocol, VerificationPlan


def _paired_protocol(plan: VerificationPlan) -> tuple[RTLProtocol, RTLProtocol] | None:
    sinks = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "sink" and protocol.data is not None
    )
    sources = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source" and protocol.data is not None
    )
    if len(sinks) != 1 or len(sources) != 1 or sinks[0].kind != sources[0].kind:
        return None
    if sinks[0].clock and sources[0].clock and sinks[0].clock != sources[0].clock:
        return None
    return sinks[0], sources[0]


def _connections(ports: tuple[str, ...], module_name: str, clock_name: str) -> list[str]:
    connections: list[str] = []
    for port in ports:
        signal = clock_name if port == clock_name else "vif." + port
        connections.append("        ." + port + "(" + signal + ")")
    return connections


def _port_names_from_plan(plan: VerificationPlan) -> tuple[str, ...]:
    ports: list[str] = []
    prefix = f"port:{plan.module}."
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            locator = ref.locator.split("@", 1)[0]
            if locator.startswith(prefix):
                ports.append(locator.removeprefix(prefix))
    return tuple(dict.fromkeys(ports))


def _clock_name(ports: tuple[str, ...]) -> str | None:
    return next((port for port in ports if port in {"clk", "clock"} or port.endswith(("_clk", "_clock"))), None)


def _comma_terminate(lines: Iterable[str]) -> list[str]:
    values = list(lines)
    return [line + ("," if index < len(values) - 1 else "") for index, line in enumerate(values)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
