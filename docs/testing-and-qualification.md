# Testing and qualification

Every change must pass Ruff, formatting, mypy, the branch-coverage ratchet,
wheel build, installed-wheel smoke tests, and dependency audit. CI also checks
documentation links/examples/schema declarations, malformed inputs, secrets,
static security findings, and release supply-chain outputs.

A GA profile additionally requires good-DUT end-to-end execution, a declared
mutation matrix with every mutant killed by the expected check, exact result
traceability, qualified tool versions, reproducible generated artifacts, and no
skips. Contract tests do not constitute vendor qualification. Vendor records
must be fresh, signed/controlled, and tied to exact tool versions; external pilot
records must come from two unrelated customer designs.

Performance qualification records stage runtime and peak RSS for a
multi-million-line RTL repository and large XML/PDF inputs. A release candidate
fails when a comparable baseline regresses by more than 10%. No such broad-scale
benchmark or two-pilot evidence is currently checked into this repository.

`dv-enterprise benchmark` writes performance-qualification v2 evidence with
platform/kernel/tool identity, commit and wheel digests, complete input
fingerprints, runtime, peak RSS, and reproducibility metadata. Stage 10 requires
identical ≥2,000,000-line RTL, ≥128 MiB XML, and ≥64 MiB PDF fingerprints on
native Ubuntu 24.04 and WSL2 Ubuntu 24.04.
