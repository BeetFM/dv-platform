# Veriforge GA contract

Veriforge is the product name. `dv-platform` is the Python distribution and
primary CLI; `dv-enterprise` is the enterprise-adapter CLI.

The prospective stable 1.x surface is deliberately smaller than the source
tree: CLI command names and options, JSON envelopes and error codes,
`dv-platform.toml`, persisted schemas, packaged JSON schemas, and plugin APIs
v1 and v2. API v1 remains readable and loadable throughout 1.x; v2 adds the
sandbox/audit contract. Direct imports from `dv_platform` are internal implementation details and
may change in minor releases. LiteLLM and live-provider behavior are opt-in
preview functionality and are excluded from support SLOs.

Version 0.1.x and the Alpha classifier remain in force. A supported capability
means only the bounded profile identified in the [capability matrix](capability-matrix.md),
with the evidence required by its acceptance document. Missing vendor evidence,
external pilots, or security gates cannot be replaced by a passing unit test.
The ordered Stage 6–13 gates and version transitions are defined in
[Broad-GA stages](ga-stages.md) and enforced by the checked-in GA ledger.

Schemas remain backward-readable for at least one major release. A destructive
migration requires a verified backup, a dry-run report, and an explicitly
selected migration. Deprecations require release-note notice for one minor
release before removal; breaking stable-surface changes require a major version.
