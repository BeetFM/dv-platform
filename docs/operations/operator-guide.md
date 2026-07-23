# Operator guide

Install the signed wheel on Python 3.11–3.13 in Linux or WSL, verify its checksum
and signature, then follow [installation](config/installation.md) and
[configuration](config/configuration.md). The production sequence is analyze →
index → plan → generate → run/prove → coverage → `status --policy ci`.

Archive the exact config, wheel checksum, project manifest, normalized facts,
plans/revisions, generated provenance, run summaries, coverage reports, and
status JSON. A zero tool exit without mapped checks is not success. Treat
timeouts, interrupted summaries, stale provenance, unsupported constructs, and
traceability gaps as open failures.

Back up SQLite databases with SQLite's backup API or `.backup`, then run
`PRAGMA integrity_check` against the copy. Restore into an empty work directory
and run status in report mode before allowing CI policy evaluation. See
[upgrade and rollback](upgrade-and-rollback.md) for release changes.

Review retention candidates with `dv-platform purge --as-of YYYY-MM-DD`; repeat
with `--apply` to delete only the fixed transient-state allowlist. The command
never deletes plan, run, coverage, generated, or backup evidence and refuses any
symlink in scope.
