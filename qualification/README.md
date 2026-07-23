# Qualification evidence

`ga-gates-v1.json` is the release source of truth. A profile may be accepted
only when its evidence paths exist and the required end-to-end tests are
repeatable. Contract or surrogate results must never be relabeled as vendor
evidence.

Stage 8 board-peripheral evidence is recorded in
`stage8-board-peripherals.md`. The accepted profiles are deliberately bounded;
the evidence does not imply support for unlisted electrical, bus, or controller
modes.

Stage 10 performance records use
`schemas/qualification/performance-qualification-v1.schema.json` and are compared with
`scripts/qualification/performance.py --require-ga-scale`. Ubuntu 24.04
and WSL2 Ubuntu 24.04 require separate records with identical input identities.

Stage 11 vendor records are imported through `dv-enterprise qualify import`.
Their integrity hash is necessary but not a signing claim: broad-GA evidence
must also include a separately verified Sigstore bundle or an enterprise PKI
signature tied to the exact attestation bytes.

Stage 12 pilot evidence must be redacted and content-free, but retain the RC
wheel digest, project/tool profile, exact status/check counts, artifact
reproducibility digest, upgrade/rollback outcome, and approver identity. The
SystemVerilog-heavy and VHDL or mixed-tool pilots must be unrelated designs.
