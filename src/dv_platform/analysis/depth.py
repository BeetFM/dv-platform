"""Deterministic verification-depth intent derived from normalized RTL facts."""

from __future__ import annotations

import math

from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    Severity,
    VerificationClaim,
    VerificationDepthPolicy,
)
from dv_platform.core.peripherals import PERIPHERAL_CONTRACTS


def build_depth_checks(
    module: RTLModule,
    policies: tuple[VerificationDepthPolicy, ...] = (),
) -> tuple[str, ...]:
    """Return conservative closure checks for reset, memory, protocol, and CDC facts."""

    checks: list[str] = []
    for domain in module.control_domains:
        if domain.reset is None:
            continue
        checks.append(
            f"Cover reset {domain.reset} assertion and release for control domain {domain.domain_id} on {domain.clock}."
        )
        if domain.asynchronous_reset:
            checks.append(
                f"Verify asynchronous reset {domain.reset} assertion and clocked release for control domain "
                f"{domain.domain_id} on {domain.clock}."
            )

    memories = {memory.name: memory for memory in module.memories}
    for access in module.memory_accesses:
        memory = memories.get(access.memory)
        if memory is None or not access.synchronous or len(access.address_signals) != 1:
            continue
        if access.kind == "write" and access.enable_signals and memory.depth is not None:
            checks.append(
                f"Cover memory {memory.name} write access {access.access_id} at the lowest and highest legal addresses."
            )
        if access.kind == "read" and len(access.data_signals) == 1:
            checks.append(
                f"Verify synchronous read access {access.access_id} from memory {memory.name} returns the selected element."
            )

    for protocol in module.protocols:
        checks.append(f"Cover {protocol.name} transfer with {protocol.valid} and {protocol.ready} asserted together.")
        checks.append(f"Cover {protocol.name} backpressure followed by a successful transfer.")

    for path in module.cdc_paths:
        if path.safe:
            checks.append(
                f"Cover synchronized CDC path {path.signal} propagation from {path.source_domain} to "
                f"{path.destination_domain}."
            )
        else:
            checks.append(
                f"Resolve unsafe CDC path {path.signal} from {path.source_domain} to {path.destination_domain} before closure."
            )
    for policy in policies:
        if policy.kind == "reset":
            cycles = policy.parameter("release_cycles") or "2"
            checks.append(
                f"Verify configured reset {policy.subject} release completes within {cycles} cycles for {policy.module}."
            )
            recovery = policy.parameter("recovery_cycles") or "1"
            removal = policy.parameter("removal_cycles") or "1"
            checks.append(
                f"Verify configured reset {policy.subject} recovery/removal intent uses {recovery}/{removal} guarded cycles."
            )
            dependency = policy.parameter("depends_on_reset")
            if dependency:
                checks.append(
                    f"Verify configured reset {policy.subject} remains held until dependency reset {dependency} is released."
                )
        elif policy.kind == "memory":
            collision = policy.parameter("read_during_write")
            if collision is not None and collision != "undefined":
                checks.append(f"Verify configured memory {policy.subject} read-during-write behavior is {collision}.")
            if policy.parameter("profile") == "bounded_sram":
                checks.extend(
                    (
                        f"Verify configured memory {policy.subject} merges only byte-enabled write lanes.",
                        f"Verify configured memory {policy.subject} round-robin arbitration is exclusive and starvation bounded.",
                        f"Verify configured memory {policy.subject} zero initialization at every legal address.",
                        (
                            f"Verify configured memory {policy.subject} corrects single-bit errors, detects double-bit errors, and scrubs repaired words."
                            if policy.parameter("protection") == "secded"
                            else f"Verify configured memory {policy.subject} parity detects an injected single-bit error."
                        ),
                    )
                )
        elif policy.kind == "formal":
            latency = policy.parameter("max_latency_cycles") or "unspecified"
            checks.extend(
                (
                    f"Verify configured formal contract {policy.subject} responds within {latency} cycles.",
                    f"Verify configured formal contract {policy.subject} preserves its induction invariant.",
                    f"Cover configured formal contract {policy.subject} assumption consistency and non-vacuity.",
                )
            )
        elif policy.kind == "cdc":
            structure = policy.parameter("structure") or "configured"
            latency = policy.parameter("max_latency_cycles") or "unspecified"
            checks.append(
                f"Verify configured CDC path {policy.subject} uses {structure} structure and propagates within "
                f"{latency} destination cycles."
            )
        elif policy.kind == "uart":
            checks.extend(
                (
                    f"Verify UART {policy.subject} TX/RX baud timing and serial data ordering.",
                    f"Verify UART {policy.subject} framing, parity, stop-bit, and break behavior.",
                    f"Verify UART {policy.subject} overflow reporting and reset recovery.",
                )
            )
        elif policy.kind == "spi":
            checks.extend(
                (
                    f"Verify SPI {policy.subject} CPOL/CPHA modes 0 through 3 and sampled data.",
                    f"Verify SPI {policy.subject} chip-select timing and MSB/LSB bit ordering.",
                )
            )
        elif policy.kind == "i2c":
            checks.extend(
                (
                    f"Verify I2C {policy.subject} open-drain wired-AND signaling and START/STOP/repeated START.",
                    f"Verify I2C {policy.subject} ACK/NACK and bounded clock stretching.",
                    f"Verify I2C {policy.subject} arbitration loss, bus-busy handling, and recovery.",
                )
            )
        elif policy.kind == "gpio_timer_interrupt":
            checks.extend(
                (
                    f"Verify GPIO {policy.subject} direction, masked writes, set/clear, and edge/level interrupts.",
                    f"Verify timer {policy.subject} prescaling, compare, rollover, periodic mode, and interrupt clear.",
                    f"Verify watchdog {policy.subject} feed, timeout interrupt, and reset request.",
                    f"Verify PWM {policy.subject} period, duty boundaries, update timing, and polarity.",
                    f"Verify interrupt controller {policy.subject} mask, pending, clear, fixed priority, and simultaneous sources.",
                )
            )
    return tuple(dict.fromkeys(checks))


def validate_depth_policies(
    module: RTLModule,
    policies: tuple[VerificationDepthPolicy, ...],
    config_source: str = "dv-platform.toml",
) -> tuple[VerificationClaim, ...]:
    """Validate configured depth intent against deterministic normalized facts."""

    claims: list[VerificationClaim] = []
    cyclic_resets = _cyclic_reset_subjects(policies)
    for policy in policies:
        ref = EvidenceRef(
            EvidenceKind.CONFIGURATION,
            config_source,
            f"verification_depth:{policy.kind}/{policy.module}/{policy.subject}",
            "Explicit project verification-depth policy.",
        )
        status = ClaimStatus.SUPPORTED
        statement = (
            f"Configured {policy.kind} verification policy for {policy.subject} resolves to normalized RTL facts."
        )
        if policy.kind == "memory":
            status, statement = _validate_memory_policy(module, policy, statement)
        elif policy.kind == "formal":
            status, statement = _validate_formal_policy(module, policy, statement)
        elif policy.kind == "reset":
            status, statement = _validate_reset_policy(module, policy, statement)
            if policy.subject in cyclic_resets:
                status = ClaimStatus.CONTRADICTED
                statement = "Configured reset dependency graph contains a cycle."
        elif policy.kind == "cdc":
            status, statement = _validate_cdc_policy(module, policy, statement)
        elif policy.kind in PERIPHERAL_CONTRACTS:
            status, statement = _validate_peripheral_policy(module, policy, statement)
        claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:depth-policy:{policy.kind}:{policy.subject}",
                scope=module.name,
                statement=statement,
                claim_type=ClaimType.DOCUMENTATION_INTENT,
                severity=Severity.CRITICAL,
                generation_precondition=True,
                status=status,
                evidence_refs=(ref,),
            )
        )
    return tuple(claims)


def _validate_peripheral_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    """Validate a complete peripheral mapping without inferring signal intent."""

    contract = PERIPHERAL_CONTRACTS[policy.kind]
    if policy.parameter("profile") != contract.profile:
        return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} policy has no qualified executable profile."
    integer_values: dict[str, int] = {}
    for name, minimum, maximum in contract.integer_parameters:
        value = policy.parameter(name)
        if value is None or not value.isdecimal():
            return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} policy is missing bounded parameter {name}."
        integer_values[name] = int(value)
        if not minimum <= integer_values[name] <= maximum:
            return ClaimStatus.CONTRADICTED, f"{policy.kind} parameter {name} is outside the qualified range."
    for name, permitted in contract.enum_parameters:
        if policy.parameter(name) not in permitted:
            return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} policy is missing qualified {name} intent."

    mappings = {signal.name: policy.parameter(signal.name) for signal in contract.signals}
    if any(not value for value in mappings.values()):
        return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} policy is missing a required signal mapping."
    if len(set(mappings.values())) != len(mappings):
        return ClaimStatus.CONTRADICTED, f"{policy.kind} signal mappings must be distinct."
    ports = {port.name: port for port in module.port_details}
    if any(value not in ports for value in mappings.values()):
        return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} signals are not all observable module ports."
    for signal in contract.signals:
        port = ports[mappings[signal.name] or ""]
        if port.direction != signal.direction:
            return ClaimStatus.CONTRADICTED, (
                f"{policy.kind} mapping {signal.name} must be a module {signal.direction}."
            )
        expected_width = _peripheral_signal_width(signal.width, integer_values)
        actual_width = port.width or 1
        if actual_width != expected_width:
            return ClaimStatus.CONTRADICTED, (
                f"{policy.kind} mapping {signal.name} width {actual_width} does not match {expected_width}."
            )

    clock = mappings["clock"]
    reset = mappings["reset"]
    domains = tuple(domain for domain in module.control_domains if domain.clock == clock and domain.reset == reset)
    resets = tuple(item for item in module.reset_details if item.name == reset and item.active_low is not None)
    if len(domains) != 1 or len(resets) != 1:
        return ClaimStatus.MISSING_EVIDENCE, (
            f"{policy.kind} clock/reset mapping must resolve to one normalized domain with known polarity."
        )
    return ClaimStatus.SUPPORTED, default_statement


def _peripheral_signal_width(width: int | str, values: dict[str, int]) -> int:
    if isinstance(width, int):
        return width
    if width == "irq_index_width":
        return max(1, math.ceil(math.log2(values["irq_sources"])))
    return values[width]


def _validate_formal_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    if policy.parameter("profile") != "bounded_response":
        return ClaimStatus.MISSING_EVIDENCE, "Formal policy has no qualified executable profile."
    required = ("clock", "reset", "trigger_signal", "response_signal", "invariant_signal")
    values = {name: policy.parameter(name) for name in required}
    if any(not value for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Bounded-response policy is missing a required signal mapping."
    if len(set(values.values())) != len(values):
        return ClaimStatus.CONTRADICTED, "Bounded-response signal mappings must be distinct."
    ports = {port.name: port for port in module.port_details}
    if any(value not in ports for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Bounded-response signals are not all observable ports."
    if ports[values["clock"] or ""].direction != "input" or ports[values["reset"] or ""].direction != "input":
        return ClaimStatus.CONTRADICTED, "Bounded-response clock and reset must be inputs."
    if ports[values["trigger_signal"] or ""].direction != "input":
        return ClaimStatus.CONTRADICTED, "Bounded-response trigger must be an input."
    if any(ports[values[name] or ""].direction != "output" for name in ("response_signal", "invariant_signal")):
        return ClaimStatus.CONTRADICTED, "Bounded-response response and invariant must be outputs."
    if any(ports[value or ""].width not in {None, 1} for value in values.values()):
        return ClaimStatus.CONTRADICTED, "Bounded-response mappings must be scalar."
    domains = tuple(
        domain
        for domain in module.control_domains
        if domain.clock == values["clock"] and domain.reset == values["reset"]
    )
    if len(domains) != 1:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded-response clock/reset does not resolve to one control domain."
    if policy.parameter("assume_trigger_pulse") != "true":
        return ClaimStatus.MISSING_EVIDENCE, "Qualified bounded-response intent requires a pulse assumption."
    if policy.parameter("require_response_causality") != "true":
        return ClaimStatus.MISSING_EVIDENCE, "Qualified bounded-response intent requires response causality."
    return ClaimStatus.SUPPORTED, default_statement


def _validate_memory_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    """Validate the deliberately bounded, executable synchronous SRAM profile."""

    memory = next((item for item in module.memories if item.name == policy.subject), None)
    if memory is None:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured memory {policy.subject} is not normalized."
    if policy.parameter("profile") != "bounded_sram":
        return ClaimStatus.MISSING_EVIDENCE, "Memory policy has no qualified executable profile."
    if memory.depth is None or memory.depth < 2 or memory.address_width is None or memory.element_width is None:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM depth, address width, and element width must be known."
    if memory.element_width < 8 or memory.element_width % 8:
        return ClaimStatus.CONTRADICTED, "Bounded SRAM elements must contain a whole number of bytes."
    if policy.parameter("read_during_write") not in {"read_first", "write_first", "no_change"}:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM requires a defined read-during-write policy."
    if memory.read_during_write not in {"unknown", policy.parameter("read_during_write")}:
        return ClaimStatus.CONTRADICTED, "Configured collision behavior contradicts normalized memory facts."
    if policy.parameter("initialization") != "zero":
        return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires zero initialization."
    if policy.parameter("arbitration") != "round_robin":
        return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires round-robin arbitration."
    protection = policy.parameter("protection")
    if protection not in {"parity", "secded"}:
        return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires parity or SECDED protection."

    required = (
        "clock",
        "reset",
        "read_enable",
        "read_address",
        "read_data",
        "port0_request",
        "port0_write_enable",
        "port0_address",
        "port0_write_data",
        "port0_byte_enable",
        "port0_grant",
        "port1_request",
        "port1_write_enable",
        "port1_address",
        "port1_write_data",
        "port1_byte_enable",
        "port1_grant",
    )
    protection_signals = (
        ("error_signal", "inject_error")
        if protection == "parity"
        else (
            "corrected_error_signal",
            "uncorrectable_error_signal",
            "inject_single_error",
            "inject_double_error",
            "scrub_enable",
            "scrub_done",
        )
    )
    required = (*required, *protection_signals)
    values = {name: policy.parameter(name) for name in required}
    if any(not value for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM policy is missing a required signal mapping."
    if len(set(values.values())) != len(values):
        return ClaimStatus.CONTRADICTED, "Bounded SRAM signal mappings must be distinct."
    ports = {port.name: port for port in module.port_details}
    if any(value not in ports for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM signals are not all observable module ports."
    inputs = {
        "clock",
        "reset",
        "read_enable",
        "read_address",
        "port0_request",
        "port0_write_enable",
        "port0_address",
        "port0_write_data",
        "port0_byte_enable",
        "port1_request",
        "port1_write_enable",
        "port1_address",
        "port1_write_data",
        "port1_byte_enable",
        *(protection_signals[1:] if protection == "parity" else protection_signals[2:5]),
    }
    outputs = set(required) - inputs
    if any(ports[values[name] or ""].direction != "input" for name in inputs):
        return ClaimStatus.CONTRADICTED, "Bounded SRAM driven signals must be inputs."
    if any(ports[values[name] or ""].direction != "output" for name in outputs):
        return ClaimStatus.CONTRADICTED, "Bounded SRAM observed signals must be outputs."
    scalar = {
        "clock",
        "reset",
        "read_enable",
        "port0_request",
        "port0_write_enable",
        "port0_grant",
        "port1_request",
        "port1_write_enable",
        "port1_grant",
        *protection_signals,
    }
    if any(ports[values[name] or ""].width not in {None, 1} for name in scalar):
        return ClaimStatus.CONTRADICTED, "Bounded SRAM controls and status signals must be scalar."
    for name in ("read_address", "port0_address", "port1_address"):
        if ports[values[name] or ""].width != memory.address_width:
            return ClaimStatus.CONTRADICTED, "Bounded SRAM address width contradicts normalized memory shape."
    for name in ("read_data", "port0_write_data", "port1_write_data"):
        if ports[values[name] or ""].width != memory.element_width:
            return ClaimStatus.CONTRADICTED, "Bounded SRAM data width contradicts normalized memory shape."
    for name in ("port0_byte_enable", "port1_byte_enable"):
        if ports[values[name] or ""].width != memory.element_width // 8:
            return ClaimStatus.CONTRADICTED, "Bounded SRAM byte-enable width does not match its data width."

    domains = tuple(
        domain
        for domain in module.control_domains
        if domain.clock == values["clock"] and domain.reset == values["reset"]
    )
    if len(domains) != 1:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM clock/reset does not resolve to one control domain."
    accesses = tuple(
        access for access in module.memory_accesses if access.memory == policy.subject and access.synchronous
    )
    if not any(access.kind == "read" for access in accesses) or not any(access.kind == "write" for access in accesses):
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM needs normalized synchronous read and write accesses."
    if any(access.domain_id != domains[0].domain_id for access in accesses):
        return ClaimStatus.CONTRADICTED, "Bounded SRAM accesses do not share the configured control domain."
    return ClaimStatus.SUPPORTED, default_statement


def _cyclic_reset_subjects(policies: tuple[VerificationDepthPolicy, ...]) -> set[str]:
    graph = {
        policy.subject: policy.parameter("depends_on_reset")
        for policy in policies
        if policy.kind == "reset" and policy.parameter("depends_on_reset")
    }
    cyclic: set[str] = set()
    for subject in graph:
        chain: list[str] = []
        current: str | None = subject
        while current in graph:
            if current in chain:
                cyclic.update(chain[chain.index(current) :])
                break
            chain.append(current)
            current = graph[current]
    return cyclic


def _validate_reset_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    resets = tuple(reset for reset in module.reset_details if reset.name == policy.subject)
    if len(resets) != 1:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured reset {policy.subject} does not resolve uniquely."
    domains = tuple(domain for domain in module.control_domains if domain.reset == policy.subject)
    if len(domains) != 1:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured reset {policy.subject} does not own one control domain."
    domain = domains[0]
    expected_domain = policy.parameter("domain")
    expected_clock = policy.parameter("clock")
    if expected_domain is not None and expected_domain != domain.domain_id:
        return ClaimStatus.CONTRADICTED, f"Configured reset domain {expected_domain} contradicts {domain.domain_id}."
    if expected_clock is not None and expected_clock != domain.clock:
        return ClaimStatus.CONTRADICTED, f"Configured reset clock {expected_clock} contradicts {domain.clock}."
    expected_async = policy.parameter("asynchronous_assertion")
    if expected_async is not None and (expected_async == "true") != domain.asynchronous_reset:
        return ClaimStatus.CONTRADICTED, "Configured reset assertion style contradicts the normalized control domain."
    ready = policy.parameter("ready_signal")
    ports = {port.name: port for port in module.port_details}
    if not ready or ready not in ports or ports[ready].direction != "output" or ports[ready].width not in {None, 1}:
        return ClaimStatus.MISSING_EVIDENCE, "Configured reset requires an observable scalar ready output."
    power_good = policy.parameter("power_good_signal")
    isolation = policy.parameter("isolation_signal")
    retention = policy.parameter("retention_signal")
    power_fields = (power_good, isolation, retention)
    if any(power_fields) and not all(power_fields):
        return (
            ClaimStatus.MISSING_EVIDENCE,
            "Configured power sequence requires power-good, isolation, and retention mappings.",
        )
    if power_good is not None:
        if any(signal not in ports for signal in power_fields):
            return ClaimStatus.MISSING_EVIDENCE, "Configured power-sequence signals are not observable ports."
        if ports[power_good].direction != "input" or any(
            ports[signal or ""].direction != "output" for signal in (isolation, retention)
        ):
            return ClaimStatus.CONTRADICTED, "Power good must be an input and isolation/retention must be outputs."
        if any(ports[signal or ""].width not in {None, 1} for signal in power_fields):
            return ClaimStatus.CONTRADICTED, "Configured power-sequence signals must be scalar."
        if len(set(filter(None, (*power_fields, ready)))) != 4:
            return ClaimStatus.CONTRADICTED, "Configured power-sequence mappings must be distinct."
    dependency_reset = policy.parameter("depends_on_reset")
    dependency_ready = policy.parameter("depends_on_ready")
    dependency_sync = policy.parameter("dependency_sync_signal")
    dependency_fields = (dependency_reset, dependency_ready, dependency_sync)
    if any(dependency_fields) and not all(dependency_fields):
        return ClaimStatus.MISSING_EVIDENCE, "Configured ordered reset requires all dependency signal mappings."
    if dependency_reset is None:
        return ClaimStatus.SUPPORTED, default_statement
    if dependency_reset == policy.subject:
        return ClaimStatus.CONTRADICTED, "Configured reset cannot depend on itself."
    dependency_domains = tuple(item for item in module.control_domains if item.reset == dependency_reset)
    if len(dependency_domains) != 1 or dependency_domains[0].domain_id == domain.domain_id:
        return ClaimStatus.CONTRADICTED, "Configured reset dependency is not a distinct normalized control domain."
    if any(signal not in ports for signal in (dependency_ready, dependency_sync)):
        return ClaimStatus.MISSING_EVIDENCE, "Configured reset dependency signals are not observable ports."
    if ports[dependency_ready or ""].direction != "output" or ports[dependency_sync or ""].direction != "output":
        return ClaimStatus.CONTRADICTED, "Configured reset dependency signals must be observable outputs."
    paths = tuple(
        path
        for path in module.cdc_paths
        if path.signal == dependency_ready and path.destination_domain == domain.domain_id
    )
    if len(paths) != 1:
        return ClaimStatus.MISSING_EVIDENCE, "Configured reset-domain crossing does not resolve uniquely."
    path = paths[0]
    if (
        path.classification not in {"two_flop", "synchronizer"}
        or path.synchronizer_stages < 2
        or len(path.stage_signals) != path.synchronizer_stages
        or path.stage_signals[-1] != dependency_sync
    ):
        return ClaimStatus.CONTRADICTED, "Configured reset-domain dependency is not a qualified synchronizer."
    return ClaimStatus.SUPPORTED, default_statement


def _validate_cdc_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    structure = policy.parameter("structure")
    if structure == "async_fifo":
        return _validate_async_fifo_policy(module, policy, default_statement)
    paths = tuple(path for path in module.cdc_paths if path.signal == policy.subject)
    if len(paths) != 1:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured CDC signal {policy.subject} does not resolve uniquely."
    path = paths[0]
    source = policy.parameter("source_domain")
    destination = policy.parameter("destination_domain")
    if source is not None and source != path.source_domain:
        return ClaimStatus.CONTRADICTED, f"Configured CDC source domain {source} contradicts {path.source_domain}."
    if destination is not None and destination != path.destination_domain:
        return ClaimStatus.CONTRADICTED, (
            f"Configured CDC destination domain {destination} contradicts {path.destination_domain}."
        )
    if structure not in {"two_flop", "pulse", "toggle", "gray", "handshake", "multi_bit_handshake"}:
        return ClaimStatus.MISSING_EVIDENCE, (
            f"Configured CDC structure {structure or 'unspecified'} is not qualified by the synchronizer backend."
        )
    minimum = int(policy.parameter("min_stages") or "2")
    qualified_classifications = {"two_flop", "synchronizer"}
    if structure in {"pulse", "toggle", "gray", "handshake"}:
        qualified_classifications.add(structure)
    elif structure == "multi_bit_handshake":
        qualified_classifications.add("handshake")
    if path.classification not in qualified_classifications or path.synchronizer_stages < minimum:
        return ClaimStatus.CONTRADICTED, (
            f"Configured CDC requires at least {minimum} stages but RTL has {path.synchronizer_stages}."
        )
    if len(path.stage_signals) != path.synchronizer_stages:
        return ClaimStatus.MISSING_EVIDENCE, "Configured CDC stage chain lacks unambiguous ordered stage signals."
    output_signal = policy.parameter("output_signal")
    if output_signal is not None and output_signal != path.stage_signals[-1]:
        return ClaimStatus.CONTRADICTED, (
            f"Configured CDC output {output_signal or 'unspecified'} does not match final stage "
            f"{path.stage_signals[-1]}."
        )
    if structure in {"pulse", "toggle", "gray", "handshake", "multi_bit_handshake"} and output_signal is None:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured {structure} CDC requires output_signal."
    if structure == "pulse":
        stretch = int(policy.parameter("pulse_stretch_cycles") or "0")
        if stretch < path.synchronizer_stages:
            return ClaimStatus.CONTRADICTED, (
                f"Configured pulse stretch {stretch} is shorter than the {path.synchronizer_stages}-stage chain."
            )
    if structure == "gray":
        if policy.parameter("max_source_steps_per_destination") != "1":
            return (
                ClaimStatus.MISSING_EVIDENCE,
                "Configured Gray counter requires max_source_steps_per_destination = 1.",
            )
        ports = {port.name: port for port in module.port_details}
        source_port = ports.get(path.signal)
        observed_port = ports.get(output_signal or "")
        if source_port is None or observed_port is None:
            return ClaimStatus.MISSING_EVIDENCE, "Configured Gray counter source and output must be observable ports."
        if source_port.width != observed_port.width or source_port.width in {None, 1}:
            return ClaimStatus.CONTRADICTED, "Configured Gray counter requires matching known widths above one bit."
    if structure in {"handshake", "multi_bit_handshake"}:
        ack_input = policy.parameter("ack_input_signal")
        ack_output = policy.parameter("ack_output_signal")
        if not ack_input or not ack_output:
            return ClaimStatus.MISSING_EVIDENCE, "Configured handshake requires ack_input_signal and ack_output_signal."
        reverse = tuple(
            candidate
            for candidate in module.cdc_paths
            if candidate.signal == ack_input
            and candidate.source_domain == path.destination_domain
            and candidate.destination_domain == path.source_domain
        )
        if path.source_domain == "external":
            reverse = tuple(candidate for candidate in module.cdc_paths if candidate.signal == ack_input)
        if len(reverse) != 1:
            return ClaimStatus.MISSING_EVIDENCE, "Configured handshake acknowledgement path does not resolve uniquely."
        ack_path = reverse[0]
        if (
            not ack_path.safe
            or ack_path.synchronizer_stages < minimum
            or not ack_path.stage_signals
            or ack_path.stage_signals[-1] != ack_output
        ):
            return ClaimStatus.CONTRADICTED, "Configured handshake acknowledgement is not a qualified synchronizer."
    known_signals = {port.name for port in module.port_details} | set(module.ports)
    data_signals = tuple(filter(None, (policy.parameter("data_signals") or "").split(",")))
    if any(signal not in known_signals for signal in data_signals):
        return ClaimStatus.MISSING_EVIDENCE, "Configured handshake data signals are not observable module ports."
    if structure == "multi_bit_handshake":
        observed = tuple(filter(None, (policy.parameter("observed_data_signals") or "").split(",")))
        if not data_signals or len(observed) != len(data_signals):
            return (
                ClaimStatus.MISSING_EVIDENCE,
                "Configured multi-bit handshake requires paired data_signals and observed_data_signals.",
            )
        ports = {port.name: port for port in module.port_details}
        if any(signal not in ports for signal in observed):
            return ClaimStatus.MISSING_EVIDENCE, "Configured observed handshake data is not observable."
        for source_signal, observed_signal in zip(data_signals, observed, strict=True):
            source_port = ports.get(source_signal)
            observed_port = ports[observed_signal]
            if source_port is None or source_port.direction != "input" or observed_port.direction != "output":
                return (
                    ClaimStatus.CONTRADICTED,
                    "Multi-bit handshake data must map input sources to output observations.",
                )
            if source_port.width != observed_port.width or source_port.width in {None, 1}:
                return (
                    ClaimStatus.CONTRADICTED,
                    "Multi-bit handshake data mappings require matching known widths above one bit.",
                )
    expected_reset = policy.parameter("reset_compatible")
    if expected_reset == "true" and path.reset_compatible is False:
        return ClaimStatus.CONTRADICTED, "Configured CDC reset compatibility contradicts normalized reset domains."
    if expected_reset == "true" and path.reset_compatible is None:
        return ClaimStatus.MISSING_EVIDENCE, "Configured CDC reset compatibility cannot be proven from reset domains."
    return ClaimStatus.SUPPORTED, default_statement


def _validate_async_fifo_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    memory = next((item for item in module.memories if item.name == policy.subject), None)
    if memory is None:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured async FIFO memory {policy.subject} is not normalized."
    if memory.depth is None or memory.depth < 2 or memory.depth & (memory.depth - 1):
        return ClaimStatus.CONTRADICTED, "Configured async FIFO depth must be a known power of two."
    if memory.element_width is None or memory.address_width is None:
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO memory width and address width must be known."

    required = (
        "write_clock",
        "write_reset",
        "write_enable",
        "write_data",
        "write_binary_pointer",
        "write_gray_pointer",
        "write_gray_sync",
        "full_signal",
        "read_clock",
        "read_reset",
        "read_enable",
        "read_data",
        "read_binary_pointer",
        "read_gray_pointer",
        "read_gray_sync",
        "empty_signal",
    )
    values = {name: policy.parameter(name) for name in required}
    if any(not value for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO policy is missing a required signal mapping."
    ports = {port.name: port for port in module.port_details}
    if any(value not in ports for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO signals are not all observable module ports."
    if values["write_clock"] == values["read_clock"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO requires distinct write and read clocks."

    domains = {domain.domain_id: domain for domain in module.control_domains}
    writes = tuple(
        access
        for access in module.memory_accesses
        if access.memory == policy.subject and access.kind == "write" and access.synchronous
    )
    reads = tuple(
        access
        for access in module.memory_accesses
        if access.memory == policy.subject and access.kind == "read" and access.synchronous
    )
    if len(writes) != 1 or len(reads) != 1:
        return (
            ClaimStatus.MISSING_EVIDENCE,
            "Configured async FIFO requires one unambiguous synchronous read and write access.",
        )
    write_domain = domains.get(writes[0].domain_id or "")
    read_domain = domains.get(reads[0].domain_id or "")
    if write_domain is None or read_domain is None or write_domain.domain_id == read_domain.domain_id:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO accesses are not in distinct normalized clock domains."
    if write_domain.clock != values["write_clock"] or read_domain.clock != values["read_clock"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO clocks contradict normalized memory access domains."
    if write_domain.reset != values["write_reset"] or read_domain.reset != values["read_reset"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO resets contradict normalized memory access domains."
    if values["write_enable"] not in writes[0].enable_signals or values["write_data"] not in writes[0].data_signals:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO write mapping contradicts the normalized memory access."
    if values["read_enable"] not in reads[0].enable_signals or values["read_data"] not in reads[0].data_signals:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO read mapping contradicts the normalized memory access."

    pointer_width = memory.address_width + 1
    for name in (
        "write_binary_pointer",
        "write_gray_pointer",
        "write_gray_sync",
        "read_binary_pointer",
        "read_gray_pointer",
        "read_gray_sync",
    ):
        if ports[values[name] or ""].width != pointer_width:
            return (
                ClaimStatus.CONTRADICTED,
                f"Configured async FIFO {name} width does not match depth-derived pointer width.",
            )
    if (
        ports[values["write_data"] or ""].width != memory.element_width
        or ports[values["read_data"] or ""].width != memory.element_width
    ):
        return (
            ClaimStatus.CONTRADICTED,
            "Configured async FIFO data widths contradict the normalized memory element width.",
        )
    if any(
        ports[values[name] or ""].width not in {None, 1}
        for name in ("write_enable", "read_enable", "full_signal", "empty_signal")
    ):
        return ClaimStatus.CONTRADICTED, "Configured async FIFO enables and status flags must be scalar."

    minimum = int(policy.parameter("min_stages") or "2")
    crossings = (
        (values["write_gray_pointer"], values["write_gray_sync"], read_domain.domain_id),
        (values["read_gray_pointer"], values["read_gray_sync"], write_domain.domain_id),
    )
    for source, output, destination in crossings:
        matching = tuple(
            path for path in module.cdc_paths if path.signal == source and path.destination_domain == destination
        )
        if len(matching) != 1:
            return (
                ClaimStatus.MISSING_EVIDENCE,
                "Configured async FIFO Gray-pointer crossing does not resolve uniquely.",
            )
        path = matching[0]
        if (
            path.classification not in {"two_flop", "synchronizer"}
            or path.synchronizer_stages < minimum
            or not path.stage_signals
            or path.stage_signals[-1] != output
        ):
            return (
                ClaimStatus.CONTRADICTED,
                "Configured async FIFO Gray-pointer crossing is not a qualified synchronizer.",
            )
    return ClaimStatus.SUPPORTED, default_statement
