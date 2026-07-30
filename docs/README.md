# Documentation

Document type: current documentation index.

Audience: users, operators, coding agents, reviewers, and release owners.

Status: current.

Last reviewed: 2026-07-30.

## Canonical guide set

The repository has six substantive guides directly under `docs/`:

1. [Product and Interface](product-and-interface.md): product boundary,
   installation, configuration, CLI, generated state, and public workflows.
2. [Architecture and Decisions](architecture.md): architecture, evidence,
   semantics, adapters, compatibility, and accepted ADRs.
3. [Verification and Qualification](verification.md): current capabilities,
   verification contracts, qualification procedures, stage evidence, and
   historical acceptance.
4. [Operations, Security, and Release](operations.md): operator workflows,
   coverage closure, security, support, upgrades, release history, and notices.
5. [Agent and Documentation Governance](agents.md): authority order, issue
   pickup, implementation, validation, handoff, and documentation rules.
6. [Roadmap, Missing Work, and Progress](roadmap.md): the complete backlog,
   Free and Enterprise plans, implementation and validation cards, staged plan,
   and append-only progress history.

## Maintained document catalog

This view is generated from
`qualification/policies/document-catalog-v1.json`.

<!-- generated: document-catalog-v1 -->
| Path | Class | Authority |
| --- | --- | --- |
| `CHANGELOG.md` | `historical_log` | `release-history` |
| `README.md` | `current_authority` | `public-product-overview` |
| `SECURITY.md` | `current_authority` | `security-policy` |
| `THIRD_PARTY_NOTICES.md` | `legal_notice` | `third-party-license-record` |
| `docs/README.md` | `current_authority` | `documentation-index` |
| `docs/agents.md` | `current_authority` | `agent-governance` |
| `docs/architecture.md` | `current_authority` | `architecture` |
| `docs/operations.md` | `current_authority` | `operations-and-release` |
| `docs/product-and-interface.md` | `current_authority` | `product-interface` |
| `docs/roadmap.md` | `current_authority` | `ticket-and-progress-authority` |
| `docs/verification.md` | `current_authority` | `qualification-and-capability` |
| `progress.md` | `historical_log` | `append-only-progress-snapshot` |
<!-- /generated: document-catalog-v1 -->

## Required reading

Coding agents must read [Agent Governance](agents.md) and the active
[Roadmap](roadmap.md) before changing behavior. Operators should start with
[Product and Interface](product-and-interface.md), then use
[Operations](operations.md). Qualification reviewers must use
[Verification and Qualification](verification.md) together with the machine
ledger at `qualification/policies/ga-gates-v1.json`.

## Authority order

1. Versioned schemas, validators, scenario target states, and GA gate policy.
2. Fresh source, plan, generated, run, coverage, and status evidence.
3. Current P0 regression records in [Roadmap](roadmap.md).
4. Current capability and production-readiness sections in
   [Verification](verification.md).
5. Qualification stage records.
6. Historical acceptance snapshots.
7. Architecture and accepted decisions.
8. Roadmap prose and historical progress.

Architecture plans and generated files are not qualification evidence.

## Consolidation contract

Each guide has a source-coverage list and every migrated source is preserved
under a stable `source-*` anchor. References to the former directory layout
have been rewritten to these guides. The conventional root `README.md`,
`SECURITY.md`, `CHANGELOG.md`, and `progress.md` are compatibility pointers;
`THIRD_PARTY_NOTICES.md` remains at the root as a legal-distribution file.

Machine-readable assets are intentionally outside the prose set:

- `qualification/policies/compatibility-baseline-v1.json`
- `qualification/evidence/vivado-xsim-2025.2-qualification-attestation.json`
- `qualification/policies/ga-gates-v1.json`
- `qualification/policies/capability-ledger-v1.json`
- `qualification/policies/document-catalog-v1.json`
- `qualification/policies/progress-ledger-v1.json`
- `qualification/policies/local-task-audit-v1.json`
- `qualification/evidence/SEM-01/systemverilog-expression-semantics-v3.json`
- `qualification/evidence/FORM-01/formal-evidence-v1.json`
- `qualification/evidence/CDC-01/{cocotb,formal}-evidence-v1.json`
- `qualification/evidence/MEM-01/{cocotb,formal}-evidence-v1.json`
- `qualification/external-designs/*.json`
- `qualification/performance/*.json`
- `schemas/**/*.json`

Skill manifests under `skills/**/SKILL.md` and fixture documents under
`tests/fixtures/` remain in their runtime-required locations.

## Validation

```bash
uv run python scripts/checks/repository_contracts.py
uv run python scripts/qualification/ga_gates.py
uv run python -m unittest   tests.documentation.test_docs   tests.repository.test_repository_contracts   tests.qualification.test_ga_gates   tests.qualification.test_enterprise_qualification
```
