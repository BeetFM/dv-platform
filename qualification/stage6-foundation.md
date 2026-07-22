# Stage 6 foundation qualification

Accepted on 2026-07-22 against the `0.1.0` development lineage. CI reruns the
controls below; this record identifies the gate and is not a waiver for a
future failure.

- 500 unit/integration tests passed with four declared optional-tool skips.
- Combined coverage was 86.15%, statement coverage was 89.08%, and true branch
  coverage was 78.15% across 5,468 branches; every versioned ratchet passed.
- Ruff lint/format and mypy passed.
- Repository contracts, the GA ledger, and tracked-file secret scanning passed.
- Bandit reported no high-severity findings; `pip-audit --skip-editable`
  reported no known dependency vulnerabilities.
- SQLite backup/restore integrity, bounded retention purge, export allowlists,
  symlink/path rejection, plugin publisher/hash checks, environment-backed
  secrets, redaction, malformed JSON/XML/PDF handling, and backward-readable
  persisted schemas are covered by executable tests.
- Two independent `uv build` invocations produced byte-identical wheels and
  source distributions.
- The release dry run generated a deterministic SPDX 2.3 SBOM, basename-only
  checksums, and SLSA/in-toto provenance; independent verification passed and
  tampering/path traversal tests failed closed.

Artifact signing and private-index publication are deliberately later-stage
release controls. This stage does not claim vendor, pilot, WSL, or broad-scale
qualification.
