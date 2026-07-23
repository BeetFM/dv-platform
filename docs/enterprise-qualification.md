# Enterprise qualification without proprietary licenses

dv-platform separates adapter correctness from access to proprietary EDA installations. A profile's qualification level is evidence, not a marketing claim.

## Qualification levels

| Level | Meaning |
| --- | --- |
| `unverified` | No qualification evidence is recorded. |
| `contract_verified` | Versioned schemas, result normalization, traceability, security boundaries, and deterministic fixtures passed. |
| `surrogate_verified` | The applicable workflow also passed on an installed open-source tool. This establishes workflow equivalence, not vendor equivalence. |
| `vendor_verified` | A portable bundle was run against the named proprietary installation and its tamper-evident attestation was imported. |
| `independently_signed` | The exact vendor attestation also has a valid detached signature from a policy-approved certificate chain whose identity is distinct from every declared project identity. |

Levels are monotonic. Re-running a lower-level check is retained in qualification history but cannot downgrade the current record.

## Contract qualification

```console
dv-enterprise qualify --profile questa --mode fixture
```

Contract qualification uses packaged, hashed simulator, formal, or analyzer result fixtures. It requires no EDA installation or license.

## Open-source surrogate qualification

```console
dv-enterprise qualify --profile spyglass --mode surrogate --probe verilator_lint
dv-enterprise qualify --profile questa --mode surrogate --probe iverilog
dv-enterprise qualify --profile jaspergold --mode surrogate --probe yosys
```

Available probes are `verilator_lint`, `verilator_simulator`, `iverilog`, `ghdl`, `yosys`, and `symbiyosys`. Commands are executed directly without a shell, inherit only a bounded environment, have bounded runtime and output, and record the actual version reported by the executable.

Surrogate qualification records the exact families and languages exercised. It must never be described as validation of proprietary tool behavior.

## Portable vendor bundle

Create a self-contained ZIP archive without needing the vendor installation locally:

```console
dv-enterprise qualification-bundle --profile questa --output questa-qualification.zip
```

To qualify collateral rendered by Veriforge's UVM backend, add
`--generated-uvm`. The bundle then includes a deterministic ready/valid UVM
environment and loopback DUT and requires `QUAL-UVM-001` in addition to the
simulator contract check:

```console
dv-enterprise qualification-bundle \
  --profile questa --generated-uvm \
  --output questa-uvm-qualification.zip
```

The archive contains immutable HDL fixtures, normalized-result schema, qualification request, instructions, and a standalone Python runner. On the licensed host, a site wrapper runs the fixtures and writes the normalized result indicated by `DV_PLATFORM_RESULT_PATH`:

```console
python run_qualification.py \
  --tool-name Questa \
  --tool-version 2026.1 \
  -- ./site-questa-qualification-wrapper
```

The runner checks every fixture hash and required check identity. It records only the executable name, return code, normalized result, tool identity, timestamps, and content hashes. Command arguments, source trees, environment values, and raw logs are not included.

Import the returned attestation:

```console
dv-enterprise qualify \
  --profile questa \
  --mode vendor \
  --attestation qualification-attestation.json
```

An unsigned import stops at `vendor_verified`. Stage 11 requires an independent
signer to sign the exact attestation bytes. Veriforge does not accept a
self-declared signer: the certificate must chain to the configured CA, its
RFC2253 subject, issuer, and DER SHA-256 fingerprint must all match an approved
signer, and its subject must not match any `project_identities` entry.

First create the canonical signing statement. It binds the signature purpose,
exact attestation digest, signature scheme, and declared signing time:

```console
dv-enterprise qualification-signing-payload \
  --attestation qualification-attestation.json \
  --signed-at 2026-07-22T12:00:00Z \
  --output qualification-signing-payload.json
```

The independent signer creates a raw SHA-256 detached signature over those
canonical statement bytes:

```console
openssl dgst -sha256 -sign independent-signer.key \
  -out qualification-attestation.sig qualification-signing-payload.json
```

Place the signature and public certificate beside a
`qualification-signature.json` manifest:

```json
{
  "schema_version": 1,
  "purpose": "veriforge-vendor-qualification",
  "signature_kind": "enterprise_pki",
  "attestation_sha256": "<sha256 of the exact attestation bytes>",
  "signature_file": "qualification-attestation.sig",
  "certificate_file": "independent-signer.pem",
  "signed_at": "2026-07-22T12:00:00Z"
}
```

The approving organization maintains a separate trust policy. Relative paths
are resolved within the policy directory; absolute paths and traversal are
rejected:

```json
{
  "schema_version": 1,
  "project_identities": ["CN=Veriforge Release"],
  "approved_signers": [{
    "kind": "enterprise_pki",
    "identity": "CN=Independent Qualification Lab",
    "issuer": "CN=Qualification CA",
    "certificate_sha256": "<sha256 of signer certificate DER>",
    "trust_root": "qualification-ca.pem"
  }]
}
```

Verification is available without changing qualification state:

```console
dv-enterprise verify-qualification-signature \
  --attestation qualification-attestation.json \
  --signature-manifest qualification-signature.json \
  --trust-policy qualification-trust-policy.json
```

Import and promote the record to `independently_signed` only after verification:

```console
dv-enterprise qualify \
  --profile vivado_xsim --mode vendor \
  --attestation qualification-attestation.json \
  --signature-manifest qualification-signature.json \
  --trust-policy qualification-trust-policy.json
```

The checked-in schemas are `qualification-signature-v1.schema.json` and
`qualification-trust-policy-v1.schema.json`. Private keys are deliberately
outside Veriforge's command surface.

The GA ledger cannot promote a Stage 11 profile by changing its state string
alone. An `independently_signed` profile must name its tool qualification
profile, attestation, signature manifest, and trust policy; the gate performs a
fresh fail-closed import and cryptographic verification in an isolated
temporary state directory.

### AMD Vivado Simulator from WSL

The `vivado_xsim` generated-UVM bundle includes `run_vivado_xsim.py`. AMD Vivado
Simulator ships a precompiled UVM 1.2 library; the wrapper supplies `-L uvm`,
the XSim timescale overrides, and fail-closed report checks. For a Windows Vivado
installation accessed from WSL, extract the bundle on a Windows-mounted path and
run:

```console
python run_qualification.py \
  --tool-name "AMD Vivado Simulator" \
  --tool-version 2025.2 -- \
  python run_vivado_xsim.py \
  --vivado-bin /mnt/c/AMDDesignTools/2025.2/Vivado/bin \
  --cmd-exe /mnt/c/Windows/System32/cmd.exe
```

The accepted 2025.2 attestation is retained under `docs/evidence` and is
re-imported in tests, so generator drift invalidates qualification evidence.

## Policy enforcement

Set a repository-wide minimum:

```console
dv-enterprise qualification-policy \
  --minimum-level contract_verified \
  --max-age-days 365
```

Set a stronger profile-specific minimum:

```console
dv-enterprise qualification-policy \
  --profile questa \
  --minimum-level independently_signed
```

`dv-enterprise status --policy ci` and the primary `dv-platform status --policy ci` fail when a configured runner is below policy, its record is corrupt, or its evidence is stale. The default policy is `unverified`, preserving existing deployments until they explicitly adopt a qualification gate.

Records and policy are stored under `.dv-platform/qualification`. Every successful attempt is retained under `history`; the highest current level is stored under `records`.
