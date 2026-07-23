# Backends and output layout

The [capability matrix](../qualification/capability-matrix.md) is authoritative for backend
depth. A generated file is not evidence of executable support. Unsupported
semantics remain explicit plan gaps.

Machine state lives under `<work-dir>`: frontend facts and manifests, retrieval
indexes, plan/revision SQLite stores, run summaries, coverage, review data, and
owner-only audit records. Generated collateral lives under `<output-dir>` by
family, target, and module. Each published module includes provenance and an
execution manifest with input and artifact hashes. Consumers must not infer
support from paths; use schema fields and status policy.

Aggregate `run --all` supports the global `--json` envelope and includes ordered
module results plus the persisted aggregate-summary path. Report adapters may
write only below configured export roots.
