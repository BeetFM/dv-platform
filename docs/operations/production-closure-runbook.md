# Production verification closure runbook

Production closure is a governed state, not a percentage printed by a simulator.
The accepted evidence chain is:

1. RTL and specification evidence produce a versioned verification plan.
2. Simulation and formal runs emit stable coverage/formal point IDs and check IDs.
3. Coverage import reconciles those points to the canonical plan.
4. A disposition closes a point only when its required governance fields are valid.
5. `dv-platform status --policy ci` is the release gate.

## Required release flow

Run the planned simulation and formal jobs, then import their persisted summaries:

```console
dv-platform coverage --from-runs --as-of 2026-07-19
dv-platform status --policy ci
```

Use an explicit UTC calendar date for reproducible waiver expiry evaluation. A release
must not depend on the wall-clock date of the CI worker. The closure report set is
`summary.json`, `summary.yaml`, `summary.md`, and `closure.sarif` under the coverage
output directory. Archive all four with the canonical plans and run summaries.

## UCIS and vendor coverage

Vendor binary databases are not portable and must not be loaded directly into the
core process. Export UCIS XML with the simulator's supported export command and use
the built-in `ucis_xml` entry point as a configured `coverage_importer` adapter. The
entry point resolves to `dv_platform.analysis.ucis.UCISXMLCoverageImporter` and
accepts `.ucis`, `.ucis.xml`, and `.ucis-xml` inputs.

Enable the adapter explicitly in `dv-platform.toml`:

```toml
[[adapter_plugins]]
kind = "coverage_importer"
name = "ucis_xml"
api_version = 1
```

The importer maps normal bins to covered/uncovered points, ignore bins to excluded
points, and hit illegal bins to failed points. `at_least` is honored. A vendor may
attach `dvCheckId`, `checkId`, or `check_id` to a bin to map it directly to a plan
check. Comma-separated `dvRequirementId`/`requirementId` and
`dvBehaviorId`/`behaviorId` attributes preserve external requirement and behavior
identity. Unmapped bins remain visible as traceability gaps and therefore cannot
silently produce release closure. Check identities are still reconciled against the
canonical plan and an unknown check fails as a stale mapping.

The XML boundary rejects DTD/entity declarations, oversized documents, missing hit
counts, unknown bin types, invalid thresholds, and non-UCIS roots. The import is
deliberately fail-closed because guessing at vendor semantics can create false closure.

## Closure rules

- `covered` closes an observed goal.
- `failed` is always actionable even when the point has hits.
- `uncovered` remains actionable.
- `waived` requires an identifier, reason, approver, and expiry date.
- `unreachable` requires an identifier, reason, and evidence reference.
- `excluded` is removed from the denominator but remains reported.
- Expired waivers return to the actionable set.
- Orphan or conflicting dispositions fail import.
- Executable plan checks without measurements fail traceability.
- Point mappings to deleted checks are stale and fail traceability.
- Points with no requirement, behavior, or plan-check identity fail traceability.

## Depth sign-off

Reset, memory, and CDC policy declarations are generation preconditions, not claims of
proof. A policy becomes supported only when structural RTL evidence and generated
dynamic checks agree. Unsupported or contradicted policy claims remain explicit plan
gaps. Protocol transfer, backpressure, and recovery checks must all execute; a passing
smoke test is not protocol closure.

Commercial simulators, formal engines, lint/CDC tools, or requirements systems may be
connected behind adapters, but their brand does not change the release contract: they
must emit stable point/check identity, preserve failed outcomes, and pass the same plan
reconciliation and disposition governance.
