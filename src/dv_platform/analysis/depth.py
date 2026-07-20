"""Deterministic verification-depth intent derived from normalized RTL facts."""

from __future__ import annotations

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
        elif policy.kind == "memory":
            collision = policy.parameter("read_during_write")
            if collision is not None and collision != "undefined":
                checks.append(f"Verify configured memory {policy.subject} read-during-write behavior is {collision}.")
        elif policy.kind == "cdc":
            structure = policy.parameter("structure") or "configured"
            latency = policy.parameter("max_latency_cycles") or "unspecified"
            checks.append(
                f"Verify configured CDC path {policy.subject} uses {structure} structure and propagates within "
                f"{latency} destination cycles."
            )
    return tuple(dict.fromkeys(checks))


def validate_depth_policies(
    module: RTLModule,
    policies: tuple[VerificationDepthPolicy, ...],
    config_source: str = "dv-platform.toml",
) -> tuple[VerificationClaim, ...]:
    """Validate configured depth intent against deterministic normalized facts."""

    claims: list[VerificationClaim] = []
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
            if not any(memory.name == policy.subject for memory in module.memories):
                status = ClaimStatus.MISSING_EVIDENCE
        elif policy.kind == "reset":
            if not any(reset.name == policy.subject for reset in module.reset_details):
                status = ClaimStatus.MISSING_EVIDENCE
        elif policy.kind == "cdc":
            status, statement = _validate_cdc_policy(module, policy, statement)
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


def _validate_cdc_policy(
    module: RTLModule,
    policy: VerificationDepthPolicy,
    default_statement: str,
) -> tuple[ClaimStatus, str]:
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
    structure = policy.parameter("structure")
    if structure != "two_flop":
        return ClaimStatus.MISSING_EVIDENCE, (
            f"Configured CDC structure {structure or 'unspecified'} is not proven by the linear-chain normalizer."
        )
    minimum = int(policy.parameter("min_stages") or "2")
    if path.classification != "synchronizer" or path.synchronizer_stages < minimum:
        return ClaimStatus.CONTRADICTED, (
            f"Configured CDC requires at least {minimum} stages but RTL has {path.synchronizer_stages}."
        )
    if len(path.stage_signals) != path.synchronizer_stages:
        return ClaimStatus.MISSING_EVIDENCE, "Configured CDC stage chain lacks unambiguous ordered stage signals."
    expected_reset = policy.parameter("reset_compatible")
    if expected_reset == "true" and path.reset_compatible is False:
        return ClaimStatus.CONTRADICTED, "Configured CDC reset compatibility contradicts normalized reset domains."
    if expected_reset == "true" and path.reset_compatible is None:
        return ClaimStatus.MISSING_EVIDENCE, "Configured CDC reset compatibility cannot be proven from reset domains."
    return ClaimStatus.SUPPORTED, default_statement
