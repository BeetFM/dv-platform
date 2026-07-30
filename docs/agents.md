# Agent and Documentation Governance

Document type: consolidated current and historical documentation.

Purpose: Authority rules, issue pickup, implementation workflow, validation, handoff, and documentation contracts.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-30.

## Current governance overlay

All 70 `source-*` sections below are preserved snapshots, including sections
that described themselves as current when consolidated. Current task state is
the generated local-work audit at the top of
[Roadmap](roadmap.md#current-local-work-audit); current capability state is
`qualification/policies/capability-ledger-v1.json`; and physical/source
document classification is
`qualification/policies/document-catalog-v1.json`.

`DOC-00`, `DOC-02`, and the repository-owned portion of `DOC-03` are closed in
the machine progress ledger. Broad protocol cells remain conservative because
documentation closure does not substitute for target-specific real-tool,
good-DUT, mutation, coverage, and strict-status evidence.

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`docs/README.md`](#source-docsreadmemd)
- [`docs/agent-execution-guide.md`](#source-docsagent-execution-guidemd)
- [`docs/documentation-contract.md`](#source-docsdocumentation-contractmd)

<a id="source-docsreadmemd"></a>
## Documentation

Consolidated from `docs/README.md`.

> Consolidation note: this 2026-07-27 index is retained as source material.
> Its former directory layout, legacy-file count, and issue-state warning are
> superseded by the current [`docs/README.md`](README.md), the source-coverage
> checks in this guide, and the current baseline in
> [`docs/roadmap.md`](roadmap.md#source-docsplanningmissing-workmd).

Document type: current documentation index.

Audience: users, operators, coding agents, reviewers, and release owners.

Status: current, with known capability-claim conflicts tracked by `DOC-00` and
`DOC-02` and legacy metadata/checker migration tracked by `DOC-03`.

Last reviewed: 2026-07-27.

<a id="source-docsreadmemd--start-here"></a>
### Start here

Coding agents must read:

1. [Agent Execution Guide](#source-docsagent-execution-guidemd) for authority, issue pickup,
   implementation order, commands, stop conditions, and handoff format.
2. [Missing Work](roadmap.md#source-docsplanningmissing-workmd) for current regressions, backlog
   IDs, source ownership, technical steps, edge cases, and completion evidence.
3. [Documentation Contract](#source-docsdocumentation-contractmd) before changing any
   capability, acceptance, operations, architecture, or roadmap statement.

Operators should begin with:

1. [Installation](product-and-interface.md#source-docsconfiginstallationmd).
2. [Configuration](product-and-interface.md#source-docsconfigconfigurationmd).
3. [Operator Guide](operations.md#source-docsoperationsoperator-guidemd).
4. [Production Closure Runbook](operations.md#source-docsoperationsproduction-closure-runbookmd).

Release/qualification reviewers should begin with:

1. [Qualification evidence index](verification.md#source-qualificationreadmemd).
2. [GA Contract](verification.md#source-docsqualificationga-contractmd).
3. [GA Stages](verification.md#source-docsqualificationga-stagesmd).
4. [Capability Matrix](verification.md#source-docsqualificationcapability-matrixmd).
5. Current P0 regressions in [Missing Work](roadmap.md#source-docsplanningmissing-workmd).

<a id="source-docsreadmemd--current-warning"></a>
### Current warning

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

<a id="source-docsreadmemd--authority-order"></a>
### Authority order

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
[Documentation Contract](#source-docsdocumentation-contractmd).

<a id="source-docsreadmemd--document-classes"></a>
### Document classes

<a id="source-docsreadmemd--architecture"></a>
#### Architecture

[Architecture](architecture.md) explains system design, data flow, trust
boundaries, adapters, evidence, protocols, semantics, and HDL frontends. It
constrains implementation but does not independently prove support.

Key documents:

- [Platform Architecture](architecture.md#source-docsarchitecturearchitecturemd)
- [Evidence and Claim Model](architecture.md#source-docsarchitectureevidence-modelmd)
- [Backend and Output Layout](architecture.md#source-docsarchitecturebackends-and-outputmd)
- [Verification Depth](architecture.md#source-docsarchitectureverification-depthmd)
- [Protocol Profiles](architecture.md#source-docsarchitectureprotocol-profilesmd)
- [Language Semantic Completeness](architecture.md#source-docsarchitecturelanguage-semantic-completenessmd)
- [Verilator AST Extraction](architecture.md#source-docsarchitectureverilator-astmd)
- [Semantic Cross-Check](architecture.md#source-docsarchitecturesemantic-cross-checkmd)
- [Slang Compatibility Matrix](architecture.md#source-docsarchitectureslang-compatibility-matrixmd)
- [Enterprise Adapters](architecture.md#source-docsarchitectureenterprise-adaptersmd)

<a id="source-docsreadmemd--acceptance"></a>
#### Acceptance

[Acceptance Evidence Index](verification.md#source-docsacceptancereadmemd) classifies the dated, bounded
historical records. Read the
snapshot date, exact profile/target/tool boundary, mutation evidence, and
exclusions. A later stage may broaden capability; do not rewrite an older
acceptance record to imply the later feature existed at that time.

Current known reconciliation areas are native APB4/AXI4-Lite, SECDED/scrub,
VHDL packages/types/generates, and broad protocols. See `DOC-02`.

<a id="source-docsreadmemd--qualification"></a>
#### Qualification

[Qualification](verification.md) defines current support vocabulary,
production-readiness behavior, GA stages, enterprise evidence levels, and test
requirements. Release evidence itself is retained under the repository-level
[`qualification/`](../qualification/) directory.

Key documents:

- [Capability Matrix](verification.md#source-docsqualificationcapability-matrixmd)
- [Verification Production Readiness](verification.md#source-docsqualificationverification-production-readinessmd)
- [Testing and Qualification](verification.md#source-docsqualificationtesting-and-qualificationmd)
- [Enterprise Qualification](verification.md#source-docsqualificationenterprise-qualificationmd)
- [GA Contract](verification.md#source-docsqualificationga-contractmd)
- [GA Stages](verification.md#source-docsqualificationga-stagesmd)

<a id="source-docsreadmemd--operations"></a>
#### Operations

[Operations](operations.md) explains installation-to-closure operation, coverage,
security/privacy, support, RAG, upgrade/rollback, and evidence retention.
Operational commands must be read with the configuration and CLI contracts.

Use:

- [Operator Guide](operations.md#source-docsoperationsoperator-guidemd) for the normal local workflow,
  state inspection, and common failure paths.
- [Production Closure Runbook](operations.md#source-docsoperationsproduction-closure-runbookmd) for
  strict end-to-end release evidence and closure.
- [Coverage Closure](operations.md#source-docsoperationscoverage-closuremd) for import formats,
  thresholds, exclusions, dispositions, and non-closing coverage states.
- [RAG Operations](operations.md#source-docsoperationsrag-operationsmd) for document indexing,
  invalidation, local retrieval, and confidentiality boundaries.
- [Security and Privacy](operations.md#source-docsoperationssecurity-and-privacymd) for network,
  secrets, sandbox, audit, retention, and export controls.
- [Support Policy](operations.md#source-docsoperationssupport-policymd) for supported/best-effort
  boundaries, issue bundles, and escalation.
- [Upgrade and Rollback](operations.md#source-docsoperationsupgrade-and-rollbackmd) for compatibility,
  backups, migration, rollback, and evidence preservation.

<a id="source-docsreadmemd--planning"></a>
#### Planning

[Planning Index](roadmap.md#source-docsplanningreadmemd) separates historical staged intent from
current work:

- [Implementation Plan](roadmap.md#source-docsplanningimplementation-planmd) is the staged design
  history and broader roadmap.
- [Missing Work](roadmap.md#source-docsplanningmissing-workmd) is the active, prioritized,
  agent-ready issue inventory and current regression record.

Agents must use Missing Work for issue state. A line marked implemented in the
Implementation Plan is not sufficient evidence of current support.

<a id="source-docsreadmemd--compatibility"></a>
#### Compatibility

[Compatibility](architecture.md#source-docscompatibilitycontractmd) defines the public import/CLI/dataclass/schema/
entry-point/generated-artifact contract. Compatibility hashes currently need
review under `QUALITY-01`; never replace the baseline without inspecting the
normalized API delta.

Use the [Refactor Compatibility Contract](architecture.md#source-docscompatibilitycontractmd) before
moving modules, changing CLI options, adding dataclass fields, changing schema
versions, or updating compatibility fingerprints.

<a id="source-docsreadmemd--configuration"></a>
#### Configuration

[Configuration](product-and-interface.md) defines installation, TOML fields, CLI commands,
machine output, exit/error behavior, and state paths. It is the user-interface
authority, subject to versioned code/schema validation.

- [Installation](product-and-interface.md#source-docsconfiginstallationmd) defines Python, platform, and external
  tool prerequisites.
- [Configuration](product-and-interface.md#source-docsconfigconfigurationmd) defines `dv-platform.toml`,
  defaults, validation, path boundaries, and persisted state.
- [CLI Contract](product-and-interface.md#source-docsconfigcli-contractmd) defines commands, JSON envelopes,
  errors/exits, and CI-facing behavior.

<a id="source-docsreadmemd--architecture-decisions"></a>
#### Architecture decisions

[Architecture Decision Index](architecture.md#source-docsadrreadmemd) links all accepted decisions for
configuration/state, RTL evidence, retrieval, claim gating, canonical storage,
generation targets, formal/UVM boundaries, and enterprise adapters. Follow an
ADR unless a later accepted ADR explicitly supersedes it.

<a id="source-docsreadmemd--evidence"></a>
#### Evidence

`docs/evidence/` retains controlled attestations such as the current Vivado
XSim UVM record. Release-stage records and policies live in
[`qualification/`](../qualification/). Evidence must be verified against its
schema, signer/trust policy, source/generated hashes, tool version, freshness,
and exact profile before use.

<a id="source-docsreadmemd--documentation-update-procedure"></a>
### Documentation update procedure

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

<a id="source-docsagent-execution-guidemd"></a>
## Agent Execution Guide

Consolidated from `docs/agent-execution-guide.md`.

Document type: current operational authority for coding agents.

Audience: Codex models, automated implementation agents, reviewers, and human
maintainers assigning repository work.

Scope: how to select, implement, verify, document, and hand off changes in this
repository. This guide does not redefine product capabilities; it explains how
to work on them without inferring missing policy.

Last reviewed: 2026-07-27.

<a id="source-docsagent-execution-guidemd--mandatory-starting-state"></a>
### Mandatory starting state

Before reading a feature document or editing code, establish these facts:

1. The repository may contain user changes. Run `git status --short` and never
   discard, reset, overwrite, or reformat unrelated work.
2. The current working tree has known P0 blockers recorded in
   [Missing Work](roadmap.md#source-docsplanningmissing-workmd):
   `BUG-CDC-01`, `QUALITY-01`, `DOC-00`, and `DOC-02`.
   `DOC-03` is the non-P0 migration for complete machine-readable document
   classification and semantic command checking.
3. The latest full local scan ran 585 tests with one SECDED formal failure and
   four environment-dependent skips. Do not describe the current tree as fully
   passing until that exact regression and all mandatory quality gates pass.
4. Capability prose currently contains known contradictions. Use the authority
   order below and choose the conservative state when evidence disagrees.

An agent that cannot establish these facts must stop before changing a support
claim.

<a id="source-docsagent-execution-guidemd--authority-and-precedence"></a>
### Authority and precedence

Use this order when two sources disagree:

1. **Security and user instructions.** Explicit user scope, repository security
   policy, and approved destructive/external actions always take precedence.
2. **Versioned machine contracts.** JSON schemas, persisted schema versions,
   configuration validators, scenario target states, plugin API contracts, and
   `qualification/policies/ga-gates-v1.json`.
3. **Fresh measured evidence.** Exact clean-checkout tool runs tied to source,
   plan, generated-artifact, tool-version, result, coverage, and status hashes.
4. **Current P0 regression records.** The rescan section and P0 issues in
   `docs/roadmap.md` can temporarily block a previously accepted
   capability without erasing its historical evidence.
5. **Current capability authority.** `docs/verification.md`
   and `docs/verification.md`, once their
   known `DOC-00`/`DOC-02` conflicts are resolved.
6. **Qualification stage records.** Files under `docs/verification.md` state
   what was accepted at a stage and with which tools/fixtures.
7. **Acceptance snapshots.** Files under `docs/verification.md` are historical,
   bounded records. A later stage may supersede a limitation without making the
   old snapshot false for its date.
8. **Architecture and ADRs.** ADRs constrain design unless superseded.
   Architecture documents explain intent but do not promote execution support.
9. **Planning prose.** Implementation plans explain sequence. They are not
   evidence that an item is implemented or qualified.

Conflict rule: never average claims or choose the newest-looking prose. Record
the exact conflicting files, use the less permissive state for release/CI, and
open or extend a `DOC-*` issue.

<a id="source-docsagent-execution-guidemd--required-reading-by-task"></a>
### Required reading by task

| Task | Read first | Then inspect |
| --- | --- | --- |
| Pick up a backlog issue | `planning/missing-work.md`, this guide | Source ownership map and ticket playbook for the selected ID |
| Change architecture | Relevant ADRs, `architecture/architecture.md` | Affected schemas, compatibility contract, capability matrix |
| Add or change config/CLI | `config/configuration.md`, `config/cli-contract.md` | `configuration/`, `cli_handlers/`, compatibility baseline/tests |
| Change RTL normalization | `architecture/language-semantic-completeness.md`, frontend-specific architecture document | Semantic schemas, normalizers, codecs, cross-check tests |
| Add verification depth | `architecture/verification-depth.md` | Depth catalog/validators, typed scenarios, generators, formal execution |
| Add protocol support | `architecture/protocol-profiles.md`, `DOC-00` | Protocol catalog, recognition, target renderers, traces, mutation tests |
| Add formal support | `acceptance/formal-depth-acceptance.md` | Formal scenarios, generation, SBY task construction, result parser |
| Change CDC/RDC/memory | Relevant acceptance record and P0 regressions | Normalized facts, policies, scenario construction, cocotb/formal evidence |
| Add simulator/formal adapter | `architecture/enterprise-adapters.md` | Enterprise adapter contracts, sandbox, result normalization, signatures |
| Change coverage | `operations/coverage-closure.md` | Coverage-v3 schema, loaders/importers, closure policy, status |
| Change AI behavior | README AI boundary, `AI-01`/`AI-02` | Gateway, planning/feedback/scenario contracts, security/privacy |
| Change release qualification | `docs/verification.md`, GA contract/stages | Gate ledger, evidence schemas, CI/release workflows |
| Documentation-only correction | `documentation-contract.md`, `DOC-00`/`DOC-02` | Machine evidence supporting every changed capability statement |

<a id="source-docsagent-execution-guidemd--ticket-pickup-procedure"></a>
### Ticket pickup procedure

Follow these steps exactly:

1. Select one issue ID from `planning/missing-work.md`.
2. Read its summary work package and its technical implementation playbook.
3. Copy the issue ID into the working notes, branch, commit, or final handoff.
4. Confirm status and dependencies. Do not begin an issue marked blocked unless
   the current task is to resolve its blocker.
5. Run the issue's reproduction or first failing check before editing.
6. Record the actual output, tool versions, and whether optional tools skipped.
7. Narrow the change to one semantic/profile/target slice if the issue permits
   multiple choices.
8. Identify schema, model, validation, planning, scenario, renderer, execution,
   closure, migration, test, and documentation owners. Mark non-applicable
   layers explicitly.
9. Define the expected support-state transition before coding.
10. Stop if completing the issue requires a product/security decision, licensed
    evidence that is unavailable, or permission outside the assigned scope.

<a id="source-docsagent-execution-guidemd--issue-intake-record"></a>
#### Issue intake record

Every agent should create this record in its reasoning/work notes before edits:

```text
Issue ID:
Requested outcome:
Current failing behavior:
Reproduction command:
Observed exit/status:
Selected semantic/profile:
Selected target/backend:
In-scope files:
Out-of-scope files:
Schema/model change:
Migration required:
Required tools and versions:
Unit/negative tests:
Real-tool tests:
Closure/status command:
Documentation updates:
Known edge cases:
Blocking decision/evidence:
```

If any field is unknown, inspect the repository. Do not fill unknown fields with
assumptions.

<a id="source-docsagent-execution-guidemd--support-state-transition-rules"></a>
### Support-state transition rules

| From | To | Minimum requirement |
| --- | --- | --- |
| `unsupported` | `scaffold` | Deterministic collateral exists, but no executable/self-checking claim is made |
| `unsupported`/`scaffold` | `partial` | Useful executable behavior with exact limits and measured results exists; incomplete production behavior remains explicit |
| `partial` | `supported` | Complete bounded contract, exact per-check outcomes, good-DUT and mutant evidence, real qualified tools, reproducibility, closure, and strict status |
| `supported` | `regressed`/blocked | A current required test/evidence path fails or becomes stale; retain historical evidence but block promotion |
| Any state | broader state | New endpoint role, target, bound, protocol feature, language, or tool requires separate evidence; support never propagates automatically |

Do not use generated source, compilation alone, process exit zero, aggregate
coverage percentage, mocked vendor output, or an AI proposal as support
promotion evidence.

<a id="source-docsagent-execution-guidemd--standard-implementation-workflow"></a>
### Standard implementation workflow

<a id="source-docsagent-execution-guidemd--step-1-preserve-and-inspect"></a>
#### Step 1: preserve and inspect

Run:

```bash
git status --short
git diff --check
```

Read overlapping changes before editing. Ignore unrelated changes. Never use
destructive Git commands to obtain a clean tree.

<a id="source-docsagent-execution-guidemd--step-2-reproduce"></a>
#### Step 2: reproduce

Use the narrowest public command or test that demonstrates the issue. Examples:

```bash
uv run python -m unittest \
  tests.integration.test_memory_depth_pipeline.GeneratedSecdedMemoryDepthPipelineTests

uv run python scripts/checks/compatibility.py --check
uv run python scripts/checks/maintainability.py --check
uv run mypy
uv run ruff format --check src tests scripts
```

Record exact versions for every external tool involved:

```bash
verilator --version
iverilog -V
ghdl --version
sby --version
yosys -V
z3 --version
```

A skip is not a pass. State whether the skipped tool is optional for the issue
or required for qualification.

<a id="source-docsagent-execution-guidemd--step-3-define-the-contract"></a>
#### Step 3: define the contract

Write down:

- exact design-unit/profile/instance identity;
- endpoint role and target;
- signal/port names, directions, widths, and types;
- clock/reset ownership;
- parameter/bound range;
- assumptions and environmental constraints;
- stimulus, oracle, completion, and timeout behavior;
- required checks, covers, traces, and coverage points;
- unsupported neighboring behavior;
- expected fail-closed diagnostics.

If the contract cannot be stated without phrases such as "normal behavior",
"standard protocol", "as appropriate", or "the obvious clock", the issue is
not ready for implementation.

<a id="source-docsagent-execution-guidemd--step-4-change-contracts-before-renderers"></a>
#### Step 4: change contracts before renderers

Apply changes in this order:

1. JSON schema/version.
2. Domain model/dataclass.
3. Codec and migration.
4. Configuration/import/frontend evidence.
5. Validation and claim gating.
6. Typed scenario and target state.
7. Renderer/generator.
8. Execution command and result decoder.
9. Coverage/closure/status.
10. Documentation and acceptance evidence.

Do not begin by adding template text. A renderer without typed semantics and a
result decoder is a scaffold.

<a id="source-docsagent-execution-guidemd--step-5-add-fail-closed-tests-first"></a>
#### Step 5: add fail-closed tests first

At minimum add:

- valid bounded input;
- missing required field/signal;
- duplicate identity;
- width/type/direction mismatch;
- ambiguous clock/reset/instance;
- unsupported adjacent feature;
- malformed/newer/legacy schema;
- stale plan/generated/run provenance;
- empty/unknown/duplicate result traces;
- known-good DUT;
- targeted mutant for each new semantic rule;
- repeated generation.

For formal changes, add assumption-witness and reachability/non-vacuity tests.
For adapters, add timeout, missing tool/license, malformed report, partial
result, and escaping artifact path tests.

<a id="source-docsagent-execution-guidemd--step-6-implement-narrowly"></a>
#### Step 6: implement narrowly

Prefer existing package boundaries and registries. Add a new abstraction only
when a real contract cannot fit the existing one. Preserve deterministic
ordering, stable IDs, source locators, and public compatibility facades.

Do not:

- infer critical semantics from names/comments;
- silently drop unsupported fields/operators/signals;
- weaken an assertion to fit an engine;
- treat an exception or timeout as an empty pass;
- let plugins set final closure;
- execute shell text produced by models/documents;
- write secrets or raw provider content to logs/audit records.

<a id="source-docsagent-execution-guidemd--step-7-verify-in-layers"></a>
#### Step 7: verify in layers

Run the narrow tests first, then affected integration/qualification tests, then
quality gates. A normal full local sequence is:

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run python scripts/checks/compatibility.py --check
uv run python scripts/checks/maintainability.py --check
uv run python scripts/checks/repository_contracts.py
uv run python scripts/checks/secrets.py
uv run python -m unittest discover -s tests
```

When coverage is required:

```bash
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run coverage json -o .dv-platform/python-coverage.json
uv run python scripts/checks/branch_coverage.py \
  .dv-platform/python-coverage.json
```

Current warning: as of 2026-07-27, the full suite, compatibility,
maintainability, mypy, and format checks have known failures recorded in
`BUG-CDC-01` and `QUALITY-01`. An agent must distinguish pre-existing failures
from new regressions and should close the assigned failures when working those
issues.

<a id="source-docsagent-execution-guidemd--step-8-run-the-public-workflow"></a>
#### Step 8: run the public workflow

For a target/profile promotion, test through the public CLI:

```bash
uv run dv-platform --repo-root /path/to/fixture analyze-rtl
uv run dv-platform --repo-root /path/to/fixture plan --target cocotb
uv run dv-platform --repo-root /path/to/fixture generate --target cocotb
uv run dv-platform --repo-root /path/to/fixture run \
  --target cocotb --module top
uv run dv-platform --repo-root /path/to/fixture coverage --from-runs
uv run dv-platform --repo-root /path/to/fixture status \
  --policy ci
```

Use `--no-require-tools` only in tests explicitly validating policy behavior.
It is not production qualification.

Inspect:

```text
.dv-platform/project-manifest.json
.dv-platform/rtl-facts/
.dv-platform/plans/plans.sqlite
.dv-platform/runs/
.dv-platform/coverage/summary.json
generated/dv-platform/
```

Verify source/config/plan/generated/run/coverage hashes refer to the same
revision and specialization.

<a id="source-docsagent-execution-guidemd--step-9-update-documentation"></a>
#### Step 9: update documentation

Follow `docs/agents.md`. Update:

- capability matrix for current state;
- relevant acceptance or qualification record;
- configuration/CLI contract if behavior changed;
- operator guidance for new runtime behavior;
- missing-work issue status;
- migration and compatibility documentation;
- tool/version/evidence assumptions.

Historical acceptance snapshots should be annotated and linked, not rewritten
as if later features existed at the earlier stage.

<a id="source-docsagent-execution-guidemd--step-10-hand-off"></a>
#### Step 10: hand off

Use this exact structure:

```text
Issue:
Outcome:
Files changed:
Behavior before:
Behavior after:
Support-state change:
Schemas/migrations:
Tests passed:
Real tools and versions:
Tests not run/skipped:
Known remaining gaps:
Evidence/artifact paths:
Documentation updated:
```

Do not say "all tests pass" unless the full command and skip count support that
statement.

<a id="source-docsagent-execution-guidemd--change-recipes"></a>
### Change recipes

<a id="source-docsagent-execution-guidemd--add-a-persisted-field"></a>
#### Add a persisted field

1. Identify owning schema and version constant.
2. Add the field with exact type, bounds, and unknown-field behavior.
3. Update model/dataclass.
4. Update serializer and deserializer.
5. Update migration for every readable old version.
6. Default new legacy semantics to unknown/partial/unsupported.
7. Update hash/canonical ordering.
8. Add round-trip, old-version, newer-version, malformed, and duplicate tests.
9. Update compatibility manifest and docs only after review.

<a id="source-docsagent-execution-guidemd--add-a-scenario"></a>
#### Add a scenario

1. Establish a supported claim from evidence.
2. Build typed stimulus, oracle, completion, coverage goals, check IDs, and
   evidence references.
3. Register target states in the scenario registry.
4. Add renderer for each claimed target.
5. Add stable generated trace IDs.
6. Add exact result decoding.
7. Emit coverage/formal points.
8. Add good-DUT, mutant, non-vacuity, and unsupported-target tests.
9. Run strict status.

<a id="source-docsagent-execution-guidemd--add-a-tool-adapter"></a>
#### Add a tool adapter

1. Define adapter kind/API version and supported tool range.
2. Validate executable and arguments without a shell.
3. Restrict environment and paths.
4. Enforce timeout, output, process, memory, and sandbox policy.
5. Prefer structured native output.
6. Normalize exact check/trace outcomes.
7. Retain tool/version/input/artifact hashes.
8. Treat empty, partial, unknown, timeout, and license failures as non-closing.
9. Add mocked contract tests and separate real-tool qualification.

<a id="source-docsagent-execution-guidemd--correct-documentation-claims"></a>
#### Correct documentation claims

1. Locate machine contract and latest passing evidence.
2. Identify whether each document is current authority or historical snapshot.
3. Record exact contradiction and choose conservative release state.
4. Update current authority and links.
5. Annotate historical records with later promotion/regression links.
6. Add a repository-contract regression fixture.
7. Run `scripts/checks/repository_contracts.py`.

<a id="source-docsagent-execution-guidemd--stop-conditions"></a>
### Stop conditions

Stop and request a decision when:

- the issue changes AI authority, physical sign-off scope, provider routing, or
  another item marked product/security decision;
- a destructive operation, external publication, secret access, license use,
  or unsupported platform expansion was not authorized;
- two authoritative machine records disagree and evidence cannot resolve them;
- required licensed/physical evidence is unavailable;
- a schema migration would intentionally make stored state unreadable;
- fixing a test would require weakening a safety/closure assertion;
- unrelated user changes make the scoped edit impossible.

Do not stop merely because implementation is difficult. Narrow the feature,
preserve fail-closed behavior, and complete a defensible slice.

<a id="source-docsagent-execution-guidemd--agent-self-review-checklist"></a>
### Agent self-review checklist

Before final handoff answer every item:

- [ ] One issue ID and bounded scope are named.
- [ ] Existing user changes were preserved.
- [ ] Current behavior was reproduced.
- [ ] Contract and authority are explicit.
- [ ] Edge cases have required outcomes.
- [ ] Schema/model/codec/migration are consistent.
- [ ] Scenario target state matches renderer and decoder reality.
- [ ] Generated artifacts carry provenance and stable traces.
- [ ] Empty/partial/unknown results are non-closing.
- [ ] Good-DUT and negative/mutant evidence exist.
- [ ] Real tools and versions are reported.
- [ ] Closure and strict status were exercised where applicable.
- [ ] Compatibility and documentation were reviewed.
- [ ] Skips and unavailable evidence are disclosed.
- [ ] No support claim exceeds measured evidence.

<a id="source-docsdocumentation-contractmd"></a>
## Documentation Contract

Consolidated from `docs/documentation-contract.md`.

Document type: current documentation governance authority.

Audience: authors, coding agents, reviewers, release owners, and operators.

Purpose: make every document usable without requiring a reader to infer
authority, time scope, implementation state, hidden prerequisites, or the
meaning of a successful result.

Last reviewed: 2026-07-27.

<a id="source-docsdocumentation-contractmd--core-rule"></a>
### Core rule

Documentation must describe one of these things explicitly:

1. Current product behavior.
2. A historical accepted snapshot.
3. A proposed architecture or implementation plan.
4. An operational procedure.
5. A versioned decision.
6. Retained qualification evidence.

A document must not mix these categories without labeling each section. Terms
such as "supports", "complete", "accepted", "qualified", "passes", and
"production" require a bounded profile, target, tool/evidence class, and time or
evidence identity.

<a id="source-docsdocumentation-contractmd--required-document-header"></a>
### Required document header

New documents and materially revised current-authority documents should begin
with:

```text
Document type: current authority | historical acceptance | architecture |
  decision | operations | roadmap | evidence guide
Authority: machine contract/evidence this document explains
Scope: exact subsystem/profile/target
Status: current | historical | proposed | blocked | superseded
Snapshot/last reviewed: YYYY-MM-DD
Supersedes: document/version or none
Superseded by: document/version or none
Known issues: backlog IDs or none
```

Existing historical acceptance records may retain their original layout, but
must state snapshot date/status and link to later promotion or regression
records when known.

<a id="source-docsdocumentation-contractmd--document-authority-classes"></a>
### Document authority classes

<a id="source-docsdocumentation-contractmd--current-authority"></a>
#### Current authority

Examples: capability matrix, configuration contract, CLI contract, support
policy, security policy.

Required sections:

- scope and explicit non-scope;
- machine contract/schema/configuration owner;
- current behavior and support-state vocabulary;
- prerequisites and supported versions;
- exact commands;
- generated/persisted outputs;
- error and fail-closed behavior;
- edge cases;
- verification/evidence references;
- known regressions/backlog links;
- update procedure.

Current-authority prose must be changed in the same patch as the behavior or
machine contract it describes.

<a id="source-docsdocumentation-contractmd--historical-acceptance"></a>
#### Historical acceptance

Examples: Stage 4/5 acceptance and bounded profile acceptance snapshots.

Required sections:

- snapshot date and accepted commit/evidence when available;
- exact bounded profile;
- target/tool versions;
- good-DUT and mutation/negative matrix;
- commands/workflow exercised;
- measured results and skips;
- explicit exclusions;
- later promotion/regression links.

Historical documents are append-only in meaning. Correct factual mistakes, but
do not rewrite old scope to include later capabilities.

<a id="source-docsdocumentation-contractmd--architecture"></a>
#### Architecture

Required sections:

- problem and system boundary;
- data/control flow;
- owning modules and schemas;
- invariants and trust boundaries;
- decisions already fixed by ADR;
- extension points;
- unsupported semantics;
- failure behavior;
- examples;
- tests/evidence that validate the architecture;
- known divergence from current implementation.

Architecture is not qualification. Phrase proposed behavior as "must" or
"planned", and implemented measured behavior as "does" only with evidence.

<a id="source-docsdocumentation-contractmd--adr"></a>
#### ADR

Required sections:

- status;
- context/problem;
- decision;
- alternatives considered;
- consequences/tradeoffs;
- compatibility/migration impact;
- security/evidence impact;
- supersession rule.

If a later ADR changes the decision, update the ADR index and both records.

<a id="source-docsdocumentation-contractmd--operations"></a>
#### Operations

Required sections:

- audience and prerequisites;
- inputs and safe path boundaries;
- exact command sequence;
- expected outputs;
- validation checks;
- failure/rollback/recovery;
- retention and secret handling;
- concurrency/interruption behavior;
- escalation criteria;
- support/evidence bundle contents.

Commands must be parser-valid. Destructive commands require preview/dry-run and
explicit target constraints.

<a id="source-docsdocumentation-contractmd--roadmapbacklog"></a>
#### Roadmap/backlog

Required fields per issue:

- stable ID;
- priority/status;
- current behavior and reproduction;
- desired bounded behavior;
- dependencies/blockers;
- source/schema/test ownership;
- ordered implementation steps;
- edge cases and required resolution;
- migration/compatibility impact;
- unit/integration/real-tool evidence;
- completion and non-goals;
- documentation updates;
- handoff state.

<a id="source-docsdocumentation-contractmd--qualificationevidence-guide"></a>
#### Qualification/evidence guide

Required sections:

- source-of-truth policy/schema;
- evidence levels and what each proves;
- signer/tool/version requirements;
- freshness/provenance;
- import/verification commands;
- rejection behavior;
- artifact paths;
- promotion conditions;
- examples that must not be interpreted as vendor/production evidence.

<a id="source-docsdocumentation-contractmd--capability-statement-grammar"></a>
### Capability statement grammar

Use this pattern:

```text
<Capability/profile> is <state> for <endpoint role> on <target/backend> with
<explicit bounds> using <tool/version evidence>. It does not cover
<neighboring exclusions>.
```

Good:

```text
The bounded AXI4-Lite subordinate profile is supported for one read and one
write outstanding on cocotb/Icarus 12 and formal/SBY 0.67/Yosys 0.33/Z3 4.8.12.
Bursts, IDs, and more than one outstanding transaction per direction remain
unsupported.
```

Bad:

```text
AXI is fully supported.
```

Never use "supported" when only a contract, schema, template, generated file,
compile check, mock runner, or process exit exists.

<a id="source-docsdocumentation-contractmd--state-vocabulary"></a>
### State vocabulary

| State | Required meaning |
| --- | --- |
| `supported` | The complete stated bounded profile has measured, reproducible, exact per-check evidence on every named target/tool |
| `partial` | Useful executable behavior exists, but one or more stated production obligations remain incomplete |
| `scaffold` | Collateral is generated, but a qualified self-checking execution/result path does not exist |
| `unsupported` | No executable claim; strict workflows report or block the gap |
| `unexecuted` | Expected executable evidence did not run or did not produce mapped outcomes |
| `bounded_pass` | A finite check passed but does not satisfy the stronger closure requirement |
| `regressed` | Previously accepted evidence exists, but a current required path fails or is stale; release promotion is blocked |
| `historical` | True for the stated snapshot; not necessarily the current release state |

Do not substitute "implemented", "complete", "works", or "available" for one
of these states when discussing release capability.

<a id="source-docsdocumentation-contractmd--detail-requirements"></a>
### Detail requirements

Every technical procedure must name:

- exact file or directory;
- exact command and required working directory;
- input format and example;
- output path and schema/version;
- expected exit/status;
- required tool and version;
- behavior for missing/invalid input;
- behavior for timeout/interruption;
- security/path/secret constraints;
- how to verify success;
- how to recover or roll back.

Every design/implementation explanation must name:

- owning class/function/module;
- upstream producer;
- downstream consumers;
- stable IDs and hashes;
- data model/schema;
- validation point;
- fail-closed boundary;
- migration behavior;
- tests and fixtures.

Avoid "handle errors", "validate input", "add tests", "update docs", or
"support protocol" without enumerating the actual errors, fields, tests,
documents, profile, role, target, and bounds.

<a id="source-docsdocumentation-contractmd--edge-case-requirements"></a>
### Edge-case requirements

At minimum, applicable documents must state behavior for:

- absent required data;
- unknown fields/newer schema;
- older schema migration;
- duplicate identities;
- ambiguous mappings;
- contradictory evidence;
- symbolic/unresolved values;
- unsupported target/tool/version;
- empty or partial execution results;
- timeout/interruption;
- stale provenance;
- path escape/symlink;
- secrets/log redaction;
- concurrent publication;
- nondeterministic ordering;
- skipped optional and required tools;
- zero coverage denominator;
- vacuous formal proof;
- parameter-sweep incompleteness.

If an edge case cannot be resolved, name the backlog issue and required product
decision.

<a id="source-docsdocumentation-contractmd--source-references"></a>
### Source references

Use repository-relative links for documents and inline repository-relative paths
for source. Add line numbers only in conversational handoffs; committed
documentation should avoid brittle source-line references.

Prefer links to:

- schemas for data shape;
- configuration/CLI contracts for user interface;
- acceptance/qualification records for evidence;
- ADRs for fixed decisions;
- missing-work IDs for gaps.

Do not link a generated temporary path as permanent evidence.

<a id="source-docsdocumentation-contractmd--command-requirements"></a>
### Command requirements

Commands must:

- run from a stated directory;
- avoid placeholders that resemble literal valid values without explanation;
- use public CLI entry points for user workflows;
- use repository scripts for maintenance checks;
- show required environment variables without secret values;
- avoid destructive commands unless the procedure is specifically about
  governed destruction;
- state whether a command writes state;
- state expected exit behavior.

The repository contract checker parses `dv-platform` examples. After changing
commands run:

```bash
uv run python scripts/checks/repository_contracts.py
```

<a id="source-docsdocumentation-contractmd--evidence-requirements"></a>
### Evidence requirements

A documentation claim should link to or name:

- source/fixture identity;
- configuration/profile;
- tool and version;
- generated provenance hash;
- result summary with exact checks;
- coverage/closure result;
- strict status;
- mutation/negative result;
- signature/attestation for vendor claims.

If evidence is unavailable, use `partial`, `scaffold`, `unsupported`,
`historical`, or `regressed` as appropriate.

<a id="source-docsdocumentation-contractmd--contradiction-procedure"></a>
### Contradiction procedure

When two documents disagree:

1. Do not edit immediately based on prose preference.
2. Record both paths and exact statements.
3. Identify each document class and snapshot.
4. Inspect machine contract and latest passing evidence.
5. Use the conservative current release state.
6. Add/update `DOC-00` or `DOC-02`.
7. Correct current authority.
8. Annotate historical snapshots with later evidence links.
9. Add a repository-contract test preventing recurrence.

<a id="source-docsdocumentation-contractmd--documentation-review-checklist"></a>
### Documentation review checklist

- [ ] Document type, authority, scope, status, and date are explicit.
- [ ] Current and historical statements are separated.
- [ ] Capability statements include profile, role, target, bounds, tools, and exclusions.
- [ ] Source/schema/configuration owners are named.
- [ ] Commands are exact and parser-valid.
- [ ] Inputs, outputs, exits, and artifact paths are documented.
- [ ] Failure, timeout, stale, and unsupported behavior is explicit.
- [ ] Edge cases have resolutions or backlog IDs.
- [ ] Evidence and test paths support every promotion claim.
- [ ] Security, secrets, paths, and destructive behavior are addressed.
- [ ] Migration and compatibility impact are stated.
- [ ] Known regressions are visible.
- [ ] Links and repository contracts pass.

<a id="source-docsdocumentation-contractmd--templates"></a>
### Templates

<a id="source-docsdocumentation-contractmd--current-technical-document"></a>
#### Current technical document

```markdown
# Title

Document type:
Authority:
Scope:
Status:
Last reviewed:
Known issues:

## Purpose
## Supported boundary
## Unsupported boundary
## Data model and ownership
## Workflow
## Configuration
## Inputs and outputs
## Failure behavior
## Edge cases
## Verification and evidence
## Operations
## Compatibility and migration
## Known issues
```

<a id="source-docsdocumentation-contractmd--backlog-issue"></a>
#### Backlog issue

```markdown
#### `ID` Title

**Status:** ...
**Priority:** ...
**Depends on:** ...

**Current behavior and reproduction:** ...
**Required behavior:** ...
**Owned files/contracts:** ...
**Implementation steps:** ...
**Edge cases and resolutions:** ...
**Tests and evidence:** ...
**Completion criteria:** ...
**Non-goals:** ...
```

<a id="source-docsdocumentation-contractmd--historical-acceptance-template"></a>
#### Historical acceptance

```markdown
# Title

Document type: historical acceptance
Snapshot date:
Status:
Profile/targets:
Tools/versions:
Superseded or broadened by:
Known regressions:

## Accepted contract
## Workflow
## Good-DUT evidence
## Mutation/negative evidence
## Traceability and closure
## Explicit exclusions
## Later changes
```
