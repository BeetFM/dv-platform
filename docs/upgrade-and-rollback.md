# Upgrade and rollback

Before upgrade, stop writers, record `dv-platform --json status`, verify the
current wheel checksum, back up every SQLite database and config, and validate
each backup with `PRAGMA integrity_check`. Install the candidate wheel into a
new environment and run status plus an analyze/plan/generate dry qualification
against a non-production copy. Never let an older binary write state after a
newer schema has modified it.

Rollback means stopping writers, restoring the previous environment and the
matching pre-upgrade work-directory backup, then validating status and a known
qualification project. Do not point the old wheel at migrated state. Destructive
migrations require an explicit dry-run report and are prohibited without a
verified backup.

`dv-platform backup --output PATH` and `dv-platform migrate --backup PATH` are
dry runs unless `--apply` is supplied. Applied backups use content-addressed
manifests and SQLite's backup API plus `PRAGMA integrity_check`; migrations
refuse non-adjacent schema jumps and require a verified backup.

`dv-platform destroy` is the separate governed path for run evidence,
counterexamples, generated collateral, and backup sets. It is dry-run by
default and requires an authorization reference, an exact configured target,
a verified recovery backup, and a versioned legal-hold registry. Active holds
fail closed; symbolic links are never traversed.
