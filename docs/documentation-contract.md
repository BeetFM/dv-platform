# Documentation Contract

Document type: current documentation governance authority.

Audience: authors, coding agents, reviewers, release owners, and operators.

Purpose: make every document usable without requiring a reader to infer
authority, time scope, implementation state, hidden prerequisites, or the
meaning of a successful result.

Last reviewed: 2026-07-27.

## Core rule

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

## Required document header

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

## Document authority classes

### Current authority

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

### Historical acceptance

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

### Architecture

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

### ADR

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

### Operations

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

### Roadmap/backlog

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

### Qualification/evidence guide

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

## Capability statement grammar

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

## State vocabulary

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

## Detail requirements

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

## Edge-case requirements

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

## Source references

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

## Command requirements

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

## Evidence requirements

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

## Contradiction procedure

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

## Documentation review checklist

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

## Templates

### Current technical document

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

### Backlog issue

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

### Historical acceptance

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
