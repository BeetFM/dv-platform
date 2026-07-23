# Stage 5 target and adapter acceptance

Snapshot date: 2026-07-21.

This acceptance compares roadmap Stage 5 with the implemented target runners,
tool qualification policy, and adapter connections. It distinguishes repository
implementation from evidence that can only be produced on a licensed deployment.

## Roadmap comparison

| Roadmap requirement | Implemented evidence | Acceptance |
| --- | --- | --- |
| Qualify generated UVM with one licensed simulator | `qualification-bundle --generated-uvm` packages byte-stable UVM produced by `UvmGenerator`, its loopback DUT, content hashes, and mandatory `QUAL-UVM-001`. AMD Vivado Simulator 2025.2 compiled and ran that exact UVM 1.2 environment with 16 scoreboard transactions and zero UVM errors/fatals. | Accepted for the paired ready/valid UVM profile. The tamper-evident `vivado_xsim` attestation is checked in and re-imported by the regression suite. Conservative fallback UVM remains scaffolded. |
| Native SystemVerilog and Verilog normalized results | Icarus wrappers compile the manifest-bound RTL and generated bench, execute `vvp`, and require exact `DV_PLATFORM_RESULT_V1` records for every generated trace. Unknown, duplicate, partial, malformed, zero-result, or failed outcomes do not close checks. | Accepted for the generated reset-to-constant vertical slice; broader native scenario depth remains partial. |
| VHDL/GHDL normalized results | The VHDL generator emits type-correct observable reset checks and result records. The GHDL runner analyzes, elaborates, and runs VHDL-2008 collateral and uses the same exact trace decoder. | Accepted for the observable reset vertical slice with GHDL 4.1.0. The real pipeline closes through coverage and CI status; broader VHDL behavior remains partial. |
| Tested tool ranges | CI status and run summaries classify the real backend, not a Python wrapper. Enforced ranges are Verilator 5, Icarus 12, SBY 0.67, Yosys 0.33, Z3 4.8, and GHDL 4–5. SBY records Yosys and Z3 separately. The vendor attestation retains exact Vivado Simulator 2025.2 identity. | Accepted. Presence without a supported version is insufficient in CI policy. |
| Connect document/OCR, embedding, vector, reporting, policy, coverage, simulator, and formal adapters | Versioned entry points now include local text/PDF and governed OCR-sidecar loaders, local hash embeddings, JSON vector storage, deterministic report manifests, regex redaction, UCIS XML, five simulator profiles, and three formal profiles. Indexing and planning use configured document/embedding/vector adapters. Enterprise execution produces normalized closure points. | Accepted for the named built-in contracts. Proprietary database/API depth remains vendor-specific. |
| Vendor exit code must never close checks | Native and enterprise execution both require normalized, traceable, non-empty results. Strict enterprise execution rejects missing trace IDs and skipped/unknown states; a passing process without a result remains non-closing. | Accepted. |

## Qualified native subset

The native SystemVerilog, Verilog, and VHDL generators are executable only for a
normalized reset-to-constant behavior with a stable mapped check. VHDL further
requires every checked target to be an observable entity port. Other scenarios
retain their renderer-registry `scaffold` or `unsupported` state. This is a
deliberately narrow qualification and does not promote native APB4, AXI4-Lite,
CDC, memory, or general behavioral benches.

## Vivado Simulator UVM qualification

AMD documents that Vivado Simulator provides a precompiled UVM 1.2 library and
requires `-L uvm` for standalone `xvlog` and `xelab`. The `vivado_xsim` bundle
includes a dedicated wrapper which applies that library plus a global elaboration
timescale required by XSim. The accepted run used the Windows Vivado 2025.2
installation from WSL:

```console
dv-enterprise qualification-bundle \
  --profile vivado_xsim \
  --generated-uvm \
  --output vivado-xsim-uvm-qualification.zip
```

The wrapper requires reference simulation completion, the named generated UVM
test, UVM phase completion, and zero UVM errors/fatals before emitting normalized
passing checks. A process exit without those markers fails. The imported evidence
is [Vivado XSim 2025.2 qualification attestation](evidence/vivado-xsim-2025.2-qualification-attestation.json),
with `vendor_verified` checks `QUAL-SIM-001` and `QUAL-UVM-001`.

## Verification

The current integrated run passes 578 tests with one expected optional skip: the
opt-in live-AI smoke test. With Slang 11.0.424 on `PATH` and the qualified gate
enabled, all three Slang tests run and pass. The GHDL integration is active and
passes against GHDL 4.1.0.
It includes real Icarus native compilation/execution, the installed formal
toolchain, exact result-decoder negative cases, deterministic UVM bundle and
attestation tamper tests, adapter entry-point/CLI tests, and the real GHDL
pipeline. Ruff, formatting, mypy, and every coverage ratchet pass. Measured
combined coverage is 86.23%, statement coverage is 89.13%, and true branch
coverage is 78.25% across 5,302 branches. Source/wheel builds and the dependency
audit also pass.
