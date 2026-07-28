# Agent Execution Guide

Document type: current operational authority for coding agents.

Audience: Codex models, automated implementation agents, reviewers, and human
maintainers assigning repository work.

Scope: how to select, implement, verify, document, and hand off changes in this
repository. This guide does not redefine product capabilities; it explains how
to work on them without inferring missing policy.

Last reviewed: 2026-07-27.

## Mandatory starting state

Before reading a feature document or editing code, establish these facts:

1. The repository may contain user changes. Run `git status --short` and never
   discard, reset, overwrite, or reformat unrelated work.
2. The current working tree has known P0 blockers recorded in
   [Missing Work](planning/missing-work.md):
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

## Authority and precedence

Use this order when two sources disagree:

1. **Security and user instructions.** Explicit user scope, repository security
   policy, and approved destructive/external actions always take precedence.
2. **Versioned machine contracts.** JSON schemas, persisted schema versions,
   configuration validators, scenario target states, plugin API contracts, and
   `qualification/policies/ga-gates-v1.json`.
3. **Fresh measured evidence.** Exact clean-checkout tool runs tied to source,
   plan, generated-artifact, tool-version, result, coverage, and status hashes.
4. **Current P0 regression records.** The rescan section and P0 issues in
   `docs/planning/missing-work.md` can temporarily block a previously accepted
   capability without erasing its historical evidence.
5. **Current capability authority.** `docs/qualification/capability-matrix.md`
   and `docs/qualification/verification-production-readiness.md`, once their
   known `DOC-00`/`DOC-02` conflicts are resolved.
6. **Qualification stage records.** Files under `qualification/stages/` state
   what was accepted at a stage and with which tools/fixtures.
7. **Acceptance snapshots.** Files under `docs/acceptance/` are historical,
   bounded records. A later stage may supersede a limitation without making the
   old snapshot false for its date.
8. **Architecture and ADRs.** ADRs constrain design unless superseded.
   Architecture documents explain intent but do not promote execution support.
9. **Planning prose.** Implementation plans explain sequence. They are not
   evidence that an item is implemented or qualified.

Conflict rule: never average claims or choose the newest-looking prose. Record
the exact conflicting files, use the less permissive state for release/CI, and
open or extend a `DOC-*` issue.

## Required reading by task

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
| Change release qualification | `qualification/README.md`, GA contract/stages | Gate ledger, evidence schemas, CI/release workflows |
| Documentation-only correction | `documentation-contract.md`, `DOC-00`/`DOC-02` | Machine evidence supporting every changed capability statement |

## Ticket pickup procedure

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

### Issue intake record

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

## Support-state transition rules

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

## Standard implementation workflow

### Step 1: preserve and inspect

Run:

```bash
git status --short
git diff --check
```

Read overlapping changes before editing. Ignore unrelated changes. Never use
destructive Git commands to obtain a clean tree.

### Step 2: reproduce

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

### Step 3: define the contract

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

### Step 4: change contracts before renderers

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

### Step 5: add fail-closed tests first

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

### Step 6: implement narrowly

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

### Step 7: verify in layers

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

### Step 8: run the public workflow

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

### Step 9: update documentation

Follow `docs/documentation-contract.md`. Update:

- capability matrix for current state;
- relevant acceptance or qualification record;
- configuration/CLI contract if behavior changed;
- operator guidance for new runtime behavior;
- missing-work issue status;
- migration and compatibility documentation;
- tool/version/evidence assumptions.

Historical acceptance snapshots should be annotated and linked, not rewritten
as if later features existed at the earlier stage.

### Step 10: hand off

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

## Change recipes

### Add a persisted field

1. Identify owning schema and version constant.
2. Add the field with exact type, bounds, and unknown-field behavior.
3. Update model/dataclass.
4. Update serializer and deserializer.
5. Update migration for every readable old version.
6. Default new legacy semantics to unknown/partial/unsupported.
7. Update hash/canonical ordering.
8. Add round-trip, old-version, newer-version, malformed, and duplicate tests.
9. Update compatibility manifest and docs only after review.

### Add a scenario

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

### Add a tool adapter

1. Define adapter kind/API version and supported tool range.
2. Validate executable and arguments without a shell.
3. Restrict environment and paths.
4. Enforce timeout, output, process, memory, and sandbox policy.
5. Prefer structured native output.
6. Normalize exact check/trace outcomes.
7. Retain tool/version/input/artifact hashes.
8. Treat empty, partial, unknown, timeout, and license failures as non-closing.
9. Add mocked contract tests and separate real-tool qualification.

### Correct documentation claims

1. Locate machine contract and latest passing evidence.
2. Identify whether each document is current authority or historical snapshot.
3. Record exact contradiction and choose conservative release state.
4. Update current authority and links.
5. Annotate historical records with later promotion/regression links.
6. Add a repository-contract regression fixture.
7. Run `scripts/checks/repository_contracts.py`.

## Stop conditions

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

## Agent self-review checklist

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
