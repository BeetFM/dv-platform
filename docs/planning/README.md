# Planning Index

Document type: current planning index.

Authority: the classification and precedence described below.

Scope: staged roadmap history and the current implementation backlog.

Status: current.

Last reviewed: 2026-07-27.

## Documents

- [Missing Work](missing-work.md) is the current regression register and
  agent-ready backlog. Its P0 list, dependency-aware pickup index, source
  ownership map, implementation sequence, edge-case policy, and ticket
  playbooks are actionable.
- [Implementation Plan](implementation-plan.md) is historical staged design
  context. Its stage labels record intended or accepted progress at a point in
  time and are not current release evidence.

## Agent procedure

1. Read the repository [Agent Execution Guide](../agent-execution-guide.md).
2. Read the current baseline and rescan result in Missing Work.
3. Select one row from the zero-assumption pickup index.
4. Confirm `Ready`, dependencies, required decisions, tool availability, and
   the first reproduction or inspection step.
5. Read the summary ticket and the corresponding technical playbook.
6. Execute the common completion contract and ticket-specific completion
   evidence.
7. Update ticket state, current capability docs, historical links, and exact
   evidence in the same change.
8. Use the handoff template in the Agent Execution Guide.

Do not infer issue completion from roadmap prose, a generated file, a unit test,
or process exit zero. The issue closes only when its bounded evidence and
strict-status requirements are satisfied.

## Adding work

Before creating a new ID, search Missing Work for the same ownership boundary.
Extend an existing ticket when the new finding has the same root cause,
dependencies, schema, and completion evidence. Create a new ticket when it has
an independent support-state transition or can be completed separately.

Every new issue must contain:

- stable ID, priority, status, and dependencies;
- current behavior and exact reproduction;
- required bounded behavior and non-goals;
- owning schemas, modules, adapters, fixtures, and docs;
- ordered implementation steps;
- edge cases with required outcomes;
- unit, integration, real-tool, mutation, closure, and compatibility evidence;
- explicit completion signal and handoff state.

Follow the [Documentation Contract](../documentation-contract.md) and add the
issue to the pickup index.
