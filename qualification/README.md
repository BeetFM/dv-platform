# Qualification Evidence

Document type: current qualification operations and evidence index.

Authority: `qualification/policies/ga-gates-v1.json`, packaged qualification
schemas, independently verified evidence, and current clean-checkout results.

Scope: GA stages 6-13, local evidence creation/verification, stage records,
external-design records, performance records, sandbox evidence, vendor
attestations, pilot evidence, and promotion gating.

Status: Stages 6-10 are recorded complete in the ledger. Stage 11 is pending.
Current release promotion is also blocked by `BUG-CDC-01`, `QUALITY-01`,
`DOC-00`, and `DOC-02`.

Last reviewed: 2026-07-27.

Supersedes: none.

Known issues: see
[`docs/planning/missing-work.md`](../docs/planning/missing-work.md).

## Release rule

`policies/ga-gates-v1.json` is the machine-readable gate-state authority. It
does not, by itself, prove that the current checkout passes the tests or still
satisfies an older evidence record. A profile may be accepted only when:

1. Its ledger state and containing stage are valid.
2. Every required evidence path exists and validates.
3. Evidence belongs to the exact source/configuration/profile/target/tool
   identities being promoted.
4. Required end-to-end tests pass in one clean checkout.
5. Required tools ran; required skips, timeouts, or license failures are
   non-closing.
6. Exact checks, mutations/negative cases, coverage, non-vacuity where
   applicable, and strict status close.
7. Vendor claims carry independently verified signatures according to the
   configured trust policy.
8. No current P0 regression blocks the capability or release.

Contract tests, generated projects, mocked results, old attestations, an
integrity hash, or an aggregate process exit cannot substitute for required
real-tool evidence.

## Current gate state

| Stage | Current ledger state | Required interpretation |
| --- | --- | --- |
| 6 | complete | Historical foundation/security evidence paths are present |
| 7 | complete | Historical bounded on-chip protocol evidence paths are present |
| 8 | complete | Historical bounded board-peripheral evidence paths are present |
| 9 | complete | Historical VHDL and project-UVM evidence paths are present |
| 10 | complete | Historical semantic-design, scale/platform, and OCI evidence paths are present |
| 11 | pending | Vendor simulator, formal, and analyzer profiles require fresh independently signed licensed-tool evidence |
| 12 | pending | Requires Stage 11, signed `1.0.0rc1`, and two unrelated enterprise pilots |
| 13 | pending | Requires Stage 12 and final artifact/SBOM/provenance/private-index verification |

The stages are sequential. Preparatory work for a later stage does not permit
promotion while an earlier stage is open. The current SECDED formal and quality
failures mean the working tree must not be described as release-ready even
though the ledger's historical Stage 6-10 entries validate.

## Evidence directories

| Path | Contents | Validation authority |
| --- | --- | --- |
| `policies/ga-gates-v1.json` | Ordered stage/profile ledger | `schemas/qualification/ga-gates-v1.schema.json`, `scripts/qualification/ga_gates.py` |
| `policies/oci-sandbox-runtime-v1.json` | Checked OCI runtime controls and measured evidence | Sandbox qualification tests and policy schema |
| `stages/` | Human-readable bounded stage evidence | Ledger references, exact tests/fixtures, documentation contract |
| `profiles/` | Profile-specific qualification records | Profile contract and named executable evidence |
| `external-designs/` | Source-licensed external-design semantic records | External-design verifier and ledger |
| `performance/` | Platform-specific baseline/current performance records | Performance schemas and `scripts/qualification/performance.py` |
| External governed evidence location | Vendor attestations, signature bundles, pilots, release artifacts | Enterprise importer, trust policy, evidence schema, release procedure |

Do not put secrets, raw customer RTL, provider prompts/responses, private keys,
license files, or unredacted pilot content into checked-in evidence.

## Evidence levels

| Level | Minimum meaning | Permitted claim |
| --- | --- | --- |
| Contract verified | Schema, parser, command construction, and normalized mock behavior pass | Adapter contract exists; no vendor execution claim |
| Tool executed | A named tool/version ran against identified inputs and produced mapped results | Exact bounded run result for that tool only |
| Vendor verified | Licensed vendor tool evidence is imported with source/tool/result identities | Exact vendor run, subject to freshness and trust limits |
| Independently signed | Signature bundle or enterprise-PKI signature verifies over exact attestation bytes using approved trust policy | Signed vendor claim for the exact payload |
| Qualified | Required targets, good DUT, mutants/negatives, exact checks, coverage/non-vacuity, provenance, and strict status all close | Supported bounded profile named by the ledger/capability matrix |

An integrity digest detects payload changes but does not identify a signer. A
mocked vendor report cannot exceed contract-verified status.

## Prerequisites

Run all commands from the repository root.

Required for ledger checks:

- repository dependencies installed through `uv`;
- readable ledger, schema, and referenced evidence files;
- Python package importable in the `uv` environment.

Required to create local GA evidence:

- clean Git checkout with a resolved 40-character commit;
- passing unittest log containing the final `Ran N tests` and `OK` summary;
- coverage JSON with totals and branch data;
- non-empty generated artifact directory containing regular, non-symlink files;
- checked-in `.github/workflows/ci.yml` and `uv.lock`;
- sufficient disk space to hash all tracked files and retained artifacts.

Required for vendor or pilot promotion:

- authorized licensed-tool environment;
- legal, redacted fixture or customer evidence;
- qualification profile matching the exact tool/profile/target;
- approved signature/trust policy;
- release owner approval and the preceding stage complete.

## Step-by-step qualification

### Step 1: preserve and identify the checkout

```bash
git status --short
git rev-parse HEAD
```

Do not discard unrelated changes. Evidence creation intentionally rejects a
dirty checkout because the commit alone would not identify the tested source
tree. A working-tree investigation may proceed, but it cannot create promotable
GA evidence.

### Step 2: validate the ledger structure

```bash
uv run python scripts/qualification/ga_gates.py
```

Expected result: exit `0` and `GA gate ledger is valid`. This verifies identity,
stage order, allowed states, evidence path existence, external-design records,
and required independent-signature fields. It does not run the product tests.

Common exit `1` causes:

- stage number/order is invalid;
- a completed stage appears after an open earlier stage;
- accepted profile lacks evidence;
- referenced evidence file is missing or invalid;
- profile ID is missing/duplicated;
- profile state or target/evidence list is invalid;
- independently signed profile lacks or fails attestation/signature/trust data.

### Step 3: enforce the intended promotion boundary

For the currently accepted historical boundary:

```bash
uv run python scripts/qualification/ga_gates.py --through-stage 10
```

Expected result: exit `0` only when every stage and profile through Stage 10 has
the required accepted state. Running through Stage 11 currently returns exit
`1` because the three Stage 11 profiles are pending. Do not change pending to
accepted merely to make this command pass.

### Step 4: run mandatory repository checks

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run python scripts/checks/compatibility.py --check
uv run python scripts/checks/maintainability.py --check
uv run python scripts/checks/repository_contracts.py
uv run python scripts/checks/secrets.py
```

Every command must exit `0`. As of 2026-07-27, format, mypy, compatibility, and
maintainability fail under `QUALITY-01`; qualification must stop until those
failures are resolved or a release authority explicitly changes the policy.

### Step 5: run tests and capture coverage

Use an evidence workspace outside the artifact directory:

```bash
mkdir -p .dv-platform/qualification
uv run coverage run -m unittest discover -s tests \
  2>&1 | tee .dv-platform/qualification/unittest.log
uv run coverage report
uv run coverage json \
  -o .dv-platform/qualification/coverage.json
uv run python scripts/checks/branch_coverage.py \
  .dv-platform/qualification/coverage.json
```

The test command currently fails on `BUG-CDC-01`; do not continue to evidence
creation from that log. Review all skips. A skip is acceptable only if the
profile being qualified does not require that tool and the final claim excludes
it.

The evidence creator parses the final unittest summary. Concatenating an old
passing log after a new failure is invalid evidence even if the parser finds an
`OK` block; reviewers must bind logs to the same job and commit and inspect the
complete job result.

### Step 6: run profile-specific real-tool workflows

For every profile/target being promoted:

1. Run the public `analyze-rtl`, `plan`, `generate`, `run`, `coverage`, and
   strict `status` workflow where applicable.
2. Retain source/configuration/plan/generated/run/coverage/status identities.
3. Run the known-good DUT.
4. Run every required mutant or negative fixture.
5. Verify exact check/trace/coverage IDs, not only aggregate counts.
6. Verify formal assumptions have reachable witnesses and required covers.
7. Record exact tool versions and platform identity.
8. Place only the governed, redacted, non-secret deliverables in the artifact
   directory used by the next step.

Use the profile's stage record for exact commands and bounds. If the stage
record lacks enough detail to repeat the run, treat that as a documentation gap
and do not infer the missing command.

### Step 7: create commit-bound evidence

After all commands pass in a clean checkout and the artifact directory is
non-empty:

```bash
uv run python scripts/qualification/ga_evidence.py create \
  --stage 10 \
  --root . \
  --test-log .dv-platform/qualification/unittest.log \
  --coverage .dv-platform/qualification/coverage.json \
  --artifacts .dv-platform/qualification/artifacts \
  --output .dv-platform/qualification/ga-evidence-v1.json
```

Change `--stage` only to the stage actually being qualified. The command writes
schema-v1 JSON and exits `0` after recording:

- commit;
- deterministic digest of tracked source files;
- CI workflow and lockfile digests;
- passed/skipped/failed test counts;
- combined and branch coverage;
- Python and `uv` versions;
- SHA-256 for every regular, non-symlink artifact;
- payload digest and `passed` status.

The command exits `1` for a dirty checkout, unresolved commit, invalid stage,
missing passing unittest summary, missing coverage totals, empty artifact set,
invalid JSON, or unreadable input.

### Step 8: verify local evidence

```bash
uv run python scripts/qualification/ga_evidence.py verify \
  --input .dv-platform/qualification/ga-evidence-v1.json
```

Expected result: exit `0` and `GA evidence verified`. Verification checks
schema/status identity, payload digest, commit/tree/workflow/lockfile digest
shape, at least one passed test with zero failures, numeric coverage, and a
non-empty artifact identity map.

Important boundary: this verifier validates evidence document integrity. It
does not rerun tests, recompute artifact hashes against a supplied directory,
verify freshness, or verify an external signer. Release review must perform
those additional comparisons.

### Step 9: import and verify vendor evidence

Stage 11 records must use `dv-enterprise qualify import` through the enterprise
qualification profile. The import must bind:

- exact attestation bytes;
- qualification profile;
- source, configuration, generated artifact, and tool identities;
- normalized exact results and coverage;
- signature manifest;
- approved trust policy;
- signer identity and verification result.

The ledger state for Stage 11 profiles is `independently_signed`, not merely
`vendor_verified`. Keep mocked adapter tests separate from real licensed
evidence. A missing license, timeout, malformed native report, unknown check,
stale source identity, untrusted signer, or signature mismatch is non-closing.

### Step 10: review promotion

Before changing any ledger state:

1. Verify all earlier stages are complete.
2. Re-run ledger validation and enforcement.
3. Recompute source/artifact identities against retained evidence.
4. Verify required tests, mutants, exact checks, coverage, non-vacuity, and
   strict status.
5. Confirm no P0 regression applies.
6. Confirm capability/acceptance/operations documents use the same bounded
   state.
7. Obtain the required independent reviewer/release-owner approval.
8. Change only the exact stage/profile state supported by evidence.
9. Run repository contracts and affected qualification tests.

## Stage-specific notes

### Stage 8 board peripherals

Evidence is recorded in
[`stages/stage8-board-peripherals.md`](stages/stage8-board-peripherals.md).
The accepted profiles are deliberately bounded. They do not imply unlisted
electrical, bus, multi-controller, timing, DMA, or analog behavior.

### Stage 10 performance

Records use
`schemas/qualification/performance-qualification-v1.schema.json` or the
current v2 performance schema as applicable and are compared with:

```bash
uv run python scripts/qualification/performance.py \
  qualification/performance/ubuntu24-scale-baseline-v2.json \
  qualification/performance/ubuntu24-scale-current-v2.json \
  --require-ga-scale
uv run python scripts/qualification/performance.py \
  qualification/performance/wsl2-scale-baseline-v2.json \
  qualification/performance/wsl2-scale-current-v2.json \
  --require-ga-scale
```

Ubuntu 24.04 and WSL2 Ubuntu 24.04 require separate records with identical
input identities. Do not merge results across platforms or replace a missing
platform record with extrapolation.

### Stage 11 vendor qualification

Vendor records are imported through `dv-enterprise qualify import`. Their
integrity hash is necessary but not a signing claim. Broad-GA evidence also
requires a separately verified Sigstore bundle or enterprise-PKI signature
tied to the exact attestation bytes and approved trust policy.

### Stage 12 pilots

Pilot evidence must be redacted and content-free while retaining RC wheel
digest, project/tool profile, exact status/check counts, artifact
reproducibility digest, upgrade/rollback outcome, and approver identity. The
SystemVerilog-heavy and VHDL or mixed-tool pilots must use unrelated designs.
Do not retain customer source, paths that reveal customer identity, logs with
source excerpts, prompts, responses, credentials, or license data.

### Stage 13 promotion

Only Stage 13 may publish `1.0.0` with a production classifier. Promotion is a
metadata-only transition from the accepted `1.0.0rc1` artifact lineage and must
verify final artifact hash, signature, SBOM, provenance, and private-index
installation without rebuilding different bytes.

## Rejection and edge cases

- **Dirty tree:** investigate locally, but do not create GA evidence.
- **Detached but resolved commit:** permitted by the evidence creator if clean;
  release policy must still prove branch/tag provenance.
- **Submodule or untracked input:** not represented by the tracked-tree digest
  unless separately bound; qualification must reject or add explicit identity.
- **Symlink artifact:** excluded by the creator; required evidence behind a
  symlink is therefore missing.
- **Empty artifact directory:** rejected.
- **Zero test count or any failed test:** rejected.
- **Required skip:** non-closing even though schema-v1 can record skips.
- **Zero branch denominator:** the creator reports 100%; reviewers must reject
  this for a profile requiring branch evidence because no branches were
  measured.
- **Unknown/newer schema:** reject until a versioned reader/migration exists.
- **Old schema:** preserve original meaning; migration must not promote state.
- **Hash match without signature:** integrity only, not signer authenticity.
- **Valid signature with stale source/tool/profile:** reject.
- **Partial/malformed/empty vendor result:** `unexecuted` or failed.
- **Concurrent evidence publication:** write to a staging path, verify, then
  atomically publish; never let readers consume a partial file.
- **Interrupted run:** discard partial artifacts or retain them only as
  diagnostic, explicitly non-promotable evidence.
- **Contradictory prose and ledger:** preserve ledger state, choose the
  conservative release claim, and resolve `DOC-00`/`DOC-02`.

## Qualification change checklist

- [ ] Exact stage/profile/role/target/bounds are named.
- [ ] Ledger and packaged schema validate.
- [ ] Current checkout is clean and commit-resolved.
- [ ] Mandatory quality checks pass.
- [ ] Full and profile-specific tests pass.
- [ ] Required tools ran at recorded versions.
- [ ] Good DUT and complete mutation/negative matrix close.
- [ ] Exact checks and coverage points map to stable identities.
- [ ] Formal evidence includes non-vacuity/reachability where required.
- [ ] Source/configuration/generated/run/coverage/status provenance agrees.
- [ ] Artifacts are non-empty, regular, redacted, and free of secrets.
- [ ] Vendor evidence has approved independent signature verification.
- [ ] No P0 regression invalidates the claim.
- [ ] Capability, acceptance, operations, and release documents agree.
- [ ] Evidence verification and repository contract tests pass.

## Validation commands

For ledger/evidence changes, run:

```bash
uv run python scripts/qualification/ga_gates.py
uv run python -m unittest \
  tests.qualification.test_ga_gates \
  tests.qualification.test_ga_evidence \
  tests.qualification.test_enterprise_qualification \
  tests.qualification.test_external_design_evidence
uv run python scripts/checks/repository_contracts.py
```

Add profile-specific qualification tests named by the changed stage record.
Report every command, result, tool version, and skip in the handoff format from
the [Agent Execution Guide](../docs/agent-execution-guide.md).
