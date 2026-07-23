# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic verification-depth intent derived from normalized RTL facts."""

from __future__ import annotations

from dv_platform.core.models import (
    ClaimStatus,
    RTLModule,
    VerificationDepthPolicy,
)


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
    ports = {port.name: port for port in module.port_details}
    ready = policy.parameter("ready_signal")
    if not ready or ready not in ports or ports[ready].direction != "output" or ports[ready].width not in {None, 1}:
        return ClaimStatus.MISSING_EVIDENCE, "Configured reset requires an observable scalar ready output."
    issue = _reset_power_issue(policy, ports, ready)
    if issue is not None:
        return issue
    issue = _reset_dependency_issue(module, policy, domain, ports)
    return issue if issue is not None else (ClaimStatus.SUPPORTED, default_statement)


def _reset_power_issue(policy, ports, ready) -> tuple[ClaimStatus, str] | None:
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
    return None


def _reset_dependency_issue(module, policy, domain, ports) -> tuple[ClaimStatus, str] | None:
    dependency_reset = policy.parameter("depends_on_reset")
    dependency_ready = policy.parameter("depends_on_ready")
    dependency_sync = policy.parameter("dependency_sync_signal")
    dependency_fields = (dependency_reset, dependency_ready, dependency_sync)
    if any(dependency_fields) and not all(dependency_fields):
        return ClaimStatus.MISSING_EVIDENCE, "Configured ordered reset requires all dependency signal mappings."
    if dependency_reset is None:
        return None
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
    return None


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
    issue = _cdc_path_issue(policy, path, structure)
    if issue is not None:
        return issue
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
    issue = _first_cdc_special_issue(module, policy, path, structure, output_signal, minimum)
    if issue is not None:
        return issue
    issue = _cdc_reset_issue(policy, path)
    return issue if issue is not None else (ClaimStatus.SUPPORTED, default_statement)


def _cdc_path_issue(policy, path, structure) -> tuple[ClaimStatus, str] | None:
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
    return None


def _first_cdc_special_issue(module, policy, path, structure, output_signal, minimum):
    issue = _cdc_structure_issue(module, policy, path, structure, output_signal)
    if issue is None:
        issue = _cdc_handshake_issue(module, policy, path, structure, minimum)
    if issue is None:
        issue = _cdc_data_issue(module, policy, structure)
    return issue


def _cdc_reset_issue(policy, path) -> tuple[ClaimStatus, str] | None:
    if policy.parameter("reset_compatible") != "true":
        return None
    if path.reset_compatible is False:
        return ClaimStatus.CONTRADICTED, "Configured CDC reset compatibility contradicts normalized reset domains."
    if path.reset_compatible is None:
        return ClaimStatus.MISSING_EVIDENCE, "Configured CDC reset compatibility cannot be proven from reset domains."
    return None


def _cdc_structure_issue(module, policy, path, structure, output_signal) -> tuple[ClaimStatus, str] | None:
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
    return None


def _cdc_handshake_issue(module, policy, path, structure, minimum) -> tuple[ClaimStatus, str] | None:
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
    return None


def _cdc_data_issue(module, policy, structure) -> tuple[ClaimStatus, str] | None:
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
    return None


def _validate_async_fifo_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
    memory = next((item for item in module.memories if item.name == policy.subject), None)
    if memory is None:
        return ClaimStatus.MISSING_EVIDENCE, f"Configured async FIFO memory {policy.subject} is not normalized."
    issue = _async_fifo_memory_issue(memory)
    if issue is not None:
        return issue

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
    ports = {port.name: port for port in module.port_details}
    issue = _async_fifo_signal_issue(values, ports)
    if issue is not None:
        return issue

    domains = {domain.domain_id: domain for domain in module.control_domains}
    writes = tuple(
        access
        for access in module.memory_accesses
        if access.memory == policy.subject and access.kind == "write" and access.synchronous
    )
    fwft = policy.parameter("first_word_fall_through") == "true"
    reads = tuple(
        access
        for access in module.memory_accesses
        if access.memory == policy.subject and access.kind == "read" and (fwft or access.synchronous)
    )
    if len(writes) != 1 or len(reads) != 1:
        return (
            ClaimStatus.MISSING_EVIDENCE,
            "Configured async FIFO requires one unambiguous write access and one qualified read access.",
        )
    write_domain = domains.get(writes[0].domain_id or "")
    read_domain = domains.get(reads[0].domain_id or "")
    if fwft and read_domain is None:
        read_domain = next((domain for domain in domains.values() if domain.clock == values["read_clock"]), None)
    if write_domain is None or read_domain is None or write_domain.domain_id == read_domain.domain_id:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO accesses are not in distinct normalized clock domains."
    if write_domain.clock != values["write_clock"] or read_domain.clock != values["read_clock"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO clocks contradict normalized memory access domains."
    if write_domain.reset != values["write_reset"] or read_domain.reset != values["read_reset"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO resets contradict normalized memory access domains."
    if values["write_enable"] not in writes[0].enable_signals or values["write_data"] not in writes[0].data_signals:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO write mapping contradicts the normalized memory access."
    read_enable_required = policy.parameter("first_word_fall_through") != "true"
    if (read_enable_required and values["read_enable"] not in reads[0].enable_signals) or values[
        "read_data"
    ] not in reads[0].data_signals:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO read mapping contradicts the normalized memory access."
    issue = _async_fifo_layout_issue(module, policy, memory, values, ports, write_domain, read_domain)
    return issue if issue is not None else (ClaimStatus.SUPPORTED, default_statement)


def _async_fifo_memory_issue(memory) -> tuple[ClaimStatus, str] | None:
    if memory.depth is None or memory.depth < 2 or memory.depth & (memory.depth - 1):
        return ClaimStatus.CONTRADICTED, "Configured async FIFO depth must be a known power of two."
    if memory.element_width is None or memory.address_width is None:
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO memory width and address width must be known."
    return None


def _async_fifo_signal_issue(values, ports) -> tuple[ClaimStatus, str] | None:
    if any(not value for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO policy is missing a required signal mapping."
    if any(value not in ports for value in values.values()):
        return ClaimStatus.MISSING_EVIDENCE, "Configured async FIFO signals are not all observable module ports."
    if values["write_clock"] == values["read_clock"]:
        return ClaimStatus.CONTRADICTED, "Configured async FIFO requires distinct write and read clocks."
    return None


def _async_fifo_layout_issue(
    module,
    policy,
    memory,
    values,
    ports,
    write_domain,
    read_domain,
) -> tuple[ClaimStatus, str] | None:
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
    return None
