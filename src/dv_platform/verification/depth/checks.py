# mypy: disable-error-code=name-defined
# ruff: noqa: F821
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
from dv_platform.core.peripherals import PERIPHERAL_CONTRACTS, PERIPHERAL_PROFILE_CONTRACTS


def build_depth_checks(
    module: RTLModule,
    policies: tuple[VerificationDepthPolicy, ...] = (),
) -> tuple[str, ...]:
    """Return conservative closure checks for reset, memory, protocol, and CDC facts."""

    checks = _depth_fact_checks(module)
    for policy in policies:
        checks.extend(_depth_policy_checks(policy))
    return tuple(dict.fromkeys(checks))


def _depth_fact_checks(module: RTLModule) -> list[str]:
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
                f"Resolve unsafe CDC path {path.signal} from {path.source_domain} to "
                f"{path.destination_domain} before closure."
            )
    return checks


def _depth_policy_checks(policy: VerificationDepthPolicy) -> tuple[str, ...]:
    if policy.kind == "reset":
        cycles = policy.parameter("release_cycles") or "2"
        recovery = policy.parameter("recovery_cycles") or "1"
        removal = policy.parameter("removal_cycles") or "1"
        checks = [
            f"Verify configured reset {policy.subject} release completes within {cycles} cycles for {policy.module}.",
            f"Verify configured reset {policy.subject} recovery/removal intent uses {recovery}/{removal} guarded cycles.",
        ]
        dependency = policy.parameter("depends_on_reset")
        if dependency:
            checks.append(
                f"Verify configured reset {policy.subject} remains held until dependency reset {dependency} is released."
            )
        return tuple(checks)
    if policy.kind == "memory":
        checks = []
        collision = policy.parameter("read_during_write")
        if collision is not None and collision != "undefined":
            checks.append(f"Verify configured memory {policy.subject} read-during-write behavior is {collision}.")
        if policy.parameter("profile") == "bounded_sram":
            protection = (
                f"Verify configured memory {policy.subject} corrects single-bit errors, detects double-bit errors, and scrubs repaired words."
                if policy.parameter("protection") == "secded"
                else f"Verify configured memory {policy.subject} parity detects an injected single-bit error."
            )
            checks.extend(
                (
                    f"Verify configured memory {policy.subject} merges only byte-enabled write lanes.",
                    f"Verify configured memory {policy.subject} round-robin arbitration is exclusive and starvation bounded.",
                    f"Verify configured memory {policy.subject} zero initialization at every legal address.",
                    protection,
                )
            )
        return tuple(checks)
    if policy.kind == "formal":
        latency = policy.parameter("max_latency_cycles") or "unspecified"
        return (
            f"Verify configured formal contract {policy.subject} responds within {latency} cycles.",
            f"Verify configured formal contract {policy.subject} preserves its induction invariant.",
            f"Cover configured formal contract {policy.subject} assumption consistency and non-vacuity.",
        )
    if policy.kind == "formal_assumption":
        assumption = policy.parameter("assumption") or "unsupported"
        bound = policy.parameter("bound_cycles") or "unspecified"
        return (
            f"Verify configured formal assumption {policy.subject} applies typed {assumption} semantics.",
            f"Cover configured formal assumption {policy.subject} witness within {bound} cycles.",
        )
    if policy.kind == "cdc":
        structure = policy.parameter("structure") or "configured"
        latency = policy.parameter("max_latency_cycles") or "unspecified"
        return (
            f"Verify configured CDC path {policy.subject} uses {structure} structure and propagates within "
            f"{latency} destination cycles.",
        )
    return _peripheral_depth_policy_checks(policy)


def _peripheral_depth_policy_checks(policy: VerificationDepthPolicy) -> tuple[str, ...]:
    catalogs = {
        "uart": (
            f"Verify UART {policy.subject} TX/RX baud timing and serial data ordering.",
            f"Verify UART {policy.subject} framing, parity, stop-bit, and break behavior.",
            f"Verify UART {policy.subject} overflow reporting and reset recovery.",
        ),
        "spi": (
            f"Verify SPI {policy.subject} CPOL/CPHA modes 0 through 3 and sampled data.",
            f"Verify SPI {policy.subject} chip-select timing and MSB/LSB bit ordering.",
        ),
        "i2c": (
            f"Verify I2C {policy.subject} open-drain wired-AND signaling and START/STOP/repeated START.",
            f"Verify I2C {policy.subject} ACK/NACK and bounded clock stretching.",
            f"Verify I2C {policy.subject} arbitration loss, bus-busy handling, and recovery.",
        ),
        "gpio_timer_interrupt": (
            f"Verify GPIO {policy.subject} direction, masked writes, set/clear, and edge/level interrupts.",
            f"Verify timer {policy.subject} prescaling, compare, rollover, periodic mode, and interrupt clear.",
            f"Verify watchdog {policy.subject} feed, timeout interrupt, and reset request.",
            f"Verify PWM {policy.subject} period, duty boundaries, update timing, and polarity.",
            f"Verify interrupt controller {policy.subject} mask, pending, clear, fixed priority, and simultaneous sources.",
        ),
    }
    return catalogs.get(policy.kind, ())


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
        elif policy.kind == "formal_assumption":
            status, statement = _validate_formal_assumption_policy(module, policy, statement)
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


def _validate_formal_assumption_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    if policy.parameter("engine") != "sby":
        return ClaimStatus.MISSING_EVIDENCE, "Formal assumption engine is unsupported; only sby is qualified."
    assumption = policy.parameter("assumption")
    if assumption not in {"stability", "range"}:
        return ClaimStatus.MISSING_EVIDENCE, "Formal assumption must select typed stability or range semantics."
    required = ("signal", "clock", "reset", "reset_active", "bound_cycles")
    values = {name: policy.parameter(name) for name in required}
    if any(value is None or value == "" for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Formal assumption is missing a required mapping or bound."
    if values["reset_active"] not in {"high", "low"}:
        return ClaimStatus.CONTRADICTED, "Formal assumption reset activation must be high or low."
    bound = values["bound_cycles"] or ""
    if not bound.isdecimal() or not 1 <= int(bound) <= 64:
        return ClaimStatus.CONTRADICTED, "Formal assumption bound_cycles must be between 1 and 64."
    ports = {port.name: port for port in module.port_details}
    if any(values[name] not in ports for name in ("signal", "clock", "reset")):
        return ClaimStatus.MISSING_EVIDENCE, "Formal assumption mappings are not all observable ports."
    if any(ports[values[name] or ""].direction != "input" for name in ("signal", "clock", "reset")):
        return ClaimStatus.CONTRADICTED, "Formal assumptions may constrain only mapped module inputs."
    domains = tuple(
        domain
        for domain in module.control_domains
        if domain.clock == values["clock"] and domain.reset == values["reset"]
    )
    if len(domains) != 1:
        return ClaimStatus.MISSING_EVIDENCE, "Formal assumption clock/reset does not resolve to one domain."
    expected_active = "low" if domains[0].reset_active_low else "high"
    if values["reset_active"] != expected_active:
        return ClaimStatus.CONTRADICTED, "Formal assumption reset activation contradicts the resolved domain."
    if assumption == "range":
        issue = _formal_range_assumption_issue(policy)
        if issue is not None:
            return issue
    return ClaimStatus.SUPPORTED, default_statement


def _formal_range_assumption_issue(
    policy: VerificationDepthPolicy,
) -> tuple[ClaimStatus, str] | None:
    minimum = policy.parameter("minimum")
    maximum = policy.parameter("maximum")
    if minimum is None or maximum is None:
        return ClaimStatus.MISSING_EVIDENCE, "Range assumption requires explicit minimum and maximum."
    try:
        if int(minimum, 0) > int(maximum, 0):
            return ClaimStatus.CONTRADICTED, "Range assumption minimum exceeds maximum."
    except ValueError:
        return ClaimStatus.CONTRADICTED, "Range assumption bounds must be integer literals."
    return None


def _validate_peripheral_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    """Validate a complete peripheral mapping without inferring signal intent."""

    profile = policy.parameter("profile") or ""
    contract = PERIPHERAL_PROFILE_CONTRACTS.get((policy.kind, profile))
    if contract is None:
        return ClaimStatus.MISSING_EVIDENCE, f"{policy.kind} policy has no qualified executable profile."
    integer_values, issue = _peripheral_parameter_issue(contract, policy)
    if issue is not None:
        return issue
    if profile == "fractional_baud_8bit" and integer_values["baud_numerator"] >= integer_values["baud_denominator"]:
        return ClaimStatus.CONTRADICTED, "UART fractional baud ratio must be strictly less than one."

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


def _peripheral_parameter_issue(contract, policy):
    integer_values: dict[str, int] = {}
    for name, minimum, maximum in contract.integer_parameters:
        value = policy.parameter(name)
        if value is None or not value.isdecimal():
            return integer_values, (
                ClaimStatus.MISSING_EVIDENCE,
                f"{policy.kind} policy is missing bounded parameter {name}.",
            )
        integer_values[name] = int(value)
        if not minimum <= integer_values[name] <= maximum:
            return integer_values, (
                ClaimStatus.CONTRADICTED,
                f"{policy.kind} parameter {name} is outside the qualified range.",
            )
    for name, permitted in contract.enum_parameters:
        if policy.parameter(name) not in permitted:
            return integer_values, (
                ClaimStatus.MISSING_EVIDENCE,
                f"{policy.kind} policy is missing qualified {name} intent.",
            )
    return integer_values, None


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
    protection = policy.parameter("protection")
    issue = _bounded_sram_policy_issue(memory, policy, protection)
    if issue is not None:
        return issue

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
    issue = _bounded_sram_signal_issue(memory, values, ports, required, protection, protection_signals)
    if issue is not None:
        return issue
    issue = _bounded_sram_access_issue(module, policy, values)
    return issue if issue is not None else (ClaimStatus.SUPPORTED, default_statement)


def _bounded_sram_policy_issue(memory, policy, protection):
    profile = policy.parameter("profile")
    if profile not in {"bounded_sram", "bounded_sram_init_hex"}:
        return ClaimStatus.MISSING_EVIDENCE, "Memory policy has no qualified executable profile."
    if memory.depth is None or memory.depth < 2 or memory.address_width is None or memory.element_width is None:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM depth, address width, and element width must be known."
    if memory.element_width < 8 or memory.element_width % 8:
        return ClaimStatus.CONTRADICTED, "Bounded SRAM elements must contain a whole number of bytes."
    if policy.parameter("read_during_write") not in {"read_first", "write_first", "no_change"}:
        return ClaimStatus.MISSING_EVIDENCE, "Bounded SRAM requires a defined read-during-write policy."
    if memory.read_during_write not in {"unknown", policy.parameter("read_during_write")}:
        return ClaimStatus.CONTRADICTED, "Configured collision behavior contradicts normalized memory facts."
    initialization_issue = _bounded_sram_initialization_issue(memory, policy, profile)
    if initialization_issue is not None:
        return initialization_issue
    if policy.parameter("arbitration") != "round_robin":
        return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires round-robin arbitration."
    if protection not in {"parity", "secded"}:
        return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires parity or SECDED protection."
    return None


def _bounded_sram_initialization_issue(memory, policy, profile):
    if profile == "bounded_sram":
        if policy.parameter("initialization") != "zero":
            return ClaimStatus.MISSING_EVIDENCE, "The qualified bounded SRAM profile requires zero initialization."
        return None
    if (
        memory.initialization_profile != "bounded_sram_init_hex"
        or not memory.initialization_path
        or not memory.initialization_sha256
        or memory.initialization_default_policy not in {"explicit_zero", "file_complete"}
    ):
        return (
            ClaimStatus.MISSING_EVIDENCE,
            "The bounded SRAM hex profile requires validated initialization metadata.",
        )
    if policy.parameter("path") != memory.initialization_path:
        return ClaimStatus.CONTRADICTED, "Configured initialization path contradicts normalized memory facts."
    configured_sha256 = policy.parameter("sha256")
    if configured_sha256 is not None and configured_sha256 != memory.initialization_sha256:
        return ClaimStatus.CONTRADICTED, "Configured initialization digest contradicts normalized memory facts."
    if policy.parameter("default_policy") != memory.initialization_default_policy:
        return ClaimStatus.CONTRADICTED, "Initialization default policy contradicts normalized memory facts."
    return None


def _bounded_sram_signal_issue(memory, values, ports, required, protection, protection_signals):
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
    return None


def _bounded_sram_access_issue(module, policy, values):
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
    return None


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
