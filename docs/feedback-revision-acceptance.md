# Feedback and revision closure acceptance

This document defines the qualified Stage 3 boundary. A feedback revision is
accepted only when its intent lineage and all replacement evidence are fresh.

| Roadmap requirement | Qualified implementation |
| --- | --- |
| Revision schema v3 | Immutable snapshots bind canonical-plan, RTL/project-manifest, parent-snapshot, affected dependency, scenario-selection, and rerun-target metadata. Legacy revisions remain readable. |
| Changed inputs | Canonical-plan or project-manifest drift rejects the chain unless feedback explicitly requests a fork. Snapshot and parent hashes are rechecked at generation. |
| Operation lifecycle | Every proposal records `proposed` followed by `validated` and `applied`/`no-op`, or `rejected` with a stable reason. |
| Dependency closure | Stable edges connect requirements, checks, scenarios, generated symbols, artifacts, runs, and coverage points. The selected closure is persisted per revision. |
| Targeted generation | Only affected paths are replaced within the selected target/module. Unrelated files and target/module directories are preserved; provenance is always refreshed. |
| Bounded AI synthesis | AI can only select existing scenario IDs and unchanged declared parameter values. It cannot add code, commands, renderers, checks, waivers, or executable claims. |
| Common AI record | Planning, scenario synthesis, and feedback persist purpose, sanitized endpoint identity, hashes, cache state, diagnostics, retry/token/cost metadata, and deterministic fallback reason. |
| Mandatory fresh evidence | `status --policy ci` rejects an actionable latest revision until every required target is generated, rerun with the exact provenance hash, and included in a passing coverage import. |

The qualified sequence is:

```text
feedback -> generate --revision -> run -> coverage --from-runs -> status --policy ci
```

Tests cover schema round trips, explicit forks, stale/tampered snapshots,
malformed lifecycle state, dependency selection, unrelated-byte preservation,
stale-run invalidation, bounded synthesis repair/fallback, audit permissions, and
the full pending-generation/pending-run/pending-coverage/closed transition.
