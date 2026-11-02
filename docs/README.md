# Physical-design workflow

## RTL optimization

`dv-enterprise rtl-optimize` reads declared Verilog/SystemVerilog and UTF-8 design documents,
freezes their exact bytes, and asks for bounded edits grounded in both source and document
evidence. Each experiment starts from that immutable RTL baseline. It must pass sequential
equivalence, technology mapping and mapping equivalence, OpenROAD implementation with standalone
OpenSTA replay, and final-netlist equivalence. Candidates compete against the current best
measurement while retaining the original constraints and acceptance gates. The selected objective
must improve, and no requirement gap may grow. Rejected trials inform subsequent proposals;
there are at most three. Neither an equivalent candidate nor an improved candidate grants sign-off.

Create an RTL project JSON beside the source and design documents:

The [RTL project schema](../schemas/signoff/rtl-project-v1.schema.json) describes the closed
format. Runtime validation additionally checks file identity, source subsets, and the selected
physical project's protected inputs.

```json
{
  "schema_version": 1,
  "design": "cpu_top",
  "sources": ["rtl/top.sv"],
  "documents": ["docs/design.md"],
  "physical_project": "physical/project.json",
  "netlist": "mapped.v",
  "mapping_library": "technology/lib/tt_025C_1v80.lib",
  "objective": "setup_wns_ns"
}
```

The physical project remains operator-authored. `netlist` names its replaceable mapped-netlist
input; `mapping_library` names one of its timing libraries. Objectives are `setup_wns_ns`
(increase), `area_um2` (decrease), or `power_watts` (decrease). The runner copies the template
and synthesizes both the baseline and candidates with the same fixed mapping commands.
SKY130 mapping uses the approved library's tie cells. The v2 source-reference input is populated
from the corresponding RTL lowering; the proof chain retains the original source comparison.

Explicitly add `rtl_optimization` to `[ai].allowed_stages` before allowing source/documents to
reach the configured provider. A signed routing policy must permit that purpose as well.
Headroom can include this stage in `[context_optimization].stages`; source, documents,
requirements, measured evidence, and history remain protected from lossy compression.

```bash
rtk proxy uv run --env-file .env dv-enterprise --config dv-platform.toml --allow-network --json rtl-optimize --project /path/to/rtl-project.json --max-iterations 3
```

The command requires the existing Enterprise CLI and adapter capabilities. Exit zero means a
proven candidate improved the selected physical objective; no improvement, provider failure,
or execution failure returns nonzero with the retained run record. Original source and physical
project files are never edited. Changed documents, stale edits, ambiguous matches, path
traversal, and symlink inputs are rejected. Run native tools only on trusted source projects;
the workspace copy is not an operating-system sandbox. Cycle/architecture changes require a
separate functional verification contract.

Package-based SystemVerilog can select a pinned `sv2v` converter using these optional RTL
project fields:

```json
{
  "editable_sources": ["rtl/top.sv"],
  "memory_mb": 8192,
  "frontend": {
    "kind": "sv2v",
    "executable": "tools/sv2v",
    "sha256": "<the converter executable SHA-256>",
    "defines": ["SYNTHESIS", "VERILATOR"]
  }
}
```

List all compilation units and headers in `sources`, with packages before their users. The
runner copies the converter and checks its digest before and after conversion. `SYNTHESIS`
must be among the explicit macro definitions. Simulation-only `translate_off` blocks are
removed from derived conversion inputs while the original source bytes remain retained.
Conversion uses at most two RTS workers and a heap capped at 2 GiB or half the address-space
budget, whichever is smaller. The default frontend remains Yosys.

`editable_sources` defaults to all sources. When specified, only those files reach the model
and only those files may change; every dependency is still compiled and included in the proof.
Supply necessary semantic context in design documents when excluding dependency files from
the model input. `memory_mb` defaults to 6144 and is bounded to 256–262144 MiB for conversion,
Yosys lowering, mapping, and proofs. Host memory-reserve protection still applies.

Derived physical projects retain the original baseline reference, both raw source versions,
design documents, converter/configuration when used, and candidate decision/proof records as
hashed inputs. Their source identity describes the RTL experiment; prior template metadata
is retained only as template provenance.

The selected result exposes `best.project` and `best.run`. Pass these exact files to
`dv-enterprise signoff check` to build and verify its release. That check retains the original
RTL reference and requires independent layout, power, activity, and approval gates.

The spacing-repaired full 8×8 INT8/INT32 matrix benchmark completed all nine native gates:
original nine-view timing, both complete equivalence stages, KLayout and Magic DRC,
antenna, density, Netgen LVS and ERC. Both DRC decks, antenna, density and ERC report
zero violations; LVS matches uniquely. Both proofs cover all 257 outputs and 4,015
next-state bits. The [completed run is retained](../qualification/evidence/PHYS-01/tpu-spacing-repaired-completed-qualification-local-v1.json).
Fresh routed-netlist tests pass all 256 matrix results, and nine-view activity replay
reports 100% annotation coverage with unchanged timing.

The density-clean 750 micrometre AES implementation now also passes all nine
native gates, with complete 129-output/530-next-state proofs, nine-view timing,
zero KLayout/Magic DRC, zero antenna/density findings and uniquely matched LVS/ERC.
Its [completed qualification](../qualification/evidence/PHYS-01/aes-final-pin-completed-nine-native-gate-qualification-local-v1.json)
and fresh three-vector routed activity replay are retained. This is a different
physical experiment from the earlier small-floorplan manual AES comparison
(2.17% less cell area and +0.602 ns setup); those earlier gains are not attributed
to the new 750 micrometre implementation.

Remaining completion gates:

- Supply approved operating constraints, area/power/IR/EM budgets, representative mission
  activity, supply-source locations and conductor dimensions, then rerun every required
  analysis and obtain independent engineering and manufacturing approvals. Existing
  known-answer activity characterization does not establish mission power signoff.
  Both completed benchmark releases still report requirements, activity, power-grid,
  IR-drop and EM checks as unknown.
- Complete layout/power qualification for the recovered live-provider AES candidate.
  The engineer-guided cofactor edit passed full source/mapped/final proofs and
  initially improved setup by 0.527 ns with 0.36% less cell area. Its original
  interrupted optimizer record remains untouched; a separate recovery verified
  selection. Subsequent stricter repair and a targeted two-branch physical ECO
  now close all nine timing views with zero native DRC/antenna findings and a
  fresh complete proof. This is not independent model discovery, a new controlled
  paired RTL claim, or approved signoff. See the [original recovery](../qualification/evidence/PHYS-01/aes-cofactor-provider-recovered-native-improvement-local-v1.json)
  and [electrical-closure evidence](../qualification/evidence/PHYS-01/aes-cofactor-two-branch-native-electrical-closure-local-v1.json).

The external benchmarks replace the full CPU as the current completion target. CPU and
frontend examples remain available, with no CPU-scale closure claim.

The physical repair loop described below tunes native repair settings while preserving RTL.

A project JSON manifest declares the design, flow Tcl, input assets, SDC constraints, Liberty libraries, and expected parasitics path. Paths are relative to the manifest directory. Every input must be declared; inputs and constraints are hashed before execution.

Use the [SKY130 v2 workflow](sky130-signoff.md) for the pinned benchmark blocks, complete PVT/RC replay, native layout/power checks, and independently approved releases. The v1 example below remains supported for the retained qualification fixture.

```json
{
  "schema_version": 1,
  "design": "gcd",
  "flow": "gcd_closure.tcl",
  "inputs": ["gcd_closure.tcl", "gcd.v", "constraints.sdc", "cells.lib"],
  "constraints": ["constraints.sdc"],
  "libraries": ["cells.lib"],
  "parasitics": "results/design.spef"
}
```

Real flows must also declare their technology LEFs, helper scripts, and other assets. The pinned runnable GCD fixture is in `.dv-platform/openroad-live/fixture/`; its asset hashes and upstream revision are in [the fixture policy](../qualification/policies/openroad-fixture-v1.json).

## Execution

The runner copies declared inputs into an isolated case directory, runs OpenROAD, extracts metrics and critical paths, then independently replays timing in standalone OpenSTA. Both processes must agree. Input and resolved-constraint fingerprints detect mutations and constraint relaxation.

For AI execution the gateway supplies the current analysis, quantified requirement gaps, evidence IDs, and experiment history. The model returns a hypothesis and validated repair settings: capacitance/slew margins, setup/hold margins, and gate cloning. These settings invoke fixed native commands. Each candidate starts from the source flow, is measured, and is compared against the incumbent and original baseline limits. Rejected results feed the next decision; duplicate recipes are rejected. There are at most three candidate iterations.

The source flow and physical strategy remain operator-authored. The AI does not invent arbitrary placement or clock-tree Tcl. Final acceptance requires the configured timing, electrical, routing, area, and power checks to pass. A failed or unavailable model call is recorded as such.

## Configuration

`dv-platform.toml` holds paths, network policy, security, product entitlement, AI, and context settings. Unsupported fields and invalid TOML value types are rejected. Both installed and source CLIs honor configured entitlements; explicit missing configuration paths fail. Provider credentials are resolved from the named environment variable. Signed routing policies can restrict destinations and data classes. Plugin loading checks entitlement, version, publisher, and signatures before importing external code.

`context_optimization` supports `off`, `advisory`, and `required` modes for Headroom and the local code graph. Headroom is restricted to a loopback HTTP endpoint. Optimized prompts must preserve required anchors; advisory failures fall back to the original bounded prompt. Use `dv-platform context-optimize build-graph` or `update-graph` to maintain the graph. PD runs include bounded advisory graph context and record its provenance. Required optimizer failures stop the run; Headroom compresses advisory context; measured evidence, requirements, and iteration history remain protected in the reconstructed prompt.

## Evidence and limits

Each execution retains native logs, metrics, constraint fingerprints, proposals, rejected trials, and the selected result. The execution record always keeps `signoff_approved=false`; its built-in logical-equivalence state is `not_checked`. Independent qualification checks are described in [verification](verification.md).

With `product.require_production_signoff=true`, `dv-platform --json status --policy ci` requires valid engineering and manufacturing approvals for a complete release. This repository enables that gate. Projects retaining the v1 policy instead check required cached physical domains. A signed physical-evidence import is separate from optimization. Cached domain results share the same design/input identity and become unknown when their evidence or waivers expire. Imports require parsed findings for every declared corner and mode. Entitlement concurrency bounds apply to native runs. The qualification signing key establishes local fixture trust only.
