# Documentation

Document type: current documentation index.

Audience: users, operators, coding agents, reviewers, and release owners.

Status: current, with known capability-claim conflicts tracked by `DOC-00` and
`DOC-02` and legacy metadata/checker migration tracked by `DOC-03`.

Last reviewed: 2026-07-27.

## Start here

Coding agents must read:

1. [Agent Execution Guide](agent-execution-guide.md) for authority, issue pickup,
   implementation order, commands, stop conditions, and handoff format.
2. [Missing Work](planning/missing-work.md) for current regressions, backlog
   IDs, source ownership, technical steps, edge cases, and completion evidence.
3. [Documentation Contract](documentation-contract.md) before changing any
   capability, acceptance, operations, architecture, or roadmap statement.

Operators should begin with:

1. [Installation](config/installation.md).
2. [Configuration](config/configuration.md).
3. [Operator Guide](operations/operator-guide.md).
4. [Production Closure Runbook](operations/production-closure-runbook.md).

Release/qualification reviewers should begin with:

1. [Qualification evidence index](../qualification/README.md).
2. [GA Contract](qualification/ga-contract.md).
3. [GA Stages](qualification/ga-stages.md).
4. [Capability Matrix](qualification/capability-matrix.md).
5. Current P0 regressions in [Missing Work](planning/missing-work.md).

## Current warning

The 2026-07-27 rescan found one SECDED formal regression and mandatory quality
gate failures. Several capability and historical acceptance documents also
contain known state drift. Do not claim a fully passing current release from
prose alone. Use the authority order in the agent guide and preserve the
conservative state until `BUG-CDC-01`, `QUALITY-01`, `DOC-00`, and `DOC-02` are
closed.

The central indexes and contracts are current, but 44 legacy Markdown files
still require class-specific metadata migration and machine enforcement. See
`DOC-03`; do not assume the presence of this index means every legacy document
has already been normalized.

## Authority order

When documents disagree:

1. Versioned schemas, validators, scenario target states, and GA gate policy.
2. Fresh source/plan/generated/run/coverage/status evidence from qualified tools.
3. Current P0 regression records.
4. Current capability and production-readiness documents.
5. Qualification stage records.
6. Historical acceptance snapshots.
7. Architecture/ADRs.
8. Roadmap prose.

Never use an architecture plan or generated file as qualification evidence.
See the full conflict procedure in the
[Documentation Contract](documentation-contract.md).

## Document classes

### Architecture

[Architecture](architecture/) explains system design, data flow, trust
boundaries, adapters, evidence, protocols, semantics, and HDL frontends. It
constrains implementation but does not independently prove support.

Key documents:

- [Platform Architecture](architecture/architecture.md)
- [Evidence and Claim Model](architecture/evidence-model.md)
- [Backend and Output Layout](architecture/backends-and-output.md)
- [Verification Depth](architecture/verification-depth.md)
- [Protocol Profiles](architecture/protocol-profiles.md)
- [Language Semantic Completeness](architecture/language-semantic-completeness.md)
- [Verilator AST Extraction](architecture/verilator-ast.md)
- [Semantic Cross-Check](architecture/semantic-cross-check.md)
- [Slang Compatibility Matrix](architecture/slang-compatibility-matrix.md)
- [Enterprise Adapters](architecture/enterprise-adapters.md)

### Acceptance

[Acceptance Evidence Index](acceptance/README.md) classifies the dated, bounded
historical records. Read the
snapshot date, exact profile/target/tool boundary, mutation evidence, and
exclusions. A later stage may broaden capability; do not rewrite an older
acceptance record to imply the later feature existed at that time.

Current known reconciliation areas are native APB4/AXI4-Lite, SECDED/scrub,
VHDL packages/types/generates, and broad protocols. See `DOC-02`.

### Qualification

[Qualification](qualification/) defines current support vocabulary,
production-readiness behavior, GA stages, enterprise evidence levels, and test
requirements. Release evidence itself is retained under the repository-level
[`qualification/`](../qualification/) directory.

Key documents:

- [Capability Matrix](qualification/capability-matrix.md)
- [Verification Production Readiness](qualification/verification-production-readiness.md)
- [Testing and Qualification](qualification/testing-and-qualification.md)
- [Enterprise Qualification](qualification/enterprise-qualification.md)
- [GA Contract](qualification/ga-contract.md)
- [GA Stages](qualification/ga-stages.md)

### Operations

[Operations](operations/) explains installation-to-closure operation, coverage,
security/privacy, support, RAG, upgrade/rollback, and evidence retention.
Operational commands must be read with the configuration and CLI contracts.

Use:

- [Operator Guide](operations/operator-guide.md) for the normal local workflow,
  state inspection, and common failure paths.
- [Production Closure Runbook](operations/production-closure-runbook.md) for
  strict end-to-end release evidence and closure.
- [Coverage Closure](operations/coverage-closure.md) for import formats,
  thresholds, exclusions, dispositions, and non-closing coverage states.
- [RAG Operations](operations/rag-operations.md) for document indexing,
  invalidation, local retrieval, and confidentiality boundaries.
- [Security and Privacy](operations/security-and-privacy.md) for network,
  secrets, sandbox, audit, retention, and export controls.
- [Support Policy](operations/support-policy.md) for supported/best-effort
  boundaries, issue bundles, and escalation.
- [Upgrade and Rollback](operations/upgrade-and-rollback.md) for compatibility,
  backups, migration, rollback, and evidence preservation.

### Planning

[Planning Index](planning/README.md) separates historical staged intent from
current work:

- [Implementation Plan](planning/implementation-plan.md) is the staged design
  history and broader roadmap.
- [Missing Work](planning/missing-work.md) is the active, prioritized,
  agent-ready issue inventory and current regression record.

Agents must use Missing Work for issue state. A line marked implemented in the
Implementation Plan is not sufficient evidence of current support.

### Compatibility

[Compatibility](compatibility/) defines the public import/CLI/dataclass/schema/
entry-point/generated-artifact contract. Compatibility hashes currently need
review under `QUALITY-01`; never replace the baseline without inspecting the
normalized API delta.

Use the [Refactor Compatibility Contract](compatibility/contract.md) before
moving modules, changing CLI options, adding dataclass fields, changing schema
versions, or updating compatibility fingerprints.

### Configuration

[Configuration](config/) defines installation, TOML fields, CLI commands,
machine output, exit/error behavior, and state paths. It is the user-interface
authority, subject to versioned code/schema validation.

- [Installation](config/installation.md) defines Python, platform, and external
  tool prerequisites.
- [Configuration](config/configuration.md) defines `dv-platform.toml`,
  defaults, validation, path boundaries, and persisted state.
- [CLI Contract](config/cli-contract.md) defines commands, JSON envelopes,
  errors/exits, and CI-facing behavior.

### Architecture decisions

[Architecture Decision Index](adr/README.md) links all accepted decisions for
configuration/state, RTL evidence, retrieval, claim gating, canonical storage,
generation targets, formal/UVM boundaries, and enterprise adapters. Follow an
ADR unless a later accepted ADR explicitly supersedes it.

### Evidence

`docs/evidence/` retains controlled attestations such as the current Vivado
XSim UVM record. Release-stage records and policies live in
[`qualification/`](../qualification/). Evidence must be verified against its
schema, signer/trust policy, source/generated hashes, tool version, freshness,
and exact profile before use.

## Documentation update procedure

1. Classify the document using the Documentation Contract.
2. Identify the machine contract and evidence behind every changed claim.
3. Preserve historical scope.
4. Update current capability, configuration/CLI, operations, acceptance/
   qualification, and backlog links together when behavior changes.
5. Add edge cases, failure behavior, migration, and evidence.
6. Run:

```bash
uv run python scripts/checks/repository_contracts.py
uv run python -m unittest \
  tests.documentation.test_docs \
  tests.repository.test_repository_contracts
```

7. Disclose known regressions or unavailable evidence.
