# Capability Matrix

Snapshot date: 2026-07-20.

States have strict meanings:

- `supported`: implemented and accepted only with measured per-check evidence.
- `partial`: useful executable behavior exists, but the production profile is not complete.
- `scaffold`: collateral can be emitted, but it is not a qualified self-checking path.
- `unsupported`: no executable claim is made; strict workflows must report or block the gap.

## Generation and execution targets

| Target | Generation | Compile/elaboration | Per-check execution | Current state |
| --- | --- | --- | --- | --- |
| cocotb/Icarus | Self-checking generic/ready-valid checks and bounded APB4 scenario driver, monitor, register reference model, scoreboard, and timeouts | Python syntax is mandatory; Icarus/cocotb is optional locally and mandatory only in its hosted profile | JUnit test identities map to stable checks; zero or unmatched tests remain `unexecuted` | `supported` for the qualified generic pilot; APB4 is `partial` pending the full mutant matrix |
| formal/SymbiYosys | Harnesses, assumptions, safety properties, covers, CDC tiers, and protocol assertions | Generated structure is checked; proof execution requires configured SBY/Yosys/solver tools | Prove/cover tasks map to stable checks; bounded and unsupported results do not close sign-off | `supported` for the qualified formal subset; APB4/register depth is `partial` |
| SystemVerilog | Conservative bench plus assertions/covers, including APB setup/access/wait stability | Verilator lint is used when available | Native runners without a normalized check result cannot mark checks covered | `partial` |
| Verilog | Conservative stimulus scaffold | Verilator lint is used when available | A zero process exit does not create check evidence | `scaffold` |
| VHDL | Conservative stimulus scaffold | GHDL validation is used when available | A zero process exit does not create check evidence | `scaffold` |
| UVM | Package/environment scaffold | No repository-qualified licensed simulator path | The built-in validator deliberately fails closed | `scaffold` |

## Protocol and register depth

| Profile | Recognition | Scenario/generation depth | State |
| --- | --- | --- | --- |
| APB4 slave | Complete named PSEL/PENABLE/PREADY/PWRITE/PADDR/PWDATA/PSTRB/PRDATA/PSLVERR interface, directions, widths, and clock/reset facts are retained; ambiguity becomes an unsupported semantic | Typed transfer/register scenarios; bounded cocotb completion; RW/RO/W1C reference behavior; byte strobes; error observation; SV/formal setup, access, wait stability, completion covers | `partial` until good/broken DUT fixtures and mandatory real-tool mutation runs cover every behavior |
| AXI4-Lite slave | Complete five-channel ready/valid signature and optional payload signals | Typed one-read/one-write outstanding scenario exists; current generated channel probes/assertions do not yet implement the full independent AW/W scoreboard and negative mutant set | `partial` |
| AHB-Lite | Bounded single-beat signature | Executable probes and stability assertions exist | `partial` |
| Ready/valid | Named source/sink channel recognition | Backpressure and data-stability checks | `supported` within the qualified pilot constraints |
| Register model | Offset, fields, reset/access metadata, byte-enable and invalid-address policies from governed/normalized sources | A scenario is executable only when dependent semantics are known; unknown behavior stays open | `partial` |

## Platform services

| Capability | State | Boundary |
| --- | --- | --- |
| Plan schema v17 | `supported` | Each scenario records `executable`, `scaffold`, or `unsupported` per target with renderer identity and reason. Plans v1-v16 remain readable; v16 static mappings migrate to `unsupported` and require re-planning. |
| Immutable revisions v2 | `supported` | Additive operations persist a full resulting-plan snapshot and distinct hash. `generate --revision` loads that snapshot; legacy metadata-only revisions remain readable but cannot be selected for generation. |
| Validation result v1 | `supported` | Simulation/formal summaries carry a common check-result envelope. No checks or unmatched tool output is `unexecuted`, regardless of exit code. |
| LiteLLM planning | `partial` | Explicit opt-in, bounded context/output, local cache, credential indirection, content-free audit, deterministic fallback, and proposal v1 compatibility exist. Planning now uses the common same-model repair gateway; proposal v2 adds evidence-linked scenario intent. |
| Reusable AI gateway | `partial` | Planning and feedback analysis use the shared gateway; repair is capped at two attempts and fallback is deterministic. `scenario_synthesis` is reported inactive. Cross-provider routing and model-authored code are unsupported. |
| Feedback closure | `partial` | `feedback --from-runs --ai` can propose additive checks/coverage goals; accepted operations change snapshot hashes. Dependency-level artifact merge/preservation and rerun orchestration remain open. |
| Plugins | `partial` | Versioned loading contracts and selected coverage/semantic/requirements/enterprise adapters are connected. Declared document/vector/report/redaction/generator extension kinds are not all production-qualified. |

## Production milestone

The open-tool production milestone is not yet accepted. Acceptance requires one APB4 and one bounded AXI4-Lite slave workflow to generate, compile, execute/prove, emit non-vacuous evidence for every executable check, close coverage, detect deliberately broken DUTs, and produce byte-identical deterministic artifacts when AI is disabled or falls back.
