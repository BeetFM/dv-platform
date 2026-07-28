# Acceptance Evidence Index

Document type: historical acceptance index and reading procedure.

Authority: the bounded commands, fixtures, tool versions, and measured outcomes
recorded by each acceptance document at its snapshot.

Scope: documents under `docs/acceptance/`.

Status: historical evidence. These files do not override current regressions or
the machine-readable GA ledger.

Last reviewed: 2026-07-27.

Known issues: `BUG-CDC-01`, `DOC-00`, and `DOC-02` in
[Missing Work](../planning/missing-work.md).

## How to use an acceptance record

An agent or release reviewer must perform these steps:

1. Read the record's date, accepted profile, endpoint role, target, tool
   versions, bounds, exclusions, and skipped tools.
2. Identify the exact good-DUT fixture, negative fixture or RTL mutant,
   generated artifact, result decoder, coverage point, and strict status result.
3. Verify whether a later qualification stage broadened the profile.
4. Check [Missing Work](../planning/missing-work.md) for a current regression.
5. Check the [Capability Matrix](../qualification/capability-matrix.md) for the
   intended current state, subject to its known `DOC-00`/`DOC-02` conflicts.
6. Check `qualification/policies/ga-gates-v1.json` for release gate state.
7. Use the least permissive current state whenever current evidence conflicts.
8. Never edit an older record to imply that a later capability existed at the
   original snapshot. Add a dated "Later changes" note and link instead.

An acceptance record proves only its stated bounds. It does not automatically
prove another protocol role, parameter value, target, simulator, formal engine,
HDL language, tool patch release, operating system, or customer design.

## Record index

| Record | Historical purpose | Read with |
| --- | --- | --- |
| [P0 Pilot Acceptance](pilot-acceptance.md) | Initial end-to-end pilot workflow and correctness boundary | Current P0 regressions and capability matrix |
| [P1 Expansion Acceptance](p1-acceptance.md) | Broader specialization, closure, document, coverage, and UVM snapshot | Current backlog and later stage records |
| [Bounded APB4](apb4-acceptance.md) | APB4 generated open-tool profile and mutation boundary | Stage 7 native promotion and `DOC-02` |
| [Bounded AXI4-Lite](axi4-lite-acceptance.md) | Five-channel bounded AXI4-Lite profile | Stage 7 native promotion and `DOC-02` |
| [Feedback and Revision](feedback-revision-acceptance.md) | Immutable revision lineage and regeneration | Current revision schema and migration docs |
| [CDC Synchronizer](cdc-synchronizer-acceptance.md) | Bounded CDC structures and mutation evidence | `BUG-CDC-01`, `CDC-01`, and current CDC policy |
| [Async FIFO](async-fifo-acceptance.md) | Governed power-of-two asynchronous FIFO behavior | `CDC-01` for unsupported FIFO/CDC shapes |
| [Reset/RDC](reset-rdc-acceptance.md) | Logical reset release and power sequencing | `RDC-01` and `PHYS-01` for physical evidence |
| [Memory Depth](memory-depth-acceptance.md) | Bounded SRAM/parity snapshot | SECDED later evidence, `BUG-CDC-01`, and `DOC-02` |
| [Formal Depth](formal-depth-acceptance.md) | Bounded-response assumptions, invariants, liveness, and non-vacuity | `FORM-01` for unsupported formal semantics |
| [Parameter Sweep](parameter-sweep-acceptance.md) | Deterministic bounded elaboration points | Current parameter policy and scale records |
| [VHDL Normalization](vhdl-normalization-acceptance.md) | Initial bounded VHDL normalization | Stage 9/10 evidence, `VHDL-01`, and `DOC-02` |
| [Stage 4](stage4-acceptance.md) | Roadmap-to-implementation snapshot for Stage 4 | Later stage records and current capability matrix |
| [Stage 5](stage5-acceptance.md) | Native result contracts and initial target boundary | Stage 7/9 promotions and `DOC-02` |

## Required evidence interpretation

| Evidence | What it can prove | What it cannot prove |
| --- | --- | --- |
| Generated source or project | Deterministic renderer output exists | Compilation, execution, checking, coverage, or support |
| Compile/elaboration success | Tool accepted the bounded input | Functional correctness or mutation detection |
| Process exit zero | Process completed according to adapter mapping | Exact checks passed unless result traces map them |
| Exact check traces | Named checks reached pass/fail outcomes | Coverage closure or absence of vacuity by themselves |
| Coverage points | Declared behavior points were measured | Correct oracle behavior or unlisted behavior |
| Good-DUT run | Expected implementation can satisfy the contract | Checker sensitivity to defects |
| Killed mutant/negative fixture | One specified defect is detected | Other fault classes or a broader profile |
| Bounded formal pass | Property holds under stated bound/assumptions | Unbounded behavior or physical timing |
| Assumption witness/cover | Environment is reachable in the modeled bound | Completeness of real deployment assumptions |
| Mocked vendor result | Adapter/parser contract behavior | Licensed vendor execution |
| Signed vendor attestation | Exact signed run and payload identity | A different commit, tool version, profile, or customer design |

## Failure and edge-case rules

- Missing fixture, log, tool version, source hash, result trace, or evidence path
  makes the claim incomplete.
- A skipped required tool is non-closing. An optional skip must be named and
  excluded from the support statement.
- Empty, duplicate, unknown, or unmatched result identities are non-closing.
- A passing old commit does not close a regression on the current commit.
- A newer schema must reject unless explicitly readable; an older schema must
  migrate conservatively and must not gain support state by default.
- A timeout, license failure, malformed report, killed process, or partial
  artifact publication is `unexecuted` or failed, never a pass.
- Formal evidence without reachability/non-vacuity evidence cannot promote
  liveness or environment-dependent claims.
- Aggregate coverage cannot conceal a missing mandatory point, ignored bin,
  zero denominator, or uncovered parameter point.
- Evidence copied across targets, tools, profiles, roles, or specializations is
  invalid unless the identity contract explicitly proves equivalence.

## Updating this directory

Follow the [Documentation Contract](../documentation-contract.md). For a new
acceptance record:

1. Add the required historical metadata.
2. Name exact profile, role, target, bounds, tools, fixtures, mutations, and
   commands.
3. Record exact passes, failures, skips, coverage, and strict status.
4. State unsupported adjacent behavior.
5. Link current capability state and backlog items.
6. Add the record to this index and the main [Documentation Index](../README.md).
7. Run:

```bash
uv run python scripts/checks/repository_contracts.py
uv run python -m unittest \
  tests.documentation.test_docs \
  tests.repository.test_repository_contracts
```
