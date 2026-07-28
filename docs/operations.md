# Operations, Security, and Release

Document type: consolidated current and historical documentation.

Purpose: Operator workflows, closure, coverage, security, support, upgrades, release history, and legal notices.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-28.

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`docs/operations/operator-guide.md`](#source-docsoperationsoperator-guidemd)
- [`docs/operations/production-closure-runbook.md`](#source-docsoperationsproduction-closure-runbookmd)
- [`docs/operations/coverage-closure.md`](#source-docsoperationscoverage-closuremd)
- [`docs/operations/rag-operations.md`](#source-docsoperationsrag-operationsmd)
- [`docs/operations/security-and-privacy.md`](#source-docsoperationssecurity-and-privacymd)
- [`docs/operations/support-policy.md`](#source-docsoperationssupport-policymd)
- [`docs/operations/upgrade-and-rollback.md`](#source-docsoperationsupgrade-and-rollbackmd)
- [`SECURITY.md`](#source-securitymd)
- [`CHANGELOG.md`](#source-changelogmd)
- [`THIRD_PARTY_NOTICES.md`](#source-thirdpartynoticesmd)

<a id="source-docsoperationsoperator-guidemd"></a>
## Operator guide

Consolidated from `docs/operations/operator-guide.md`.

Install the signed wheel on Python 3.11–3.13 in Linux or WSL, verify its checksum
and signature, then follow [installation](product-and-interface.md#source-docsconfiginstallationmd) and
[configuration](product-and-interface.md#source-docsconfigconfigurationmd). The production sequence is analyze →
index → plan → generate → run/prove → coverage → `status --policy ci`.

Archive the exact config, wheel checksum, project manifest, normalized facts,
plans/revisions, generated provenance, run summaries, coverage reports, and
status JSON. A zero tool exit without mapped checks is not success. Treat
timeouts, interrupted summaries, stale provenance, unsupported constructs, and
traceability gaps as open failures.

Back up SQLite databases with SQLite's backup API or `.backup`, then run
`PRAGMA integrity_check` against the copy. Restore into an empty work directory
and run status in report mode before allowing CI policy evaluation. See
[upgrade and rollback](#source-docsoperationsupgrade-and-rollbackmd) for release changes.

Review retention candidates with `dv-platform purge --as-of YYYY-MM-DD`; repeat
with `--apply` to delete only the fixed transient-state allowlist. The command
never deletes plan, run, coverage, generated, or backup evidence and refuses any
symlink in scope.

<a id="source-docsoperationsproduction-closure-runbookmd"></a>
## Production verification closure runbook

Consolidated from `docs/operations/production-closure-runbook.md`.

Production closure is a governed state, not a percentage printed by a simulator.
The accepted evidence chain is:

1. RTL and specification evidence produce a versioned verification plan.
2. Simulation and formal runs emit stable coverage/formal point IDs and check IDs.
3. Coverage import reconciles those points to the canonical plan.
4. A disposition closes a point only when its required governance fields are valid.
5. `dv-platform status --policy ci` is the release gate.

<a id="source-docsoperationsproduction-closure-runbookmd--required-release-flow"></a>
### Required release flow

Run the planned simulation and formal jobs, then import their persisted summaries:

```console
dv-platform coverage --from-runs --as-of 2026-07-19
dv-platform status --policy ci
```

Use an explicit UTC calendar date for reproducible waiver expiry evaluation. A release
must not depend on the wall-clock date of the CI worker. The closure report set is
`summary.json`, `summary.yaml`, `summary.md`, and `closure.sarif` under the coverage
output directory. Archive all four with the canonical plans and run summaries.

### Stage 10 candidate qualification

The scale workflow requires the repository variable `SCALE_BASELINE_REF` (or
the `baseline_ref` input on manual dispatch). It must identify a protected
reviewed commit whose v3 baseline record was produced independently. The
workflow builds and installs separate baseline and candidate wheels, runs the
product benchmark from each clean environment, compares the records, creates a
digest-bound candidate bundle, and invokes candidate-mode `ga_gates.py`.
An empty baseline reference, same commit/package, missing bundle component, or
stale artifact fails the job. WSL evidence is required only when the WSL
support claim is active; its manual workflow still fails closed when requested
without a baseline.

<a id="source-docsoperationsproduction-closure-runbookmd--ucis-and-vendor-coverage"></a>
### UCIS and vendor coverage

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

<a id="source-docsoperationsproduction-closure-runbookmd--closure-rules"></a>
### Closure rules

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

<a id="source-docsoperationsproduction-closure-runbookmd--depth-sign-off"></a>
### Depth sign-off

Reset, memory, and CDC policy declarations are generation preconditions, not claims of
proof. A policy becomes supported only when structural RTL evidence and generated
dynamic checks agree. Unsupported or contradicted policy claims remain explicit plan
gaps. Protocol transfer, backpressure, and recovery checks must all execute; a passing
smoke test is not protocol closure.

Commercial simulators, formal engines, lint/CDC tools, or requirements systems may be
connected behind adapters, but their brand does not change the release contract: they
must emit stable point/check identity, preserve failed outcomes, and pass the same plan
reconciliation and disposition governance.

<a id="source-docsoperationscoverage-closuremd"></a>
## Coverage Closure

Consolidated from `docs/operations/coverage-closure.md`.

`dv-platform coverage` accepts aggregate LCOV, JSON, and Cobertura metrics. JSON
reports may additionally provide stable coverage points and governed
dispositions. Point-aware reports make closure traceable to verification plan
checks, requirements, and behaviors instead of treating a percentage as proof
that verification intent was exercised.

<a id="source-docsoperationscoverage-closuremd--normalized-json"></a>
### Normalized JSON

```json
{
  "modules": {
    "stream_buffer": {
      "line": {"covered": 92, "total": 100},
      "functional": {"covered": 7, "total": 8}
    }
  },
  "coverage_points": [
    {
      "module": "stream_buffer",
      "point_id": "cp:backpressure_stability",
      "kind": "assertion",
      "hits": 1,
      "check_ids": ["check:backpressure_stability"],
      "requirement_ids": ["req:backpressure_stability"]
    },
    {
      "module": "stream_buffer",
      "point_id": "cp:simultaneous_push_pop",
      "kind": "coverpoint",
      "covered": false,
      "check_ids": ["check:simultaneous_push_pop"]
    }
  ]
}
```

`formal_points` is an alias whose default kind is `formal`. Each point requires
`module`, `point_id` (or `id`/`name`), and one of `status`, `covered`, or
`hits`. Supported final states are `covered`, `uncovered`, `bounded_pass`,
`unsupported`, `failed`, `waived`, `unreachable`, and `excluded`.
`bounded_pass` and `unsupported` remain actionable, non-closing states. A failed
executed check remains an actionable gap; execution does not convert a
behavioral failure into coverage closure.

<a id="source-docsoperationscoverage-closuremd--dispositions"></a>
### Dispositions

Dispositions are separate governed records. They never create coverage points
and therefore cannot silently waive a misspelled or stale point ID.

```json
{
  "waivers": [
    {
      "module": "stream_buffer",
      "point_id": "cp:simultaneous_push_pop",
      "disposition_id": "waiver:architecture-17",
      "reason": "The configured single-entry specialization cannot overlap operations.",
      "approved_by": "verification-lead",
      "expires_at": "2027-01-01"
    }
  ],
  "unreachable": [
    {
      "module": "stream_buffer",
      "point_id": "cp:illegal_state",
      "disposition_id": "proof:illegal-state-unreachable",
      "reason": "Inductive invariant excludes the encoded state.",
      "evidence_refs": ["runs/formal/stream_buffer/summary.json#prove"]
    }
  ],
  "exclusions": [
    {
      "module": "stream_buffer",
      "point_id": "cp:debug_only",
      "disposition_id": "exclude:debug-disabled",
      "reason": "Debug logic is not present in this specialization."
    }
  ]
}
```

Waivers require `approved_by`. Unreachable points require evidence. Every
disposition requires a stable ID and reason. Orphaned and conflicting
dispositions reject the import.

<a id="source-docsoperationscoverage-closuremd--closure-policy"></a>
### Closure Policy

Raw percentage is covered eligible points divided by all non-excluded points.
Closure percentage additionally counts governed waivers and proven unreachable
points. Exclusions remain visible but are removed from the denominator.

Any active uncovered point fails the coverage command. In strict or CI mode,
traceable functional/formal points without plan mappings and covered points
with stale dispositions also fail. The persisted `closure_gaps` records carry
the IDs needed by the planning feedback stage.

When canonical plans exist, import reconciles each `check_id` with its mapped
points and republishes the plan store with `closure_status` and
`coverage_point_ids`. Executable plan checks without points become
`unmeasured`; point mappings to missing checks become stale. Both conditions
fail point-aware closure and appear as plan open questions so regeneration or
stimulus work cannot silently discard them.

Supported cocotb and formal run summaries emit `coverage_points` or
`formal_points` directly from generated traceability. Those summaries can be
passed back to `dv-platform coverage --input`; point IDs remain bound to stable
check, requirement, and behavior IDs.

Coverage schema v3 also derives `parameter_sweeps` from stored plans. Explicit
specializations are grouped by original design unit and canonical check
semantics. Each cross-point lists the per-sweep state and closes only when every
configured point closes. An absent, uncovered, failed, or unexecuted point makes
the cross-point actionable; aggregate percentage cannot hide it. CI status
reports `parameter_sweep_coverage_incomplete` until the matrix is complete.

<a id="source-docsoperationscoverage-closuremd--vendor-importers"></a>
### Vendor importers

UCIS and vendor-native databases are loaded through explicitly enabled
`dv_platform.coverage_importer` entry points. An importer implements
`supports(path)` and `import_coverage(path)`, returning this normalized JSON
schema. Core applies the same point, disposition, plan-mapping, and strict/CI
validation after import; a plugin cannot directly mark closure passed.

<a id="source-docsoperationsrag-operationsmd"></a>
## RAG operations

Consolidated from `docs/operations/rag-operations.md`.

Documentation retrieval is local and deterministic by default. Supported text
and extractable PDFs are chunked with source locators and content hashes; local
hash embeddings and a JSON vector index are stored under the configured index
directory. Scanned PDFs require a governed OCR sidecar. Encrypted, malformed,
oversized, or entity-bearing inputs fail closed.

Re-index whenever source content or the embedding implementation changes. Keep
the index with the same confidentiality controls as the source documents, never
publish it as diagnostic data, and purge it under the configured retention
policy. Network embedding/vector providers require explicit adapter enablement
and `allow_network = true`; they are outside the GA contract until separately
qualified.

<a id="source-docsoperationssecurity-and-privacymd"></a>
## Security and privacy operations

Consolidated from `docs/operations/security-and-privacy.md`.

<a id="source-docsoperationssecurity-and-privacymd--threat-model"></a>
### Threat model

Repository file lists, include directives, HDL, PDFs/XML, generated code, tool
commands, plugins, model providers, site wrappers, license variables, and export
destinations are untrusted inputs. Primary risks are path or symlink escape,
entity expansion and oversized documents, generated-code execution, executable
plugin import, command/environment injection, secret persistence, model data
disclosure, denial of service, and false verification closure.

The trust boundary is a customer-controlled Linux or WSL runner. Run Veriforge
as an unprivileged dedicated account in an ephemeral container or VM, mount the
RTL repository read-only when practical, place work/output directories on
separate writable volumes, deny outbound network access by default, and expose
only the license variables required by the selected adapter. Native Windows and
macOS are not supported production platforms.

The parser and result boundaries fail closed on unsupported schemas, DTD/entity
XML, malformed checks, unsafe paths, and incomplete traceability. Tool processes
have time, output, concurrency, and memory bounds. This is defense in depth, not
a claim that EDA tools safely process hostile RTL.

<a id="source-docsoperationssecurity-and-privacymd--plugins-secrets-exports-and-retention"></a>
### Plugins, secrets, exports, and retention

Built-in entry points ship in the signed Veriforge distribution. Every
third-party adapter or generator must configure an approved publisher, a
SHA-256 digest of its installed distribution, and either a Sigstore bundle
constrained by certificate identity/OIDC issuer or an enterprise-PKI CMS
signature constrained by a trust root. Verification occurs before executable
code is imported.

Plugin API v1 remains supported throughout the 1.x compatibility line. API v2
adds mandatory `sandbox_aware = true` and `audit_schema_version = 1` contracts;
the same signature and identity policy runs before either version is imported.

Secrets are named, never stored in TOML. `security.secret_provider =
"environment"` is the supported provider; AI keys and license variables should
be injected by the isolated runner. Logs and audit records apply configured
redaction patterns, but operators must test organization-specific patterns.

Exports are restricted to `security.export_roots`. The default roots are the
work and generated-output directories. Retain state for
`security.retention_days` (default 30). `purge --as-of YYYY-MM-DD` is a dry run;
add `--apply` only after review. It refuses symlinks and is restricted to
transient AI cache/run, audit, log, RAG-index, and support-bundle trees. Plans,
run evidence, coverage, generated artifacts, and backups are never purge
targets. Network telemetry is disabled by default.

Optional rootless OCI execution uses Podman or Docker with network disabled, a
read-only root, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs,
an isolated writable run mount, and only explicitly named environment variables.
`execution.license_tokens` caps concurrent runs alongside aggregate-memory limits.

<a id="source-docsoperationssecurity-and-privacymd--incident-handling"></a>
### Incident handling

Follow [SECURITY.md](../SECURITY.md). Preserve content-free digests, affected
versions, configuration shape, and audit records; do not attach proprietary RTL,
documents, raw logs, credentials, or license files to a support ticket.

<a id="source-docsoperationssupport-policymd"></a>
## Support policy

Consolidated from `docs/operations/support-policy.md`.

The supported runtime is CPython 3.11–3.13 on 64-bit Linux. WSL2 is the supported
Windows route. Native Windows and macOS are best-effort and outside production
SLOs. Only bounded profiles marked supported in the capability matrix and exact
qualified tool ranges are covered. LiteLLM/live providers, mixed-language
elaboration, multi-agent UVM/RAL, and other preview capabilities have no SLO.

Security reports follow [SECURITY.md](../SECURITY.md). Operational tickets should
include product/package version, platform, config shape, status JSON, and
content-free log hashes. Do not send RTL, specifications, raw logs, credentials,
license data, retrieval indexes, or generated customer IP unless a separate
approved transfer process exists.

<a id="source-docsoperationsupgrade-and-rollbackmd"></a>
## Upgrade and rollback

Consolidated from `docs/operations/upgrade-and-rollback.md`.

Before upgrade, stop writers, record `dv-platform --json status`, verify the
current wheel checksum, back up every SQLite database and config, and validate
each backup with `PRAGMA integrity_check`. Install the candidate wheel into a
new environment and run status plus an analyze/plan/generate dry qualification
against a non-production copy. Never let an older binary write state after a
newer schema has modified it.

Rollback means stopping writers, restoring the previous environment and the
matching pre-upgrade work-directory backup, then validating status and a known
qualification project. Do not point the old wheel at migrated state. Destructive
migrations require an explicit dry-run report and are prohibited without a
verified backup.

`dv-platform backup --output PATH` and `dv-platform migrate --backup PATH` are
dry runs unless `--apply` is supplied. Applied backups use content-addressed
manifests and SQLite's backup API plus `PRAGMA integrity_check`; migrations
refuse non-adjacent schema jumps and require a verified backup.

`dv-platform destroy` is the separate governed path for run evidence,
counterexamples, generated collateral, and backup sets. It is dry-run by
default and requires an authorization reference, an exact configured target,
a verified recovery backup, and a versioned legal-hold registry. Active holds
fail closed; symbolic links are never traversed.

<a id="source-securitymd"></a>
## Security policy

Consolidated from `SECURITY.md`.

Report suspected vulnerabilities privately to the security contact designated
in the enterprise support agreement. Do not open a public issue with exploit
details or customer material.

We target acknowledgement within two business days, initial severity triage
within five business days, and remediation targets of 7 days for critical, 30
days for high, and 90 days for medium findings. Timelines may be shortened when
active exploitation is known. Supported security fixes cover the latest release
candidate and current 0.1.x line until 1.0 support terms supersede this policy.

Include the affected version, minimal synthetic reproduction, impact, and any
mitigations. Never include proprietary RTL, documents, credentials, license
files, or raw provider traffic.

<a id="source-changelogmd"></a>
## Changelog

Consolidated from `CHANGELOG.md`.

<a id="source-changelogmd--unreleased"></a>
### Unreleased

- Defined the prospective GA contract while retaining version 0.1.x/Alpha.
- Added JSON output for aggregate runs.
- Added plugin publisher/hash policy, export roots, environment-backed secret
  resolution, and retention configuration.
- Added production security, operations, qualification, support, upgrade, and
  rollback documentation plus automated documentation consistency checks.

<a id="source-thirdpartynoticesmd"></a>
## Third-party notices

Consolidated from `THIRD_PARTY_NOTICES.md`.

Veriforge depends on third-party Python packages and external EDA tools. The
authoritative dependency inventory and license texts are generated from the
locked environment for each release and shipped with the release SBOM. External
tools such as Verilator, Icarus Verilog, SymbiYosys, Yosys, Z3, GHDL, Slang, and
commercial vendor products are not redistributed by this repository unless a
release manifest explicitly says otherwise; their own licenses apply.

Jinja2 and MarkupSafe are used for package-owned deterministic artifact
templates. Their BSD licenses are recorded in the generated release SBOM.
