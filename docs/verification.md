# Verification

## Automated checks

```bash
uv sync --all-groups --extra ai --frozen
make check
make test
make verify-evidence
uv run coverage run -m unittest discover -s tests -v
uv run coverage json -o .dv-platform/python-coverage.json
uv run python -m scripts.checks.branch_coverage .dv-platform/python-coverage.json
```

Tests cover requirement and repair validation, iterative acceptance and regression rejection, independent STA agreement, HTTP model transport, signed routing, entitlement and plugin boundaries, context compression, MCP cleanup, evidence tampering, and separate package contents. Provider transport tests use a local HTTP fixture. They do not prove a live AI call.

Compatibility fingerprints cover the current public APIs, CLI help, entrypoints, schemas, and native Tcl driver. `repository_contracts` checks documentation links, local manifest records, and artifact hashes when available. Qualification evidence and artifacts under `qualification/evidence/` are private local files ignored by Git; evidence links below require those local files. Run `make verify-evidence` locally to require evidence manifests and every referenced artifact and verify every digest. CI runs these checks on Python 3.11, 3.12, and 3.13, builds both distributions, and audits dependencies. Native tool qualification requires a provisioned host.

## Native qualification

### External AES benchmark

The OpenROAD/OpenCores AES-128 encryption block is pinned under
`qualification/fixtures/aes/`, including its original license, upstream revision,
and file hashes. It replaces the full CPU as the next bounded qualification target;
CPU qualification remains unfinished. Preparation checks three known-answer
vectors, lowers the unmodified RTL, maps SKY130 cells under a 4096 MiB limit, and
creates a fresh nine-view physical project and an RTL optimization manifest:

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.aes --output .dv-platform/aes-new
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.sky130 qualify --project .dv-platform/aes-new/physical/project.json --output .dv-platform/aes-qualification-new
```

After baseline qualification, the existing configured-provider loop accepts the
generated `.dv-platform/aes-new/rtl-project.json` through
`scripts.qualification.rtl_live`. Keep the same provisional constraints for every
comparison. Known-answer simulation, formal equivalence, physical qualification,
and measured optimization are separate results; preparation alone proves none of
the latter three. The small simulation waveform is retained as test evidence and
is not declared an approved power workload. No production approval is issued.

The [first full-AES live-loop attempt](../qualification/evidence/PHYS-01/aes-live-baseline-proof-failure-local-v1.json)
stops before any model call because physical optimization removes 44 direct
state-name anchors. All 530 registers remain present; the fallback leaves output
obligations unproven. The [native proof-chain replay](../qualification/evidence/PHYS-01/aes-routed-proof-chain-local-v1.json)
passes logical-to-mapped and mapped-to-routed equivalence with the same exact
intermediate netlist and functional libraries. RTL measurement now uses that
checked chain and rejects a changed intermediate hash or library set. This does
not treat missing state correspondence as equivalence or omit any proof obligation.
The [proof-chain validation](../qualification/evidence/PHYS-01/current-signoff-and-rtl-chain-validation-local-v1.json)
retains 291 passing tests, repository checks, a measured coverage gate and the
workflow sources at that integration point, including a native zero-finding Magic
feedback control.

The [configured full-AES RTL run](../qualification/evidence/PHYS-01/aes-live-rtl-execution-local-v1.json)
makes two real provider calls and proves a MixColumns rewrite equivalent. Native
measurement rejects the candidate's capacitance regressions and retains the
baseline; no improvement is claimed. A
[later attempt](../qualification/evidence/PHYS-01/aes-live-context-bound-failure-local-v1.json)
completes its native baseline but exceeds the 100,000-character prompt bound
before any provider call. The
[bounded-context correction](../qualification/evidence/PHYS-01/rtl-context-bound-validation-local-v1.json)
factors repeated per-scenario gates, measurements and history, keeping every
source, design document, metric value and evidence ID. Historical passed-check
boilerplate is reconstructible from the retained metrics and unchanged gates;
every unmet check and regression remains explicit. All 313 tests and quality
checks pass. Full-AES context serialization uses 74,591 characters without
history and 95,176 with two history entries in a labeled test-double stress test.
The [configured-provider retry](../qualification/evidence/PHYS-01/aes-live-bounded-context-stop-local-v1.json) then makes two real calls and accepts one response, which proposes no edit because the physical-to-source function mapping remains insufficient. No candidate is measured and no RTL improvement is claimed; the context test-double outcome is not a live-model result.
The [proof-chain endpoint bridge](../qualification/evidence/PHYS-01/aes-proof-chain-source-provenance-local-v1.json) composes both complete 530-state bijections through an exactly matching mapped model and confirms the worst path is from sa01[2] to sa31[1]. It quotes the corresponding source dependency equations; intermediate combinational cell/function boundaries remain unavailable. The 88.469 ns value is slack, whereas absolute arrival is 12.179 ns. The [one-iteration provider trial](../qualification/evidence/PHYS-01/aes-live-source-provenance-stop-local-v1.json) consumes this evidence and completes its native baseline, but makes two provider calls and returns no edit. It asks for per-operation delay attribution; no candidate or accepted improvement is claimed.

The [published Canright S-box experiment](../qualification/evidence/PHYS-01/aes-canright-source-proof-local-v1.json) pins OpenTitan revision `30d7e787c753caaa03fe68a4a70da1bbcbc1d96f` and retains its Apache-2.0 license and original source. A forward-only adapter preserves all 256 original table entries, passes native SAT with a wrong-affine-bit negative control, proves every AES output and all 530 next-state bits, and passes all three original AES known answers. It preserves the source include directive. This is a manually prepared external candidate, not a live AI response or side-channel qualification. The [completed physical experiment](../qualification/evidence/PHYS-01/aes-canright-physical-rejection-local-v1.json) also passes mapped-to-final equivalence, but is not selected for the unchanged setup objective: area falls 32.6% (86,307.78 to 58,200.82 square micrometres), setup slack falls 5.28044 ns (88.46940 to 83.18896 ns), and worst slew remains negative at -26.3271%. The vectorless power estimate rises from 6.99369 to 337.18169 mW; no mission-workload power claim is made. The original baseline is retained and no accepted RTL improvement or layout signoff is claimed.
A subsequent [exact routed known-answer replay](../qualification/evidence/PHYS-01/aes-canright-switching-characterization-local-v1.json) passes all three AES vectors at the original 100 ns clock, achieves 100% activity coverage in all nine independent OpenROAD/OpenSTA views, and estimates at most 1.173289 mW under those tests. Timing and resolved constraints remain identical. This explains why the 337.18169 mW vectorless estimate must not be treated as measured mission power; the replay uses logical cell functions without SDF delay/glitch simulation. It does not reverse the setup-objective rejection or establish approved workload, power budgets, IR/EM, or signoff.

The [state-alias matching correction](../qualification/evidence/PHYS-01/state-alias-priority-validation-local-v1.json) fixes 20 ambiguous register matches exposed by a truth-table-preserving S-box lookup reordering. Source RTL aliases take priority over recycled generated names, while generated-only state matching retains the original fallback. Complete state bijection, clock validation and every output/next-state obligation remain required. The fresh native proof passes all 129 AES outputs and 530 next-state bits; a deliberately wrong table entry reaches a native SAT assertion failure. All 318 tests, coverage gates and repository checks pass with the compatibility fingerprint unchanged. The [completed lookup-order experiment](../qualification/evidence/PHYS-01/aes-lookup-order-rtl-improvement-local-v1.json) is selected by the fixed setup objective with no nine-view acceptance regressions: worst setup slack improves by 0.746752 ns (88.469399 to 89.216151 ns) and cell area falls from 86,307.78125 to 83,959.273438 square micrometres (about 2.72%). Source, mapping and routed proofs cover all 129 outputs and 530 next-state bits, with identical clocks and SDC hashes. Slew (-2.37555%) and capacitance (-4.17964%) still fail, so this is a measured RTL improvement rather than timing closure or layout/signoff approval. The candidate is manually source-derived, not a live-provider proposal.

The [incremental RTL guidance validation](../qualification/evidence/PHYS-01/rtl-incremental-guidance-validation-local-v1.json) clarifies that an already-failing baseline does not rule out measuring improvement without regressions. It preserves every native acceptance gate and distinguishes selection from closure and signoff. Current production selection exactly reproduces the retained manual experiment, including eight unmet requirements; all 318 tests and repository checks pass with compatibility unchanged. [Current distributions](../qualification/evidence/PHYS-01/incremental-guidance-distribution-build-local-v1.json) pass isolated installation, both CLI checks, and byte checks for 63 Python files and 14 runtime assets. The [clarified provider reproduction attempt](../qualification/evidence/PHYS-01/aes-live-lookup-clarified-reproduction-stop-local-v1.json) made one actual call but returned no edits, so it does not establish successful live AI optimization. The [live validation of the corrected guidance](../qualification/evidence/PHYS-01/aes-live-incremental-guidance-stop-local-v1.json) also produces no edit: one response fails source/document citation validation, and the repaired response recognizes the incremental hypothesis but declines to provide the full 256-entry exact-text replacement. No native candidate is measured, so successful live-provider optimization remains unproven.

The [subsequent native electrical repair](../qualification/evidence/PHYS-01/aes-lookup-electrical-closure-antenna-failure-local-v1.json) closes all nine timing/electrical views for that selected RTL at the same 100 ns clock: worst setup slack is 90.486104 ns, hold slack 0.220976 ns, capacitance margin 17.790118% and slew margin 15.587124%. Cell area is 85,926.164062 square micrometres after physical repair. Both complete equivalence stages, Magic/KLayout DRC and transistor LVS/ERC pass. Magic antenna fails with 276 findings, and small-block density remains unknown. These later physical-repair results are distinct from the same-flow RTL comparison above and do not establish signoff approval. The [fresh routed switching characterization](../qualification/evidence/PHYS-01/aes-lookup-routed-switching-characterization-local-v1.json) passes all three original AES known answers and independently replays all nine OpenROAD/OpenSTA views with 100% annotation coverage, unchanged constraints and unchanged timing metrics. Maximum estimated power is 1.784372 mW under those vectors; this is not an approved mission workload or glitch-aware power signoff. The [complete antenna diagnosis](../qualification/evidence/PHYS-01/aes-lookup-exact-antenna-pin-diagnosis-local-v1.json) reproduces all 276 feedback entries and resolves all 18 electrical error records to 12 exact input pins. One debug cell label identifies another cell on the same node; unique physical gate location and native input aliases resolve that discrepancy. These are diagnosis results, not accepted repair or signoff. The [12-pin native repair trial](../qualification/evidence/PHYS-01/aes-lookup-twelve-pin-antenna-repair-failure-local-v1.json) inserts exact-input buf6 cells and reroutes the complete design. All nine timing/electrical views pass (setup 90.561947 ns, hold 0.220846 ns), both complete equivalence stages pass, both DRC tools report zero findings, and transistor LVS/ERC pass. Independent Magic antenna findings fall from 276 to 92 but still fail. Density remains unknown for this small block; the trial is retained as incomplete and is not signoff approved. Its [fresh exact-netlist switching characterization](../qualification/evidence/PHYS-01/aes-lookup-twelve-pin-switching-characterization-local-v1.json) passes all three known answers and replays all nine OpenROAD/OpenSTA views with 100% annotation coverage, unchanged constraints and unchanged timing/electrical metrics. Maximum estimated power is 1.787070 mW under these vectors; mission activity and glitch-aware power signoff remain unapproved. The [remaining antenna diagnosis](../qualification/evidence/PHYS-01/aes-lookup-remaining-four-pin-diagnosis-local-v1.json) reproduces all 92 findings and resolves all four electrical records to four exact input pins, disjoint from the previous 12 repaired pins. An existing diode on key[88] does not establish stage protection. No further repair acceptance is implied by the diagnosis. The [16-pin cumulative repair trial](../qualification/evidence/PHYS-01/aes-lookup-sixteen-pin-antenna-repair-failure-local-v1.json) retains those 12 buffers, adds four more exact-pin buf6 cells and performs a complete reroute. All nine timing/electrical views and both full equivalence stages pass; both DRC tools report zero findings and transistor LVS/ERC pass. Setup slack is 90.612460 ns and hold slack 0.221110 ns. Magic antenna findings fall from 92 to 82 but still fail, with density/integration and engineering approval gaps unchanged. Its [fresh exact-netlist activity replay](../qualification/evidence/PHYS-01/aes-lookup-sixteen-pin-switching-characterization-local-v1.json) passes all three known answers and all nine timing views with 100% annotation coverage and unchanged timing/constraints. Maximum estimated power is 1.785459 mW under those vectors; mission activity and power signoff remain unapproved. The [subsequent three-pin diagnosis](../qualification/evidence/PHYS-01/aes-lookup-remaining-three-pin-diagnosis-local-v1.json) reproduces all 82 findings and resolves all five gate/layer records to three distinct native input pins, disjoint from the prior 16 repaired inputs. This establishes repair targets only; it does not approve a further trial. The [19-pin cumulative repair trial](../qualification/evidence/PHYS-01/aes-lookup-nineteen-pin-antenna-repair-failure-local-v1.json) retains the previous 16 buffers, adds three exact-pin buf6 cells and reroutes the complete design. All nine timing/electrical views, both complete equivalence stages, both DRC checks and transistor LVS/ERC pass; setup slack is 90.367067 ns and hold slack 0.221571 ns. Magic antenna findings fall from 82 to 21 but still fail. Density/integration and independent engineering approval gaps remain unresolved. The [fresh exact-netlist activity characterization](../qualification/evidence/PHYS-01/aes-lookup-nineteen-pin-switching-characterization-local-v1.json) passes all three known answers and independently replays all nine timing views with 100% annotation coverage and unchanged constraints/timing. Maximum estimated power is 1.787589 mW under those vectors; it does not establish approved mission activity or power signoff. The [21-finding antenna diagnosis](../qualification/evidence/PHYS-01/aes-lookup-last-three-pin-diagnosis-local-v1.json) reproduces every finding and resolves all three gate/layer records to three exact native input pins, disjoint from the previous 19 repaired pins. This diagnoses the remaining targets for that layout and grants no further repair acceptance. The [22-pin cumulative repair trial](../qualification/evidence/PHYS-01/aes-lookup-twenty-two-pin-antenna-repair-failure-local-v1.json) passes all nine timing/electrical views and both complete equivalence stages, both DRC tools and transistor LVS/ERC, but Magic antenna findings increase from 21 to 36. It is retained as a failed antenna trial, not closure; its layout is the subject of a fresh exact-pin diagnosis.

The [retained AES preparation](../qualification/evidence/PHYS-01/aes-prepared-local-v1.json)
passes all three vectors and maps 9,862 SKY130 instances under the 4096 MiB limit.
The [initial ports-only proof](../qualification/evidence/PHYS-01/aes-initial-equivalence-local-v1.json)
left 129 output obligations unproven at depth eight, blocking the optimization loop
before any provider call. This is not a functional counterexample or a completed
formal qualification. The subsequent
[complete transition check](../qualification/evidence/PHYS-01/aes-transition-controls-local-v1.json)
proves all 129 primary-output bits and all 530 retained next-state bits after native
synthesis normalization, with a complete state bijection and checked clock
connections/polarity. A wrong ciphertext update reaches a failed SAT assertion.
The method is integrated into RTL optimization and release checks; unsupported
state correspondence retains the clock-event engine. A failed transition proof
never invokes that fallback. [Mapped-netlist simulation](../qualification/evidence/PHYS-01/aes-mapped-vectors-local-v1.json)
also passes all three known-answer vectors using Liberty-derived cell models.

Current AES preparation retains the upstream SKY130 configuration and routing
script and uses their 35% floorplan utilization and 0.3 routing-capacity adjustment.
The [shared preparation check](../qualification/evidence/PHYS-01/benchmark-strategy-validation-local-v1.json)
keeps fresh AES and matrix draft requirements consistent with that utilization;
older drafts incorrectly retained the factory's 50% description. Timing constraints
are unchanged, and signed requirements cannot be rewritten by preparation.
The [earlier physical experiments](../qualification/evidence/PHYS-01/aes-superseded-strategies-local-v1.json)
were explicitly canceled as superseded; they are not completed physical checks.
The [completed AES baseline](../qualification/evidence/PHYS-01/aes-native-baseline-local-v1.json)
passes source/final equivalence and transistor LVS. All nine independent timing
views ran, with setup WNS +87.416 ns against the original provisional 100 ns
clock, but hold WNS −0.072151 ns and electrical violations keep timing open.
KLayout reports 276 violations (269 metal-3 minimum-area and seven nitride-spacing);
Magic reports 1,121 DRC and 702 antenna violations. Router-local DRC zero therefore
does not establish physical signoff. AES closure, measured RTL improvement, and
matrix-accelerator qualification remain unfinished.
The [batched layout exporter](../qualification/evidence/PHYS-01/aes-batched-export-local-v1.json)
materializes the routed vias in one layout update batch. A native geometric XOR
against the pre-flatten import is empty on all 40 layers; this preserves export
geometry and does not clear the existing DRC findings.
The [current-fixture release regression](../qualification/evidence/PHYS-01/rtl-release-transition-local-v1.json)
passes native timing, both equivalence checks, Magic/KLayout DRC, LVS, antenna,
connectivity, and grid execution with the integrated transition checker. This is
a small mux handoff using a test-double proposal, not AES physical qualification.
The [updated AES proof](../qualification/evidence/PHYS-01/aes-normalized-transition-local-v1.json)
also passes all 129 output and 530 next-state obligations after the additional
enabled-register normalization, under the same 4096 MiB native cap.
The [legacy-template attempt](../qualification/evidence/PHYS-01/rtl-release-legacy-template-local-v1.json)
retains the known DRC failures from the older CTS/floating-fill strategy.

New SKY130 flows exclude probe and multi-power cells from native repair and CTS,
matching the pinned upstream policy. A
[native policy check](../qualification/evidence/PHYS-01/sky130-cell-exclusions-local-v1.json)
confirms all 36 excluded cells after linking. This does not remove such cells
from an existing mapped netlist. The
[repair experiments](../qualification/evidence/PHYS-01/aes-mcmm-repair-failures-local-v1.json)
retain two actual failures: uninitialized named-corner layer RC, then invalid
probe-cell pin access after correcting RC. The [subsequent reporting diagnostics](../qualification/evidence/PHYS-01/aes-mcmm-reporting-diagnostics-local-v1.json)
reach completed AES routing with zero router DRC and 11 antenna violations, then
fail multi-scene power reporting. Their three PVT views with nominal RC show
positive timing/electrical margins; this is not complete nine-view closure.

The shared driver now exports routed checkpoints before reports and explicitly
selects the primary power scene. V2 analysis accepts the exact declared PVT count,
retains the aggregate implementation metrics, and checks standalone primary STA
against the matching typical scenario after the complete nine-view replay.
The default single-view guard remains intact. The
[native multi-corner regression](../qualification/evidence/PHYS-01/multiscene-driver-local-v1.json)
passes timing, both equivalence checks, both DRC tools, LVS, antenna, ERC and grid
execution. Activity coverage fails; engineering readiness and signoff remain false.
An [injected report failure](../qualification/evidence/PHYS-01/multiscene-report-failure-local-v1.json)
retains ODB, DEF, Verilog and SDC checkpoints without emitting analysis completion.

A fresh full AES run adds at most three post-route antenna repair/reroute passes
and a separate pre-repair checkpoint. The original timing constraints and PDK
files remain unchanged. The [metal-area diagnosis](../qualification/evidence/PHYS-01/aes-metal-area-diagnosis-local-v1.json)
confirms two sampled metal-3 errors exist in OpenDB and are exported unchanged:
0.1905 square micrometres against the original 0.24 minimum. It does not establish
the cause or resolution of all 269 findings.
A [controlled full-route extraction experiment](../qualification/evidence/PHYS-01/rcx-route-preservation-local-v1.json)
subsequently identifies a reproducible implementation failure: inline OpenRCX
removes all 861 routed RECT repair patches and introduces 346 metal-3 minimum-area
violations in the unchanged full AES layout. Running extraction in a disposable
child database preserves all 861 patches and produces a byte-identical parent
DEF. Both exports use the original PDK minimum-area rule. An
[already-extracted two-patch control](../qualification/evidence/PHYS-01/rcx-ordered-patch-control-local-v1.json)
does not reproduce the loss; that limited counter-control is retained alongside
the full-route evidence. The integrated workflow isolates extraction rather than
changing layout rules. The [older AES qualifications](../qualification/evidence/PHYS-01/aes-mcmm-supersession-local-v1.json)
were explicitly superseded after the full06 replacement passed both equivalence
proofs, all nine timing views, router antenna checks and KLayout DRC under the
same source, constraints, PDK assets and tools. Their interrupted Magic checks
remain unproven. Full06 continues using its unchanged isolated workflow.

The [native resource controls](../qualification/evidence/PHYS-01/openroad-resource-controls-local-v1.json)
verify the OpenROAD launcher's actual 4 GiB address-space ceiling and
preservation of a stricter inherited 2 GiB limit. Earlier physical runs were not
all capped; synthesis and equivalence limits do not imply a physical-run limit.
The [software validation](../qualification/evidence/PHYS-01/mcmm-software-validation-local-v1.json)
retains 285 passing tests, repository checks, local artifact verification, and a
passing coverage ratchet. These checks do not establish physical sign-off.
The [candidate default-flow qualification](../qualification/evidence/PHYS-01/factory-mcmm-complete-local-v1.json)
also completes the native qualifier: multi-corner repair changes the small
regression's worst hold slack from −0.039059 ns to +0.220102 ns without changing
its timing constraints. Nine-view timing, both equivalence checks, Magic/KLayout
DRC, antenna, LVS, ERC and memory mutation controls pass. The candidate shares
inherited address-space handling across synthesis, mapping and both proof paths,
so a requested 6 GiB ceiling respects a parent's 4 GiB limit. Its
[preceding attempt](../qualification/evidence/PHYS-01/factory-mcmm-layout-local-v1.json)
retains the actual failed limit-setting control. The repair, extraction isolation
and inherited-limit changes are now integrated; repository checks are repeated
against the integrated sources. Unknown workload, density, power and
approved-requirement gates still prevent sign-off.
The [integrated workflow validation](../qualification/evidence/PHYS-01/integrated-workflow-validation-local-v1.json)
retains the before/after sources, 288 passing tests, repository checks and an
actual passing coverage ratchet for the integrated code. Larger AES and matrix
qualification remain separate requirements.
The [Magic extraction preservation control](../qualification/evidence/PHYS-01/magic-capacitance-preservation-local-v1.json)
uses the same complete retained AES GDS: disabling parasitic capacitance and
coupling extraction produces byte-identical LVS SPICE and full DRC details and
preserves all 702 antenna findings in a complete saved-extraction replay. The
[initial timed-out attempt](../qualification/evidence/PHYS-01/magic-capacitance-diagnostics-local-v1.json)
remains incomplete rather than being relabeled as passed. Magic now suppresses
only those unused capacitances; full geometry checks, transistor extraction and
antenna checking remain enabled. Timing still uses independent OpenRCX SPEFs.
The [completed full AES08 run](../qualification/evidence/PHYS-01/aes-native-verification-local-v1.json)
passes both DRC tools, both equivalence proofs and all nine timing views, but
Magic finds 143 antenna violations despite OpenROAD reporting zero. Its LVS gate
also rejects an unresolved diode primitive. The
[resolved-diode controls and integrated API replay](../qualification/evidence/PHYS-01/aes-diode-lvs-controls-local-v1.json)
pass full transistor LVS without black boxes and reject reversed, incorrectly
sized and shorted diode junctions. The parser now rejects subcell property errors
even when Netgen prints a unique top-level match. The
[complete antenna feedback](../qualification/evidence/PHYS-01/aes-magic-antenna-feedback-local-v1.json)
retains all 143 findings; none is filtered or waived. Antenna closure remains open.
The [18-diode trial](../qualification/evidence/PHYS-01/aes-diode-only-repair-failure-local-v1.json)
preserves every inserted junction but produces byte-identical antenna feedback.
The pinned Magic technology file explicitly does not model diode-diffusion credit.
No deck or threshold is changed; the subsequent trial uses native routing jumpers.
The [targeted buffer/full-reroute trial](../qualification/evidence/PHYS-01/aes-full-reset-buffer-antenna-failure-local-v1.json) inserts 18 inline buffers without changing the source, original placements, constraints or rule limits. It passes all nine timing views, both complete equivalence stages, both full-layout DRC tools, transistor LVS and ERC. Magic antenna findings rise to 184 from 143, so this repair is rejected despite zero native router antenna findings. Draft requirements, activity, density and power-integrity gates remain unknown.
The [exact-pin antenna diagnosis](../qualification/evidence/PHYS-01/aes-exact-antenna-pin-diagnosis-local-v1.json) replays the retained GDS and extraction with pinned Magic debug mode and reproduces byte-identical 184-finding feedback. Physical poly-node queries and OpenDB correlation resolve all ten gate/plane errors to seven exact input pins, rather than every input of the affected cells. Two existing diodes are connected to the failing text_in[12] node across the completed layout; this does not establish process-stage protection. The [seven additional exact-pin buffer repair](../qualification/evidence/PHYS-01/aes-exact-pin-antenna-closure-local-v1.json) now passes all nine timing/electrical views, both full equivalence stages, both DRC tools, transistor LVS/ERC and zero Magic antenna findings. An initial missing KLayout PATH was corrected by replaying release checks against byte-identical completed DB/netlist outputs without rerouting. This validates the original upstream AES plus physical repair, not the separate reordered-RTL circuit. Requirements, workload, power integrity and small-block density/integration remain unapproved or unknown. Its documented locality bound is 55 micrometres after legal-slot planning found a 52.49 micrometre maximum; the earlier 50 micrometre cutoff was a preparation heuristic, not a PDK, SDC or signoff rule. All native acceptance gates remain unchanged.

A [diode-load control](../qualification/evidence/PHYS-01/antenna-diode-equivalence-local-v1.json)
proves that the real SKY130 input-only antenna diode is handled through its
Liberty model without removing it by cell name.

### OpenROAD matrix tile

The pinned OpenROAD/LogikBench `tpu` benchmark uses the upstream defaults: an
8×8 weight-stationary array, signed INT8 operands, and INT32 output lanes. It is a
matrix tile without CPU, SRAM-macro, or software-stack dependencies. The original
MIT license and source provenance are retained under `qualification/fixtures/tpu/`.

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.tpu --output .dv-platform/tpu-new
```

The [retained preparation](../qualification/evidence/PHYS-01/tpu-prepared-local-v1.json)
checks four complete tiles against integer matrix multiplication, including
signed extremes, identity/zero weights, input bubbles, and valid timing. All
256 scalar results pass. SKY130 mapping completes under the 4096 MiB native
limit with 42,367 mapped cells. The
[mapped-netlist simulation](../qualification/evidence/PHYS-01/tpu-mapped-vectors-local-v1.json)
also passes all 256 results with Liberty-derived functional cell models.

The [initial formal preparation](../qualification/evidence/PHYS-01/tpu-model-bound-local-v1.json)
compiled both models but stopped before proof because the mapped JSON is larger
than the checker's former 64 MiB parsing bound. The parser now permits 128 MiB;
native execution retains its 4096 MiB cap. Additional native normalization merges
redundant enabled sign registers before checking the complete state bijection.
The [complete matrix transition proof](../qualification/evidence/PHYS-01/tpu-complete-transition-proof-local-v1.json)
passes all 257 primary-output and 4,015 next-state comparisons on the original
8×8 design. All 4,272 obligations are reconstructed from the native graphs;
every one of the 1,043 unique miters has a verified native SAT receipt, and the
first/middle/last inverted-output controls reject. The retained
[Boolean-model audit](../qualification/evidence/PHYS-01/tpu-boolean-model-audit-local-v1.json)
checks every connected gate for defined scalar Boolean semantics, single drivers,
and acyclic driven logic. Pinned native Yosys regenerates byte-identical AIG inputs
with all 4,147 shared inputs and 4,272 comparisons. This audit does not itself prove
equivalence. The
[complete-proof diagnostics](../qualification/evidence/PHYS-01/tpu-complete-proof-diagnostics-local-v1.json)
include the SAT and ABC CEC timeouts. The
[GIA controls](../qualification/evidence/PHYS-01/tpu-gia-controls-local-v1.json)
accept self and reject first/middle/last output inversions, but full GIA CEC ends
undecided. The [exact-cone preparation](../qualification/evidence/PHYS-01/tpu-cone-preparation-local-v1.json)
retains all 4,272 comparisons as 1,043 unique Boolean miters, with a complete
output-to-cone map. The largest cone passes native SAT. The original four-worker
pool was explicitly superseded after validating 135 completed proofs for reuse.
A twelve-worker direct-SAT pool added further proofs but encountered many
180-second proof timeouts. The [validated normalization handoff](../qualification/evidence/PHYS-01/tpu-normalization-handoff-local-v1.json)
retains that terminal pool, completed proofs, canceled partial work and rejecting
first/middle/last controls. It was explicitly superseded after a stronger method
proved a timed-out cone; observation expiry did not trigger cancellation.
The [retention correction](../qualification/evidence/PHYS-01/tpu-handoff-retention-correction-local-v1.json)
preserves late output from eight interrupted jobs separately and restores the
exact original hash-bound log prefixes. None has a completed native result or
receipt, and none is reused as a successful proof.
The completed pool reused complete proofs and normalized every unfinished cone
with an explicitly pinned ABC executable before SAT. Six workers account for
both Yosys and its ABC child, plus a 1 GiB coordinator, within a 4 GiB aggregate
ceiling. The
[native normalization control](../qualification/evidence/PHYS-01/tpu-abc-controls-local-v1.json)
proves one previously timed-out cone and rejects its inverted output through an
actual failed SAT assertion. This control is not a complete matrix proof.
A separate [state-cut reconstruction](../qualification/evidence/PHYS-01/tpu-clock-state-reconstruction-local-v1.json)
reproduces the exact proof input from the uncut native models, checking all 4,015
state pairs, 257 outputs and the rising-edge primary clock. No comparisons or tile
dimensions are dropped. Partial successes, sampled simulation and timeouts are not accepted
as full equivalence, and the diagnostic proof cache is not integrated into release
approval.
The [integrated cone backend](../qualification/evidence/PHYS-01/scalable-proof-integration-local-v1.json)
now runs through the production equivalence API and release-check callers. It
rebuilds native Boolean graphs and every comparison from the current inputs;
it does not import the diagnostic certificate or external proof cache. The
software checks pass 311 tests, including native arithmetic/output/clock/reset
mutations, undef-aware fallback and artifact tampering. A frozen full-matrix
preflight exposes all 4,272 comparisons and passes the Boolean audit. A fresh
[complete production-API proof](../qualification/evidence/PHYS-01/tpu-production-complete-proof-local-v1.json) has passed all 4,272 comparisons through 642 unique native SAT miters. Its audit reconstructs every state cut and comparison and verifies all artifact hashes and native receipts; it uses the production Boolean builder and is not a second independent Boolean implementation or SAT replay.
Routed physical qualification and measured RTL improvement remain unfinished;
simulation or mapping alone does not establish them.
The [full matrix physical baseline](../qualification/evidence/PHYS-01/tpu-native-physical-baseline-local-v1.json)
completes routing and all nine independent views under the 4 GiB native limit.
Setup WNS is +78.4736 ns and hold +0.106351 ns; router DRC and antenna counts are
zero. Slow-corner slew fails by 15.3915%, so timing closure remains open despite
positive setup and hold. Final layout verification is still required.

The [repaired full matrix](../qualification/evidence/PHYS-01/tpu-native-timing-closure-local-v1.json)
passes every original timing/electrical gate in all nine views at the unchanged
exploratory 100 ns clock. Worst setup slack is +78.446995 ns, hold +0.173970 ns,
slew margin +27.0834%, and capacitance margin +36.9803%; native router DRC and
antenna counts are zero. Clearing stale signal routes before placement-based
repair and full rerouting resolved the routing-tree/pin-access failures. The [full native release-check qualification](../qualification/evidence/PHYS-01/tpu-full-native-qualification-unapproved-local-v1.json) completes both equivalence stages, both DRC tools, transistor LVS/ERC and 100% activity coverage. Magic antenna fails with 36 findings. Its original density-pass conclusion is invalid: the native log contains 259 mixed-case Error labels that the old uppercase-only parser missed.
The [density-parser correction and fresh native replay](../qualification/evidence/PHYS-01/density-case-parser-validation-local-v1.json) reproduce identical findings on the exact GDS and correctly mark density failed. All 318 tests, coverage and repository checks pass with compatibility unchanged. The old unapproved release is retained without altering its bytes. A [historical impact audit](../qualification/evidence/PHYS-01/density-historical-report-audit-local-v1.json) inspects 20 retained release bundles and 19 bound density logs; the single completed report is this invalidated matrix density conclusion, with no approval documents present. Timing closure does not approve the boundary assumptions, power budgets or failed layout gates. The [exact two-pin matmul antenna repair](../qualification/evidence/PHYS-01/tpu-exact-pin-antenna-closure-local-v1.json) subsequently completes fresh source and routed proofs covering all 257 outputs and 4,015 next-state bits, with 642 fresh source miters and no external proof cache. All nine timing/electrical views pass; both DRC tools, independent Magic antenna (zero findings), transistor LVS and ERC pass. The corrected density check still fails with all 259 findings, and engineering readiness and signoff remain false. The earlier activity trace is not reused after this circuit change. The [fresh exact-routed switching validation](../qualification/evidence/PHYS-01/tpu-exact-pin-routed-switching-characterization-local-v1.json) passes all four original matrix tiles and 256 scalar results, then independently replays all nine timing views with 100% annotation coverage and unchanged constraints/timing. Maximum estimated power is 4.698523 mW under those vectors, without mission-workload approval or glitch-aware power signoff.

[Routed-netlist switching capture](../qualification/evidence/PHYS-01/routed-benchmark-known-vectors-local-v1.json)
passes all three AES known answers and all 256 matrix results on the actual
routed logical circuits, including the repaired matrix. Liberty-derived cell
models retain every functional cell; only disconnected physical cells are
removed. Derived testbenches use named ports and a uniformly scaled timescale
to exercise the original vectors at the 100 ns characterization clock.
The [activity replay](../qualification/evidence/PHYS-01/routed-benchmark-activity-replay-local-v1.json)
on the completed AES and initial matrix baselines reaches 100% activity
annotation in every one of their nine independent OpenROAD/OpenSTA views.
Clocks, resolved constraints and timing metrics remain unchanged. Worst
estimated power under these known-answer vectors is 1.821349 mW for AES and
4.697330 mW for the matrix. These traces cover benchmark tests and do not
establish an approved mission workload, IR/EM closure or manufacturing approval.

The RTL loop has a separate registered-multiplexer qualification with a labeled proposal test
double and real Yosys, OpenROAD, and standalone OpenSTA execution:

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.rtl --template .dv-platform/sky130/fixture-v2/project/project.json --output .dv-platform/rtl-native-new
```

Use a fresh output directory. Qualification requires native mapping and final-netlist proofs
for the baseline and valid candidate, and rejects an incorrect-output RTL mutation. A valid
candidate may still fail to improve physical metrics; qualification distinguishes completed
measurement from optimization success. It does not establish live-model execution or production
approval. Portable tests separately require rejection of smaller-area timing regressions and
retain unsuccessful trials for the next model decision.

The retained [RTL mux run](../qualification/evidence/PHYS-01/rtl-mux-local-v1.json) completed
source, mapping, and final-netlist equivalence with nine native timing views. Worst setup slack
increased from 96.11213869 ns to 96.12212182 ns under the same exploratory 100 ns clock;
area remained 633.107239 square micrometres and no requirement gap grew. The incorrect-output
mutation was rejected. Its 802 retained artifacts are checked by `make verify-evidence`.
The proposal came from the explicit test double, and the block remains unapproved for production.

The separate [live Luna RTL run](../qualification/evidence/PHYS-01/rtl-luna-local-v1.json)
records two accepted provider responses and two candidates that completed native source,
mapping, and final-netlist proofs plus nine-view physical replay. The first candidate increased
worst setup slack by 0.00998313 ns with unchanged area; the second did not beat it and was
rejected. Its 1,090 retained artifacts include provider receipts and the frozen workflow.
It remains a mux qualification under exploratory constraints, not a CPU or manufacturing approval.

The [selected RTL release handoff](../qualification/evidence/PHYS-01/rtl-release-local-v1.json)
uses a fresh factory-generated SKY130 project and a labeled proposal test double. Its selected
candidate passed native timing, source/final equivalence, Magic and KLayout DRC, Netgen LVS,
antenna, connectivity, and power-grid execution. The 1,387 retained artifacts bind the original
RTL reference, selected source, decision receipt, physical project, and release reports.
Activity, density, approved requirements, and IR/EM limits remain unknown; engineering readiness
and production approval are false. Reproduce the handoff with a fresh output directory:

```bash
rtk proxy .dv-platform/sky130/tools/run uv run python -m scripts.qualification.rtl_release --template /path/to/physical-project.json --output .dv-platform/rtl-release-new
```

The [installed-wheel Luna run](../qualification/evidence/PHYS-01/rtl-installed-luna-local-v1.json)
also completed `dv-enterprise rtl-optimize` with a real provider call and native nine-view replay.
It returned exit zero with an improved, proven candidate. The retained wheels, pinned dependency
list, installed import origins, CLI result, and native artifacts establish execution from the
installed public and private distributions rather than the editable checkout.

To qualify the configured provider against an existing RTL project, use a fresh output directory:

```bash
rtk proxy .dv-platform/sky130/tools/run uv run --env-file .env python -m scripts.qualification.rtl_live --config dv-platform.toml --project /path/to/rtl-project.json --output .dv-platform/rtl-live-new --allow-network --max-iterations 2
```

This explicit qualification command enables only the `rtl_optimization` purpose for the run,
uses a short-lived repository test entitlement, and preserves the configured provider routing
policy. It fails unless a real provider response produces a candidate with completed native
measurement and equivalence. It does not issue production licenses or approvals.

For the pinned SKY130 CPU and nine-view workflow, follow [SKY130 sign-off and qualification](sky130-signoff.md). Portable tests also cover v2 schemas, independent approval roles, report-specific waivers, expiry/revocation/tampering, native tool protocols, power-source validation, and lossless timing-context factoring. The manual native CI job exercises the provisioned tools; ordinary PR CI runs the portable suite.

The pinned fixture uses OpenROAD `26Q2-1164-g08f67ee5ec` and fifteen source assets from the revision in [the fixture policy](../qualification/policies/openroad-fixture-v1.json). Preserve `.dv-platform/openroad-live/fixture/`; outputs below must be new directories.

```bash
uv run python -m scripts.qualification.openroad_agentic --fixture .dv-platform/openroad-live/fixture --output .dv-platform/native-check
uv run --env-file .env python -m scripts.qualification.openroad_agentic --fixture .dv-platform/openroad-live/fixture --output .dv-platform/live-check --live-ai
```

The first command uses a measurement-driven test double with real native tools. The second uses the configured AI provider and operator-authored [closure flow](../qualification/fixtures/openroad/gcd_closure.tcl). Qualification creates a temporary test entitlement and does not issue production licenses.

The live path verifies native routing, the original clock, immutable constraints, independent OpenSTA, and model execution. On timing closure it also runs a separate Yosys equivalence check and signed physical-evidence import. Equivalence covers every output and register D cone for all shared input/state assignments, validates register correspondence and clock polarity, and must reject a bad-output mutation.

## Retained local evidence

The [CPU decoder qualification](../qualification/evidence/PHYS-01/cpu-decoder-luna-local-v1.json)
uses the existing CPU package, decoder, and design document. Native `sv2v` conversion and
equivalence accepted a sign-extension rewrite and rejected a wrong-sign mutation. A separate
live Luna proposal completed conversion, source/mapping/final-netlist proofs, and all nine
SKY130 timing views through a registered decoder wrapper. Area rose from 4007.59 to 4041.38
square micrometres, so the area objective kept the original RTL. Hold timing remains open;
this establishes package-based execution and measured rejection, not full CPU closure.

The frontend/source proof is independently reproducible with a fresh output directory:

```bash
rtk proxy uv run python -m scripts.qualification.cpu_rtl --cpu-root ../cpu --converter .dv-platform/sky130/cpu-first/source/build/tools/sv2v --output .dv-platform/cpu-decoder-frontend-new
```

The [full-CPU mapping resource failure](../qualification/evidence/PHYS-01/cpu-map-memory-local-v1.json)
retains the 8 GiB SAT-sharing failure, its exact input RTLIL/library, and native logs. That
failed experiment does not establish mapped CPU execution. The revised staged CPU preparation
omits optional SAT sharing and verifies reusable mapping checkpoints independently.
The independently archived [coarse CPU checkpoint](../qualification/evidence/PHYS-01/cpu-coarse-local-v1.json)
completed that stage under the same 8 GiB budget. It preserves the source RTLIL, output checkpoint,
driver, tool/library identities, and receipts outside the running workspace. It does not establish
fine mapping, functional equivalence, physical implementation, or production approval.
The later [gate-expansion resource failure](../qualification/evidence/PHYS-01/cpu-fine-memory-local-v1.json)
retains the native `std::bad_alloc` failure under 8 GiB. Preparation now checkpoints memory
lowering separately before gate expansion; a resumed run is not evidence of completion until
its native processes finish and its outputs verify.
The [memory-lowering checkpoint](../qualification/evidence/PHYS-01/cpu-memory-checkpoint-local-v1.json)
subsequently completed under 10 GiB. Its archived input/output RTLIL, script, tool/library,
driver, and receipt hashes verify independently of the active workspace. Gate expansion,
technology mapping, and full CPU functional and physical qualification remain outstanding.
The [hierarchical generic-gate checkpoint](../qualification/evidence/PHYS-01/cpu-generic-checkpoint-local-v1.json)
then completed gate expansion using `techmap -extern`, retaining shared implementations rather
than inlining them. Its native structural checks passed, but subsequent library validation
found 582 coarse cells inside generated modules; this first-pass checkpoint is not a fully
lowered gate netlist. The earlier
[10 GiB inline expansion failure](../qualification/evidence/PHYS-01/cpu-fine-memory-10g-local-v1.json)
remains retained as a failed experiment. Generic gates are not SKY130 cells: library mapping,
functional equivalence, physical closure, and approval are still required.
The [completed generic expansion](../qualification/evidence/PHYS-01/cpu-generic-complete-local-v1.json)
adds a second expansion pass inside the shared modules and passes a strict no-coarse-cell
assertion. This resolves the first-pass limitation while preserving hierarchy; it still does
not establish SKY130 library mapping or functional equivalence.
The [full CPU SKY130 mapping](../qualification/evidence/PHYS-01/cpu-mapped-local-v1.json)
subsequently completed all synthesis stages and final library mapping under 10 GiB, including
the strict mapped-cell check. Its 194 retained artifacts include every checkpoint, the original
reference netlist, mapped Verilog/JSON, source inputs, native receipts, tool/driver identities,
and the self-contained physical project. This establishes full-core mapping, not equivalence,
physical closure, or approval; those remain separate gates.
The [mapped hierarchy size estimate](../qualification/evidence/PHYS-01/cpu-mapped-size-local-v1.json)
counts 21,575,002 standard-cell instances and 180.747 square millimetres of library cell area.
It streams the mapped JSON into per-module instance counts, then runs native Yosys statistics
on a count-only hierarchy with every connection omitted. Native leaf counts match an independent
recursive count exactly. This characterizes the unplaced hierarchy; it does not measure final
routed area, timing, power, or functional correctness. Generated selection logic and ROB logic
dominate the count and warrant investigation before claiming practical full-core closure.
The [initial full CPU equivalence attempt](../qualification/evidence/PHYS-01/cpu-equivalence-memory-local-v1.json)
exhausted 10 GiB during flattened clock-model optimization and proves no equivalence result.
The [native clock-model controls](../qualification/evidence/PHYS-01/equivalence-hierarchy-controls-local-v1.json)
pass after moving clock-event lowering and optimization before flattening. Both positive proofs
pass and all five mutations reach a failed equivalence assertion. A resource error is explicitly
rejected as control evidence. Full CPU equivalence remains a separate, unfinished requirement.
The [helper-compaction control](../qualification/evidence/PHYS-01/helper-compaction-controls-local-v1.json)
proves a compacted 512-input selector equivalent with generic cells reduced from 16,896 to 1,024,
and rejects an inverted-output mutation. This motivates optimizing generated helper definitions
before full-core implementation, but does not establish a compacted CPU or CPU equivalence.
The [full CPU generic compaction](../qualification/evidence/PHYS-01/cpu-helper-compacted-local-v1.json)
subsequently passed structural checks under 8 GiB and reduced generic cells from 20,174,669
to 12,395,094. This result concerns the generic hierarchy; mapped area, complete CPU equivalence,
and physical verification remain separate requirements.
The [compacted SKY130 mapping](../qualification/evidence/PHYS-01/cpu-compacted-mapped-local-v1.json)
then completed with 11,441,818 mapped instances and 79.722 square millimetres of native library
area, 55.9% below the original unplaced hierarchy. Routed timing, power, and full CPU equivalence
are not established by those statistics.
The [state-name control](../qualification/evidence/PHYS-01/equivalence-state-names-local-v1.json)
proves a counter with preserved state names; hiding them leaves the same bounded proof unproven.
CPU preparation now preserves those names, with a separately retained
[named coarse checkpoint](../qualification/evidence/PHYS-01/cpu-named-coarse-local-v1.json).
The [named memory checkpoint](../qualification/evidence/PHYS-01/cpu-named-memory-local-v1.json)
also completed with verified input/output hashes; complete mapping and CPU equivalence remain required.
The [complete named-state mapping](../qualification/evidence/PHYS-01/cpu-named-mapped-local-v1.json)
retains the same 11,441,818 instances and 79.722 square millimetres of library area, with state
names preserved. The [source-model resource failure](../qualification/evidence/PHYS-01/cpu-source-model-memory-local-v1.json)
then exhausted 10 GiB during structural checking and produced no equivalence result.
Model compilation and structural checking now run in separate processes; the
[native fixture regression](../qualification/evidence/PHYS-01/rtl-release-model-validation-local-v1.json)
passes using this separation. Full CPU proof and physical characterization remain unfinished.
The [verified-model release regression](../qualification/evidence/PHYS-01/rtl-release-verified-models-local-v1.json)
passes native source/final equivalence, nine-view timing, both DRC tools, LVS, antenna,
connectivity, and grid execution on the small fixture using the staged proof engine.
Prepared-model hashes are checked before use and after proof. Workload, density, approved
requirements, IR/EM limits, and production approval remain incomplete.

- [Luna feedback loop](../qualification/evidence/PHYS-01/openroad-luna-feedback-local-v1.json): three real model-guided experiments; regressions rejected with timing left open.
- [Luna timing closure](../qualification/evidence/PHYS-01/openroad-luna-closed-local-v1.json): original 0.485 ns clock, setup WNS +0.00492556 ns, TNS zero, hold WNS +0.080093 ns, zero routing DRC and antenna violations; independent STA and external equivalence passed.

The manifests bind the retained artifacts by SHA-256. They are local execution evidence, not a release approval. Qualification uses a single Nangate45 typical view and operator-authored physical strategy. Full MCMM, independent foundry sign-off, and automatic equivalence inside product runs remain outside this evidence.

The [matmul decap density preview](../qualification/evidence/PHYS-01/tpu-decap-density-preview-local-v1.json) replaces 46,338 same-footprint filler cells in a separate geometry experiment. Native Magic density findings decrease from 259 to 185: diffusion and local-interconnect findings clear, while MET1–MET5 each retain 37 minimum-density findings. Whole-chip FOM is 36.4704% and LI is 57.7069%. This preview has no timing, equivalence, DRC, LVS, antenna or power qualification and is not approved for integration. Connected metal density repair remains necessary.

The [22-buffer AES activity replay](../qualification/evidence/PHYS-01/aes-lookup-twenty-two-pin-switching-characterization-local-v1.json) passes all three known answers and all nine timing views with 100% annotation coverage and unchanged timing/constraints; maximum estimated power is 1.788231 mW under those vectors. The [complete 36-finding diagnosis](../qualification/evidence/PHYS-01/aes-lookup-two-nand-pin-diagnosis-local-v1.json) resolves all three gate/layer records to two exact NAND inputs, disjoint from the previous 22 targets. Two additional buf6 cells are undergoing fresh native qualification; no acceptance is implied.

The [decap preview KLayout and area checks](../qualification/evidence/PHYS-01/tpu-decap-klayout-area-validation-local-v1.json) pass the complete pinned KLayout deck, including floating-metal checks, with zero findings. The production native `rsz::design_area` metric is unchanged at 386,479.4375 square micrometres. These completed checks do not establish timing, Magic DRC/antenna, transistor LVS, power integrity or engineering approval; further independent checks are running on the same immutable preview geometry.

The [decap preview timing replay](../qualification/evidence/PHYS-01/tpu-decap-nine-view-timing-local-v1.json) performs fresh minimum/nominal/maximum OpenRCX extraction and independently replays all nine views in OpenROAD and standalone OpenSTA. Every timing/electrical metric, clock and resolved constraint matches the original completed matrix baseline exactly: setup slack 78.435868 ns, hold slack 0.174066 ns, capacitance margin 36.980287% and slew margin 27.083424%. The database and SDC remain unchanged. Density still fails on all five metal layers; Magic/layout and power/signoff gates remain separate. The [earlier stopped driver attempt](../qualification/evidence/PHYS-01/tpu-decap-loaded-driver-stop-local-v1.json) is preserved: a loaded checkpoint lacks the in-memory router DRC state expected by the implementation driver, so timing replay uses the production extraction/replay functions directly without inventing a routing count.

The [decap candidate final equivalence proof](../qualification/evidence/PHYS-01/tpu-decap-complete-final-equivalence-local-v1.json) freshly proves all 257 outputs and 4,015 next-state bits from mapped logic to the exact decap candidate, without an imported proof cache. The independent source-to-mapped stage is still running. This completed final-stage proof does not resolve the five failing metal-density layers or grant layout, power or signoff approval.

The [decap candidate exact-netlist switching characterization](../qualification/evidence/PHYS-01/tpu-decap-routed-switching-characterization-local-v1.json) passes all four matrix tiles and 256 scalar results at the unchanged 100 ns clock. All nine independent OpenROAD/OpenSTA activity replays achieve 100% annotation coverage with identical original clocks, resolved constraints and timing metrics. Maximum estimated power is 4.698699 mW under those vectors. Mission activity, power-grid/IR/EM budgets and signoff remain unapproved.

The [exact-reference live reproduction](../qualification/evidence/PHYS-01/aes-live-exact-reference-reproduction-stop-local-v1.json) supplies the complete proven manual S-box after-text as document evidence while retaining original source RTL. Preflight checks all 256 values, validates the exact edit contract and fits a 97,800-character context under the unchanged limit. Fresh baseline proofs and nine-view measurement pass their execution protocols. Two real model calls yield one accepted structured response with no edit: the provider interprets the historical successful recipe as prohibited repetition. No candidate is measured, no live-provider improvement is proven and no signoff is approved. The current prompt clarifies that successful historical experiments may be reproduced for fresh native validation; rejected recipes and recipes in the current run history remain prohibited. Native acceptance and duplicate validation are unchanged.

The [successful-recipe prompt clarification](../qualification/evidence/PHYS-01/rtl-reproduction-guidance-validation-local-v1.json) passes `make check` and all 318 tests. AST comparison confirms only system-prompt text changes; the real historical reference edit validates with empty history and remains rejected when already present in the current run history. Native acceptance files and compatibility fingerprint are unchanged. The [current distribution build](../qualification/evidence/PHYS-01/recipe-reproduction-distribution-build-local-v1.json) rebuilds and installs both tiers offline, verifies packaged/installed source and runtime bytes, and exercises both CLIs outside the checkout. These are software checks, not proof of a successful new live-provider candidate or signoff.

The [24-buffer AES repair trial](../qualification/evidence/PHYS-01/aes-lookup-twenty-four-pin-antenna-repair-failure-local-v1.json) passes all nine timing/electrical views, both complete equivalence stages, both DRC tools and transistor LVS/ERC. Worst setup slack is 90.602157 ns, hold slack 0.221114 ns, capacitance margin 59.732073% and slew margin 14.921916%; cell area is 86,504.210938 square micrometres. Magic antenna findings decrease from 36 to 29 but still fail; small-block density and owner power/integration/approval requirements remain unresolved. Its complete antenna diagnosis and fresh exact-netlist activity replay are running separately.

The [24-buffer AES exact-netlist activity characterization](../qualification/evidence/PHYS-01/aes-lookup-twenty-four-pin-switching-characterization-local-v1.json) passes all three original known answers and all nine timing views with 100% annotation coverage and unchanged original clocks, resolved constraints and timing metrics. Maximum estimated power is 1.787891 mW under those vectors. Antenna still fails with 29 findings; mission activity and power/signoff approval remain unproven.

The [complete 29-finding AES diagnosis](../qualification/evidence/PHYS-01/aes-lookup-single-o21ai-pin-diagnosis-local-v1.json) reproduces every feedback entry and resolves both native layer records to one exact input, `_16258_/B1` on `net693`, disjoint from the previous 24 targets. Equal-scale extracted MOS gate-area sums are 6,360 native square units for that input and 19,800 for buf6. Area-only scaling of the measured 1,073.38 ratio suggests 344.7827 versus the 400 limit; this supports a sizing hypothesis and grants no acceptance. One new buf6 was inserted 5.25 micrometres from the sink with original placements and power routing preserved, and the cumulative 25-buffer trial is undergoing complete native rerouting and qualification.

The [decap candidate native PG/body-pin check](../qualification/evidence/PHYS-01/tpu-decap-power-connectivity-local-v1.json) inspects 664,430 supply/body pins with zero violations and records 175,383 grid vias. The exact candidate database hash is unchanged. This is the production connectivity/geometry check, not static grid IR, conductor EM, approved mission power or engineering/manufacturing acceptance.

The [clarified-guidance live reproduction and transport audit](../qualification/evidence/PHYS-01/aes-live-recipe-guidance-reproduction-stop-local-v1.json) completes fresh baseline measurement and both 129-output/530-state proofs, then makes one real provider call. The valid response contains no edit and again declines full table reconstruction. The complete 5,176-character proven replacement was present in the 97,800-character request: replaying prompt construction exactly reproduces both recorded hashes, with no optimizer or local trimming. No native candidate is measured and live-provider improvement remains unproven. Further retries are not scheduled without new actionable evidence or configuration; all native acceptance gates remain unchanged.

The [completed decap candidate layout validation](../qualification/evidence/PHYS-01/tpu-decap-complete-layout-validation-local-v1.json) reports zero findings in both pinned DRC tools, zero Magic antenna findings and a unique transistor LVS match. Exact candidate ODB, GDS and technology-lock hashes remain unchanged. These isolated checks complement its retained nine-view timing, final equivalence, activity and PG/body-pin evidence. Five metal layers still fail density with 185 findings; the fresh source proof and owner power/IR/EM and independent approval requirements remain separate. This does not establish complete executable-project qualification or engineering/manufacturing acceptance.

The [25-buffer AES repair trial](../qualification/evidence/PHYS-01/aes-lookup-twenty-five-pin-antenna-repair-failure-local-v1.json) passes all nine timing/electrical views, both complete 129-output/530-state proofs, both DRC tools and transistor LVS/ERC. Worst setup slack is 90.577061 ns, hold slack 0.221052 ns, capacitance margin 30.766365% and slew margin 11.015189%; cell area is 86,550.507812 square micrometres. Magic antenna findings increase from 29 to 59, so this is retained as a failed antenna trial. The gate-area projection was a sizing hypothesis, not acceptance; complete fresh diagnosis and exact-netlist activity replay are running separately.

The [complete decap candidate equivalence chain](../qualification/evidence/PHYS-01/tpu-decap-complete-equivalence-local-v1.json) freshly proves all 257 outputs and 4,015 next-state bits in both source-to-mapped and mapped-to-final stages. All 642 unique source SAT miters pass natively, without an imported proof cache, and mapped hashes link both stages. This completes the isolated candidate proof checks; metal density and owner power/IR/EM/independent approval gaps remain unresolved.

The [25-buffer AES activity characterization](../qualification/evidence/PHYS-01/aes-lookup-twenty-five-pin-switching-characterization-local-v1.json) passes all three original known answers and all nine timing views with 100% annotation coverage and original clocks/constraints/timing unchanged. Maximum estimated power is 1.788666 mW under those vectors; antenna and mission power/signoff remain unapproved. The [complete 59-finding diagnosis](../qualification/evidence/PHYS-01/aes-lookup-two-nand-delay-pin-diagnosis-local-v1.json) resolves both electrical records to `_15147_/A` on `ld` and `hold675/A` on `_07629_`, disjoint from the previous 25 targets. Native gate-area-only buf6 projections are 245.907 and 139.107 against the 400 limit; these are sizing hypotheses only. Two new exact-input buffers were inserted in legal whitespace with prepared checkpoint hashes verified, and cumulative 27-buffer qualification is running.

The [read-only supply-cell geometry study](../qualification/evidence/PHYS-01/tpu-supply-cell-metal-geometry-local-v1.json) measures ten pinned filler, decap and tap masters. Native KLayout polygon comparisons show that each master has exactly the same two M1 power-rail shapes for its footprint. Fixed-footprint stock-cell substitution therefore cannot add M1 geometry while preserving routes. The tap cell has two supply pins and is not a four-pin drop-in replacement. The [initial census stop](../qualification/evidence/PHYS-01/tpu-supply-cell-census-stop-local-v1.json) preserves the overly strict four-pin assumption failure. Neither study changes a design or grants density/signoff acceptance; connected metal geometry remains necessary.

The [first grounded-M1 proposal](../qualification/evidence/PHYS-01/tpu-grounded-m1-first-proposal-local-v1.json) identifies 95,014 rectangles in supply-only spans, with contact strips inside actual ground and 0.28 micrometre clearance to other existing M1. Geometric M1 coverage rises from 25.8964% to 33.4406%, below 35%. The [denser proposal](../qualification/evidence/PHYS-01/tpu-grounded-m1-denser-proposal-local-v1.json) preserves that clearance and proposes 118,116 rectangles, reaching 36.0742% geometric coverage. These are geometric studies, not Magic window-density results. A separate native candidate preserves all original signal/placement/pin data, has a byte-identical logical netlist, matches every GDS layer except exactly the proposed grounded-M1 additions, and passes PG/body-pin checking with zero violations; full KLayout and Magic density checks are pending. No full project or signoff approval is inferred.

The cumulative 27-buffer AES repair07 completed native qualification with all nine timing/electrical views, both equivalence stages, both DRC tools, transistor LVS and power-pin ERC passing. Magic antenna verification still failed with 14 findings; the implementation router's zero antenna count does not supersede Magic. Setup slack is 90.56205385604699 ns, hold slack 0.22112084385739195 ns and area 86608.0625 um2 under the unchanged exploratory constraints. The result is retained in `qualification/evidence/PHYS-01/aes-lookup-twenty-seven-pin-antenna-repair-failure-local-v1.json`; fresh switching replay and owner/independent approval remain outstanding.

Fresh exact-netlist switching capture08 and replay08 completed for cumulative27-buffer AES: all three known answers passed at100ns; all nine independent OpenROAD/OpenSTA views reported100% annotation coverage with unchanged clocks, constraints and timing metrics. Maximum known-vector power was0.001788469962776 W. Evidence: `qualification/evidence/PHYS-01/aes-lookup-twenty-seven-pin-switching-characterization-local-v1.json`. This does not clear the14 Magic antenna findings or establish an approved mission workload/power budget.

The actual additive grounded-M1 preview completed:118116 VGND rectangles, preserved native signal connectivity and component/pin/net DEF sections, byte-identical logical netlist, and exact streamed-layer geometry comparison passed. KLayout DRC and power/body-pin ERC each reported0 violations. Magic density still failed with171 findings (23 MET1 and37 each MET2–MET5), improved from185 on the decap candidate. Global MET1 density is39.05570469193776%, but failing local windows prevent acceptance. Retained evidence: `qualification/evidence/PHYS-01/tpu-grounded-m1-native-preview-local-v1.json`. This is not full project qualification; fresh Magic DRC/antenna/LVS, timing, power integrity and independent approval remain outstanding.

The AES14-finding diagnosis completed exact native replay and queried every electrical record. The remaining inputs are `_16007_/B` on `net358` and `_15933_/A2` on `_07323_`, disjoint from all27 prior target pins. Evidence: `qualification/evidence/PHYS-01/aes-lookup-remaining-nand-o21ai-diagnosis-local-v1.json`. Repair08 adds two real buf6 cells at these inputs and has started a fresh complete qualification; insertion success does not establish antenna closure.

Read-only grounded-M1 proposals03/04 compare wider periodic fingers with single clearance-bounded rectangles in existing supply-only spans. Their geometric M1 fractions are0.379056044075103 and0.3854869905289069, respectively; these are not Magic window results. Retained proposals: `qualification/evidence/PHYS-01/tpu-grounded-m1-wide-proposal-local-v1.json` and `qualification/evidence/PHYS-01/tpu-grounded-m1-span-proposal-local-v1.json`. Actual candidate02 built4976 rectangles with preserved connectivity and logical netlist but failed GDS export because preview preparation omitted the results directory; that failed attempt is retained in `qualification/evidence/PHYS-01/tpu-grounded-m1-span-export-stop-local-v1.json`. Corrected candidate03 has started in a fresh directory with the unchanged original sources and mandatory checks.

A read-only native inventory of the unchanged decap source found existing VGND anchors on every upper metal:6734 landing rectangles each on met2/met3 and37 stripes each on met4/met5. This provides measured connection geometry for further grounded-fill work; rectangle area sums contain overlaps and are not density measurements. Source ODB/GDS hashes were unchanged. Evidence: `qualification/evidence/PHYS-01/tpu-upper-metal-native-ground-census-local-v1.json`.

Upper-metal groundwork now has retained read-only connected-growth and rectangular proposals: `qualification/evidence/PHYS-01/tpu-upper-metal-ground-growth-proposal-local-v1.json` and `qualification/evidence/PHYS-01/tpu-upper-metal-ground-rectangle-proposal-local-v1.json`. After conservative1600nm clearance and minimum-dimension filtering, geometric coverage is0.3878593509084133 for met4 and0.4754355551498694 for met5. These are not Magic density measurements.

The first actual upper-metal preview stopped before ODB export because five odd-width/odd-height rectangles could not be represented by native OpenDB SBoxes. The disposable native probe and failed build are retained in `qualification/evidence/PHYS-01/tpu-upper-metal-native-sbox-probe-local-v1.json` and `qualification/evidence/PHYS-01/tpu-upper-metal-native-constructor-stop-local-v1.json`. A revised683-rectangle representation preserves exactly the original668-rectangle union, proven by KLayout XOR0 on each layer (`qualification/evidence/PHYS-01/tpu-upper-metal-ground-exact-representation-local-v1.json`). Actual candidate02 built successfully, preserves original connections and PG geometry, and has passed the exact streamed-layer comparison. Native DRC/density and full qualification remain pending. This upper-metal preview uses the original decap source; it is independent of the separate M1 candidate03, which has passed KLayout DRC0 and is running Magic density.

The complete M1 span preview now reports168 Magic density findings:20 local MET1 failures and37 each MET2–MET5. Global MET1 density increased to0.42290215727855324, while fullKLayout DRC and PG/body-pin ERC remain0. Exact source connectivity/geometry and logical-netlist invariants passed. Evidence: `qualification/evidence/PHYS-01/tpu-grounded-m1-span-native-preview-local-v1.json`. This result shows that filling only existing PG-only cell spans does not close local M1 windows. Read-only study05 is testing growth into source-M1 whitespace with280nm non-ground clearance and verified source-ground contact; it is not an accepted implementation.

The actual upper-metal candidate02 completed its preview. Source connectivity, placement/signal routes, original PG geometry, byte-identical logical netlist and exact GDS layer unions passed; ERC0. Magic density reported111 findings,37 each MET1–MET3, and no MET4/MET5 findings, with global fractions0.4111983262710436 and0.5049682678867167. KLayout DRC still FAILED with12 `m4.5ab` findings (conditional0.4um spacing for3um-wide M4). Evidence: `qualification/evidence/PHYS-01/tpu-upper-metal-native-density-drc-failure-local-v1.json`. This independent preview does not combine the separate M1 candidate or establish full qualification/approval.

Exact DRC marker classification is retained in `qualification/evidence/PHYS-01/tpu-upper-metal-m4-spacing-diagnosis-local-v1.json`. Revised proposal04 removes new widening within4um of all12 markers while preserving the original source metal and functional routes (`qualification/evidence/PHYS-01/tpu-upper-metal-marker-keepout-proposal-local-v1.json`); actual candidate03 is running native checks. M1 growth/control and all-legal-row finger studies are retained in `qualification/evidence/PHYS-01/tpu-grounded-m1-growth-control-local-v1.json` and `qualification/evidence/PHYS-01/tpu-grounded-m1-full-row-proposal-local-v1.json`; their geometric fractions0.2898444960494959 and0.3684418635175136 are forecasts only and do not supersede native density results.

The read-only M2/M3 study01 exceeded its configured600-second native deadline. The native wrapper terminated the process group and process inspection confirmed termination. No completed proposal or density result exists. Evidence: `qualification/evidence/PHYS-01/tpu-middle-metal-proposal-deadline-local-v1.json`. Future work must improve geometry filtering efficiency before retrying; this was an actual native deadline, not an observation timeout.

The native batch-filter optimization passed a complete same-input M4/M5 proposal control: all drawn proposal layers matched the retained reference exactly (XOR0), and positive-overlap versus touch-only and boundary-preserving rectangle selection semantics passed explicit native checks. Source hashes and all clearance/width/ground checks are unchanged. Evidence: `qualification/evidence/PHYS-01/tpu-ground-growth-batch-filter-validation-local-v1.json`. Fresh M2/M3 study02 now uses these validated filters with the original600-second deadline and unchanged geometry limits; it is a changed algorithm, not a restart of the timed-out job.

The optimized M2/M3 study02 completed under the original600-second native deadline. It proposes29549 source-ground-connected, native-representable rectangles with420nm other-metal clearance and unchanged370nm/330nm minimum dimensions. Geometric coverage is0.25960228795218265 for M2 and0.48064413877639506 for M3 (`qualification/evidence/PHYS-01/tpu-middle-metal-six-micron-proposal-local-v1.json`). M2 remains insufficient at this forecast stage. Study03 increases only proposed M2 reach to12um while keeping M3 reach6um and all acceptance/clearance/width/source constraints unchanged. These are read-only proposals, not actual native density/DRC acceptance.

M2 reach12um/M3 reach6um study03 completed with31451 representable, source-ground-connected rectangles and unchanged420nm other-metal clearance. Its geometric fractions are0.3358181892617869 and0.48064413877639506 (`qualification/evidence/PHYS-01/tpu-middle-metal-twelve-micron-proposal-local-v1.json`). Actual middle-metal candidate01 now runs independent native geometry/netlist/ERC/KLayout/Magic density checks to determine actual DRC and density failures, rather than treating forecasts as acceptance. It uses the original decap source and is separate from the M1 and upper-metal previews; no combined project or signoff approval exists.

The manually reordered-lookup AES repair08 completed all required native implementation checks: nine original timing/electrical views, both complete129-output530-state equivalence stages, KLayout DRC0, Magic DRC0/antenna0, transistor LVS and PG/body-pin ERC. Retained evidence: `qualification/evidence/PHYS-01/aes-lookup-twenty-nine-pin-antenna-closure-local-v1.json`. Fresh exact-routed-netlist capture09 passed all three known answers at100ns, and independent nine-view replay09 reported100% activity coverage with unchanged clocks/constraints/timing; maximum known-vector power is0.001789554138668W (`qualification/evidence/PHYS-01/aes-lookup-twenty-nine-pin-switching-characterization-local-v1.json`). Owner mission/power/IR/EM, small-block density/integration and independent approvals remain open. The original sealed release is preserved; the activity characterization is separate evidence.

A direct implementation comparison verifies identical nine-view clocks/resolved constraints, byte-identical PDK lock/assets and all native timing/equivalence/DRC/antenna/LVS/ERC checks for the original repaired AES and the manually reordered/repaired AES. Cell area decreases88597.476562 to86675.632812um2 (2.169185652432326%), while setup slack increases89.94007316687203 to90.5419739183344ns (+0.6019007514623809ns). Capacitance margin decreases49.065171426272386% to30.33070212168676% and hold margin decreases0.221775209308106 to0.22112739417323724ns; every original gate remains satisfied. This compares complete implementations including different physical repairs, and does not attribute all benefits solely to RTL or claim live-provider discovery. Evidence: `qualification/evidence/PHYS-01/aes-closed-implementation-comparison-local-v1.json`.

M1 study07 proposes155070 grounded460nm fingers on620nm pitch with2300nm reach, forecasting geometric coverage0.40307820800666866 (`qualification/evidence/PHYS-01/tpu-grounded-m1-dense-row-proposal-local-v1.json`). Its proposed160nm clearance is a geometry choice; pinned ordinary140nm and conditional wide280nm DRC gates remain unchanged. Actual independent M1 candidate04 is running native checks. Upper-metal marker repair candidate03 has passed native ERC and KLayout DRC0 and is running Magic density; the M2/M3 candidate remains independent. No combined matrix qualification or independent approval exists.

Upper-metal repair candidate03 completed with exact source connectivity/netlist/GDS invariants, PG/body-pin ERC0 and fullKLayout DRC0. Pinned Magic density reported111 findings only onM1–M3 and noM4/M5 global or window failures; globalM4 is0.41071335729211905 andM5 is0.5049682678867167. Evidence: `qualification/evidence/PHYS-01/tpu-upper-metal-drc-density-preview-local-v1.json`. This remains an independent geometry preview; fresh timing/Magic DRC/antenna/LVS, power integrity, combination with other layers and independent approval are outstanding.

Middle-metal candidate01 also completed. Source connectivity/placement/routes/PG geometry, byte-identical logical netlist and exact GDS unions passed; ERC0. KLayout DRC FAILED with798 findings (2m2.1,175m2.2,519m2.3ab,10m3.2,92m3.3cd). Magic density FAILED with146 findings:37M1,35M2,37M4,37M5; M3 has no density findings. GlobalM2 0.37594025428798283 does not clear35 localM2 failures; globalM3 is0.5063753201796062. Evidence: `qualification/evidence/PHYS-01/tpu-middle-metal-native-density-drc-failure-local-v1.json`. Future work must repair actual width/spacing findings and localM2 coverage; this failed preview must not be treated as accepted or combined with the other candidates.

M1 finger candidate04 completed with exact source connectivity/components/signal routes/PG geometry and logical-netlist invariants, exact streamed-layer union, native PG/body-pin ERC0 and fullKLayout DRC0. Magic density reported148 findings onlyM2–M5, with noM1 global/window failures; globalM1 density is0.4385647185746646. Evidence: `qualification/evidence/PHYS-01/tpu-grounded-m1-drc-density-preview-local-v1.json`. The pinned ordinary140nm and conditional wide280nm rules remained unchanged. This is an independent geometry preview, not combined matrix qualification or fresh complete timing/Magic DRC/antenna/LVS/power/approval.

A native source/technology via census found single-cut `M1M2_PR_C` with150nm cut and320nm square M1/M2 enclosures. Its exact native constructor, position, master and bbox passed an in-memory-only probe; the initial missing wire-shape argument failure is preserved. Evidence: `qualification/evidence/PHYS-01/tpu-native-m1-m2-via-anchor-census-local-v1.json` and `qualification/evidence/PHYS-01/tpu-native-single-cut-via-api-local-v1.json`. No source design files changed.

Initial read-only M2 bars proposed new native vias through actual sourceM1 ground to reach previously unanchored spaces. Controls01/02 retained focused width/spacing findings (`qualification/evidence/PHYS-01/tpu-m2-bar-via-initial-control-local-v1.json`, `qualification/evidence/PHYS-01/tpu-m2-bar-via-opened-control-local-v1.json`). Exact focused comparison against the unchanged source found baseline width0/spacing0 versus proposal width413/spacing35, confirming those findings are introduced (`qualification/evidence/PHYS-01/tpu-m2-focused-source-comparison-local-v1.json`). Focused checks do not replace the full pinned deck.

Revised M2 study03 uses160nm-grid bars, keeps320nm clearance from all sourceM2 and source via cuts, places new single cuts on500nm pitch (350nm gap), and removes only new ground around focused corner markers. Source-ground M1 and new-M2 pad enclosures, exact rectangle union, and all source hashes passed. Focused width140nm/spacing140nm/cut-spacing170nm findings are0 after one bounded cleanup. The proposal has93313 rectangles and181927 native vias, geometricM2 0.35641002783535125 (`qualification/evidence/PHYS-01/tpu-m2-gridded-bar-via-proposal-local-v1.json`). Actual M2/via candidate01 built with every source connection and original PG shape preserved and is running independent GDS/ERC/fullDRC/Magic density checks. This forecast does not establish density closure, full qualification or approval.

M3 marker study01 removes only proposed widening within4um keepouts around all102 retained nativeM3 markers;3797 rectangles retain source ground anchors and forecast geometricM3 0.4749863992543016 (`qualification/evidence/PHYS-01/tpu-m3-marker-keepout-proposal-local-v1.json`). Actual M3 candidate01 has built, passed logical-netlist/GDS invariants and ERC0, and is running full native layout checks. It is separate from the M1, M2 and upper-metal previews; a combined fully qualified matrix and owner/independent approvals remain outstanding.

The initial native M2/via candidate completed with source/netlist/exact-GDS invariants and ERC0, fullKLayout DRC0, but164 density findings including16 localM2 failures despite globalM2 0.3831038084738925 (`qualification/evidence/PHYS-01/tpu-m2-native-via-density-preview-local-v1.json`). The M3 marker candidate01 left3m3.3cd findings while allM3 density windows passed (`qualification/evidence/PHYS-01/tpu-m3-three-marker-density-control-local-v1.json`). All three residual markers were retained and added to proposal02 (`qualification/evidence/PHYS-01/tpu-m3-residual-marker-proposal-local-v1.json`). Actual M3 candidate02 now passes ERC and fullKLayout DRC0 and has noM3 global/window density findings;148 density findings remain only on its unchanged other layers (`qualification/evidence/PHYS-01/tpu-m3-drc-density-preview-local-v1.json`).

For executable final qualification, a native inventory found43908 signal/clock nets, all wired and guided, with311517 guides (`qualification/evidence/PHYS-01/tpu-native-checkpoint-guide-inventory-local-v1.json`). A real full detailed_route replay completed its0th optimization/violation scan with0 native DRVs. Before/after COMPONENTS, PINS, NETS and independent SPECIALNETS DEF sections are byte-identical; source files remained unchanged. Evidence: `qualification/evidence/PHYS-01/tpu-native-checkpoint-route-replay-local-v1.json`. This establishes an executable router stage for the final project without invented counters; it does not itself establish final signoff.

Read-only combinedM1/M2 anchor controls used the retained M1-clean source with155252 ground rectangles (`qualification/evidence/PHYS-01/tpu-combined-m1-m2-anchor-census-local-v1.json`). The first proposal stopped when nested region selections merged overlapping contacts and violated prior-via preservation (`qualification/evidence/PHYS-01/tpu-combined-contact-preservation-stop-local-v1.json`). A native overlapping-contact control reproduced that merge and verified exact two-contact preservation with explicit independent-polygon semantics. Corrected proposal02 preserves every prior M2 shape/via and has focused width/spacing/cut0, but adds only0.0005844410355732 geometric coverage to0.35699446887092445 (`qualification/evidence/PHYS-01/tpu-combined-m1-m2-anchor-proposal-local-v1.json`); it is not accepted as clearing the16 native local-density failures.

Wider M2 proposal04 uses320nm physical grid and unchanged320nm clearance from all source metal/cuts, with explicit ordinary140nm, new-wide280nm and cut170nm focused checks0 (`qualification/evidence/PHYS-01/tpu-m2-wide-bar-via-proposal-local-v1.json`). Actual candidate02 (89728 rectangles/171245 native vias) passes source/netlist/exact-GDS invariants, ERC0, fullKLayout DRC0 and every M2 global/window density check. GlobalM2 is0.46027388277716863; its148 density findings are solely on unchanged other layers. Evidence: `qualification/evidence/PHYS-01/tpu-m2-wide-native-drc-density-preview-local-v1.json`. All five target metal layers now have independent KLayout/density-clean previews; this does not substitute for a combined design check.

A full original8x8 combined project is built and production-schema validated:249267 PG rectangles acrossM1–M5 and171245 native vias, preserving source connections/components/signal routes/originalPG, all nine original scenarios, SDC and PDK lock. InputODB SHA2069f12dc9cea32d0f30bcd72867454de80e1e16e6db880ddfb54e7730da0828 is retained with the immutable project preparation (`qualification/evidence/PHYS-01/tpu-combined-ground-project-preparation-local-v1.json`). Its source flow performs real detailed_route replay, retains qualified decaps/fillers and extracts parasitics in a child process. Combined geometry prequalification is running; logical-netlist identity, exact all-layer source-plus-proposal GDS comparison and ERC have passed. Complete combined formal/timing/Magic DRC/antenna/LVS/activity/power and independent owner/manufacturing approvals remain required. Future qualification logs must stay outside the retained preparation directory.

The full original8x8 combined ground geometry prequalification completed successfully: source logical netlist byte-identical, every streamed GDS layer matches original plus exactly proposed M1–M5/via additions, native PG/body-pin ERC0, fullKLayout DRC0 and pinnedMagic density0 across every global/local window. Global fractions are FOM0.3595308726076569, LI0.5677162391358473, M1 0.4295631955793496, M2 0.4516873240839948, M3 0.5052410988710652, M4 0.41060291241503627 and M5 0.5048163065870224. Evidence: `qualification/evidence/PHYS-01/tpu-combined-ground-drc-density-preview-local-v1.json`.

Full qualification has now started separately at `.dv-platform/tpu-combined-ground-qualification-01` from the immutable production-validated project. Its log is adjacent (`.dv-platform/tpu-combined-ground-qualification-01.execution.log`), outside the retained preparation directory. It must measure the actual final router state, rerun all original nine timing views and independent OpenSTA, both complete formal stages, Magic DRC/antenna and transistor Netgen LVS, plus remaining activity/power/requirements checks. No external formal proof cache, benchmark/proof reduction or relaxed original constraints are allowed. The combined precheck does not grant final approval; owner operating/mission/area/power/IR/EM inputs and independent trust/engineering/manufacturing approvals remain absent.

The complete combined implementation stage finished under the original constraints: all nine timing/electrical views pass with setup slack78.425159699691ns, hold slack0.17111229100308378ns, capacitance margin37.01398493617128%, slew margin27.08423150362192% and cell area386479.4375um2. A read-only post-implementation snapshot audit found COMPONENTS, PINS, NETS and SPECIALNETS DEF sections byte-identical to the prepared combined input. Parent full qualification is still running formal/layout/release checks; its live baseline outputs are not retained as final qualification artifacts yet.

Fresh capture10 on the exact completed routed netlist passed all four known-answer tiles/256 scalar results at100ns,160 rises and16000ns. Independent OpenROAD/OpenSTA replay10 completed all nine views with100% activity annotation coverage, unchanged clocks/resolved constraints and every timing metric; maximum known-vector power is0.004698315169662W. This separate completed characterization is retained in `qualification/evidence/PHYS-01/tpu-combined-ground-routed-switching-characterization-local-v1.json`. It does not establish an approved mission workload, power-integrity compliance or independent signoff. The qualification parent remains active and must finish both complete formal stages, Magic DRC/antenna, transistor Netgen LVS and all required release checks.

The subsequent fresh combined qualification02 completed with a failed native gate. All nine timing views, both full equivalence proofs (257 outputs and 4,015 next-state bits each), KLayout DRC, Magic antenna, density, Netgen LVS and ERC passed. Magic DRC reported 302 wide-metal spacing violations. The terminal run and adjacent log are retained in [the completed qualification evidence](../qualification/evidence/PHYS-01/tpu-combined-ground-completed-qualification-local-v1.json). Requirements, mission activity and power-integrity checks remain unknown; no signoff approval was granted. Separate marker-directed ground-geometry repairs are undergoing native checks. The first corrected candidate preserved exact GDS geometry and passed ERC but exposed 108 KLayout spacing/floating-metal findings; its successor remains unqualified.

The marker-directed spacing repair now preserves exact streamed geometry and passes ERC, full KLayout DRC and every Magic density window in [the clean preview](../qualification/evidence/PHYS-01/tpu-combined-ground-spacing-clean-preview-local-v1.json). A separate pinned Magic full-DRC execution reports zero violations and an empty details report, but its wrapper failed while serializing a receipt; [the raw result and independent audit](../qualification/evidence/PHYS-01/tpu-combined-ground-spacing-magic-zero-local-v1.json) retain that distinction. The [immutable repaired project](../qualification/evidence/PHYS-01/tpu-combined-ground-spacing-project-preparation-local-v1.json) preserves the original benchmark, nine timing scenarios, constraints and verification policy. Its fresh full qualification at `.dv-platform/tpu-combined-ground-spacing-qualification-01` has passed all nine timing views and both complete equivalence proofs (257 outputs and 4,015 next-state bits each). Full physical verification is still running; these intermediate results do not establish final qualification or approval.

Fresh capture11 on the spacing-repaired exact routed logical netlist passed all four tiles/256 scalar results at the original100ns clock,160 rises and16000ns; [all79 capture artifacts are retained](../qualification/evidence/PHYS-01/tpu-spacing-repaired-routed-switching-capture-local-v1.json). Independent OpenROAD/OpenSTA replay11 then passed all nine views with100% activity annotation coverage, identical original clocks/resolved constraints and unchanged timing metrics within1e-6. Maximum known-vector power is0.004698293283582W; [all276 replay artifacts are retained](../qualification/evidence/PHYS-01/tpu-spacing-repaired-routed-switching-replay-local-v1.json). This binds characterization to the repaired implementation but does not supply an approved mission workload, power/IR/EM limits, or independent signoff. Parent full physical qualification remains active.

The fresh spacing-repaired full qualification completed with CLI exit0. All14 release checks were inspected: timing, source/final equivalence, KLayout DRC, Magic DRC, antenna, density, Netgen LVS and ERC passed; requirements, activity, power_grid, ir_drop and em remain unknown. Both fresh proofs cover257 outputs and4015 next-state bits, with all five mutation controls rejected and positive controls passed. KLayout/Magic DRC, antenna, density and ERC have zero violations; Netgen reports a unique match. The complete stable run and adjacent log are retained as8749 artifacts in [the repaired completed-qualification evidence](../qualification/evidence/PHYS-01/tpu-spacing-repaired-completed-qualification-local-v1.json). No external proof cache or original benchmark/constraint reduction was used. This supersedes the earlier running status for this candidate; it does not grant approved mission/power requirements or independent signoff. Separate capture11/replay11 remains characterization only.

AES density remains unknown because its retained466.33um die is below the pinned deck's700um minimum; missing analysis cannot be waived. A separate750um die/730um core project has been production-schema validated and [retained as120 preparation artifacts](../qualification/evidence/PHYS-01/aes-density-supported-project-preparation-local-v1.json). Original full AES RTL, mapped/reference netlists, all nine scenarios, SDC, policy and PDK bytes are unchanged. The existing native implementation flow is reused with an explicit supported floorplan, the existing RC/extraction helper and a post-placement recovery checkpoint. Initial implementation at `.dv-platform/aes-density-supported-implementation-01` has completed placement and reached detailed routing; no new timing, density, formal or physical qualification pass is claimed. Logs remain outside the retained preparation directory. This exploratory die size is not an approved manufacturing floorplan.

The supported-density750um AES native implementation completed placement, routing and independent OpenSTA replay for all nine original scenarios. All clocks and resolved-constraint hashes match the retained prior AES implementation; setup slack90.32141434772711ns, hold slack0.23001356375118576ns, capacitance margin23.493202198858153%, slew margin21.114200353622437% and cell area91799.296875um2. Final detailed-router and router-antenna counts are zero. The local summary wrapper then exited1 on a nonexistent `run.best.analysis` field; the completed native `run.json` reports `timing_closed`, and an independent read-only audit verifies all nine OpenROAD/OpenSTA scenario margins and all120 preparation hashes. [All309 terminal implementation/log/audit artifacts are retained](../qualification/evidence/PHYS-01/aes-density-supported-native-implementation-local-v1.json); the failed immutable wrapper was preserved without rerunning the native design. This is a changed exploratory floorplan, not a new RTL improvement comparison. A separate copied layout/density control has passed exact logical-netlist export and PG/body-pin ERC0; KLayout/density and complete final formal/Magic/LVS qualification remain pending.

Supported750um AES density repair now has cumulative native FOM/LI/M1/M2 closure. The uniform85% wide-decap control cleared FOM but exceeded the pinned60% LI maximum; the55% control cleared LI but fell below the pinned33% FOM minimum. Both failed controls remain retained. A [read-only spatial study](../qualification/evidence/PHYS-01/aes-spatial-decap-readonly-study-local-v1.json) reproduced every native FOM/LI aggregation from three controls and checked its projection against the held-out55% run. Its28103 explicitly selected matching-footprint PG-only substitutions then [passed every actual local/global FOM and LI check](../qualification/evidence/PHYS-01/aes-spatial-decap-fom-li-closure-local-v1.json), with strict raw physical-master-difference checks,byte-identical normalized functional netlists,ERC0 and fullKLayoutDRC0. No threshold or deck change was made.

The subsequent [native groundedM1 result](../qualification/evidence/PHYS-01/aes-grounded-m1-native-density-closure-local-v1.json) adds135803 anchored rectangles and clears M1 density; the [cumulative groundedM2 result](../qualification/evidence/PHYS-01/aes-grounded-m2-native-density-closure-local-v1.json) adds13189 rectangles and123208 source-enclosed nativevias and clears M2 density. Both preserve components,pins,signal routes,pin/net connections and originalPG geometry,pass exact all-layer source-plus-proposal GDS comparisons,raw logical export identity,ERC0 and fullKLayoutDRC0. The latest completed result has15 density findings solely onM3/M4/M5. A source-ownedM3 growth candidate is running separately. Fresh final nine-view timing,complete source/final formal,Magic DRC/antenna,Netgen LVS,power and independent approvals remain required; pre-fill timing is not final-fill qualification.


The first cumulative AES M3 control completed with exact source-plus-M3 GDS,
identical logical export and zero ERC findings, but failed native KLayout DRC
with 96 spacing findings (8 ordinary and 88 wide-metal). Its pinned density
replay reported 14 findings: four FOM and five each on M4/M5; M3 density passed.
The complete failed control is retained in
[`aes-grounded-m3-spacing-failed-control-local-v1.json`](../qualification/evidence/PHYS-01/aes-grounded-m3-spacing-failed-control-local-v1.json).
The next read-only proposal uses those actual AES markers, expands their bounds
by 4 um and rounds outward to the 5 nm manufacturing grid before trimming only
added M3 geometry. Its 666 rectangles preserve source geometry and ground
anchoring; see
[`aes-grounded-m3-native-marker-proposal-local-v1.json`](../qualification/evidence/PHYS-01/aes-grounded-m3-native-marker-proposal-local-v1.json).
The first marker repair reduced native KLayout spacing findings from 96 to 3.
A second read-only proposal adds those three actual marker keepouts, retains
664 rectangles and passes exact geometry and ground-anchor checks; see
[`aes-grounded-m3-cumulative-marker-proposal-local-v1.json`](../qualification/evidence/PHYS-01/aes-grounded-m3-cumulative-marker-proposal-local-v1.json).
Its native candidate replay is pending. FOM/LI balance must be checked again
against the final upper-metal geometry; prior lower-layer density passes do not
replace that replay or final timing, equivalence, Magic, LVS, power and approval
checks.


The cumulative 99-marker AES M3 candidate subsequently passed full KLayout DRC
with zero findings, ERC with zero findings, exact all-layer source-plus-M3 GDS
comparison and byte-identical logical export. Its completed density replay passes M3, with 14 findings remaining solely on
FOM (four), M4 (five) and M5 (five). The complete native preview is retained in
[`aes-grounded-m3-native-spacing-closure-local-v1.json`](../qualification/evidence/PHYS-01/aes-grounded-m3-native-spacing-closure-local-v1.json).
A read-only native upper-PG census and first M4/M5 proposal are retained
in
[`aes-m3-clean-upper-native-census-local-v1.json`](../qualification/evidence/PHYS-01/aes-m3-clean-upper-native-census-local-v1.json)
and
[`aes-upper-ground-first-proposal-local-v1.json`](../qualification/evidence/PHYS-01/aes-upper-ground-first-proposal-local-v1.json).
The upper proposal has 347 ground-anchored rectangles with 4 um non-ground
clearance; its 32.84% M4 and 45.24% M5 geometric coverage is not a native density
pass. The cumulative M4/M5 native trial has started; full upper-layer checks
and final cumulative qualification remain required.


The first cumulative M4/M5 native control completed with 13 spacing findings
and six density findings: four FOM and two local M4 windows. M5 passed all local
and global density checks; global M4 passed but its lowest local window was
33.69% against the unchanged 35% minimum. The complete control is retained in
[`aes-upper-spacing-local-density-control-local-v1.json`](../qualification/evidence/PHYS-01/aes-upper-spacing-local-density-control-local-v1.json).
Applying the 13 actual native marker keepouts reduced KLayout findings to zero
with unchanged source geometry and logical export. That completed density
control is retained in
[`aes-upper-native-spacing-closure-density-control-local-v1.json`](../qualification/evidence/PHYS-01/aes-upper-native-spacing-closure-density-control-local-v1.json).
Increasing only M4 ground growth from 4 um to 5 um, retaining all keepouts and
4 um non-ground clearance, also passed full KLayout and ERC with zero findings.
Its all-layer pinned density replay is pending; the proposal is retained in
[`aes-upper-ground-local-density-repair-proposal-local-v1.json`](../qualification/evidence/PHYS-01/aes-upper-ground-local-density-repair-proposal-local-v1.json).
A prepared read-only incremental decap projection will use the completed
upper-metal density measurements before selecting additional physical-only
matching-footprint substitutions. No further density, timing, Magic, LVS, power
or signoff approval pass is claimed.


The 5 um M4 growth trial completed with zero full KLayout and ERC findings.
All LI and M1 through M5 local/global pinned density checks pass; only four FOM
minimum-density findings remain. Its complete source-preserving native preview
is retained in
[`aes-upper-native-metal-density-closure-local-v1.json`](../qualification/evidence/PHYS-01/aes-upper-native-metal-density-closure-local-v1.json).
An initial read-only decap diagnostic correctly stopped at its POLY-invariance
guard: physical decaps themselves add POLY, so that assumption cannot calibrate
filler-to-decap controls. The rejected diagnostic is retained in
[`aes-incremental-decap-poly-assumption-rejected-local-v1.json`](../qualification/evidence/PHYS-01/aes-incremental-decap-poly-assumption-rejected-local-v1.json).
The corrected empirical projection anchors to actual current FOM/LI tile values,
uses measured native 0/85-percent response slopes, and independently checks the
55-percent control. It selects 500 additional matching-footprint physical-only
decaps (456 eight-site and 44 four-site), predicting passing FOM/LI margins;
see
[`aes-incremental-decap-measured-projection-local-v1.json`](../qualification/evidence/PHYS-01/aes-incremental-decap-measured-projection-local-v1.json).
The separate native decap trial is running with strict position, master,
connectivity, route and exact PINS/NETS/SPECIALNETS preservation guards. Predicted
margins do not replace its full native layout/density replay or final cumulative
qualification and approval.


The incremental 500-decap native trial completed with zero ERC, full KLayout
DRC and pinned density findings. All local/global checks on FOM, LI and M1
through M5 pass. Actual FOM is 33.2682% globally and at least 33.2520% locally;
LI is 59.3611% globally. All original instance positions, functional cells,
connections and routes are preserved; exact PINS/NETS/SPECIALNETS sections and
normalized functional exports match. The complete preview is retained in
[`aes-cumulative-all-density-native-closure-local-v1.json`](../qualification/evidence/PHYS-01/aes-cumulative-all-density-native-closure-local-v1.json).
The exact cumulative checkpoint is frozen in
[`aes-cumulative-fill-project-preparation-local-v1.json`](../qualification/evidence/PHYS-01/aes-cumulative-fill-project-preparation-local-v1.json).
Native inventory confirms 97,810 persisted guides on all 11,091 routed nets;
no routed net lacks guides. All nine original scenarios, RTL, timing
constraints, requirements and PDK files remain unchanged. Fresh full native
qualification has started: actual detailed-router replay, new extraction and
nine-view timing, complete source/final transition proofs, Magic DRC/antenna,
KLayout, pinned density, Netgen LVS and ERC. The clean preview does not establish
those final results or independent power, engineering or manufacturing approval.


Fresh cumulative AES qualification has completed actual detailed-route replay
with zero router/antenna violations, and all nine original OpenROAD/OpenSTA views
pass: setup slack 90.32594 ns, hold slack 0.23001 ns, capacitance margin 23.49566%,
slew margin 21.11413%, cell area 91,799.296875 um2. Both newly executed complete
transition proofs pass all 129 outputs and 530 next-state bits; final KLayout DRC
has zero findings. Magic verification is still running, followed by remaining
post-replay layout checks. The parent qualification output is not retained as a
completed run until its process terminates.
Fresh three-vector known-answer tests passed on the exact routed netlist at the
unchanged 100 ns clock; their 4,500 ns switching capture and independent nine-view
replay are retained in
[`aes-cumulative-routed-switching-capture-local-v1.json`](../qualification/evidence/PHYS-01/aes-cumulative-routed-switching-capture-local-v1.json)
and
[`aes-cumulative-routed-switching-replay-local-v1.json`](../qualification/evidence/PHYS-01/aes-cumulative-routed-switching-replay-local-v1.json).
Every view has 100% annotation coverage, identical original timing and a maximum
known-vector power estimate of 1.724098 mW. These measurements do not establish
approved mission activity, power/IR/EM budgets or independent signoff approval.


Magic completed DRC and extraction on the cumulative AES implementation and
reported two M4 spacing-marker rectangles; antenna checking is still active.
Current DEF/EXT calibration matches 100 placed/fixed N-oriented instances at
5 nm per Magic unit, with zero matches at the tested 1 nm and 10 nm scales.
A native inventory identifies the exact added upper-metal group of 350 objects.
Removing the three marker-adjacent M4 rectangles would strand other added fill,
so the grounding guard rejected that read-only proposal; see
[`aes-magic-m4-three-rectangle-grounding-rejected-local-v1.json`](../qualification/evidence/PHYS-01/aes-magic-m4-three-rectangle-grounding-rejected-local-v1.json).
The revised six-rectangle proposal also removes the three newly unanchored added
M4 descendants. Every remaining fill component overlaps actual original ground;
all 4,401 native M4 ground anchors match the source GDS. Its expected drawn-area
reduction is 112.7542 um2; see
[`aes-magic-m4-anchored-removal-proposal-local-v1.json`](../qualification/evidence/PHYS-01/aes-magic-m4-anchored-removal-proposal-local-v1.json).
The guarded separate native repair workspace is prepared but not launched. It
requires parent termination, retention of the complete failed control, and
passing results on every other native parent gate before deleting only those
six identified added M4 objects. Exact preservation, full DRC/density and fresh
complete qualification remain required; no violation waiver or approval exists.

A distinct configured-provider case addresses the earlier lookup-table copying
refusal by freezing the S-box and restricting edits to the encryption datapath,
key schedule and Rcon. All five original AES source files, the original setup
objective and every physical input, constraint and nine-view gate remain byte
identical. The known rejected MixColumns recipe remains supplied evidence. The
validated case and frozen unchanged helper are retained in
[`aes-bounded-datapath-provider-preparation-local-v1.json`](../qualification/evidence/PHYS-01/aes-bounded-datapath-provider-preparation-local-v1.json).
One optimization iteration is running its fresh full native baseline; it has
not yet recorded a provider response or accepted improved candidate. Any edit
still requires complete new proofs and native physical measurements. This case
does not attribute the measured manual lookup improvement to the provider.


The bounded datapath case has now terminated with no improvement and no native
candidate. Its single optimization iteration made two provider requests: the
first response failed source/document citation validation; the corrected response
was a structured abstention. The provider could not identify a distinct RTL
operation to optimize from the existing register-level source map without
repeating the known rejected MixColumns recipe. The baseline remains selected;
all original sources and requirements are unchanged. The complete run is retained
in
[`aes-bounded-datapath-provider-abstention-local-v1.json`](../qualification/evidence/PHYS-01/aes-bounded-datapath-provider-abstention-local-v1.json).
Preparation intended one request; the unchanged helper's automatic validation
correction produced the actual two, which are explicitly recorded. No accepted
live-provider improvement is claimed. Further provider work requires verified
operator-level timing evidence or another concrete corrective change, not an
unchanged repetition of this prompt. The cumulative-layout parent remains active
in Magic antenna analysis, and its six-object M4 repair remains queued behind
parent completion and the complete retained control.

The engineer-guided AES cofactor provider trial now has a separate
[recovery audit](../qualification/evidence/PHYS-01/aes-cofactor-provider-recovered-native-improvement-local-v1.json).
One accepted provider request made two source edits; full source and mapped proofs,
a fresh complete mapped-to-routed proof, and nine native timing views establish
+0.5270877068 ns setup margin and -0.3595326905% cell area against the unchanged
baseline. The original optimizer record remains interrupted and unfinalized.
Capacitance and slew still fail, and independent discovery and signoff are not claimed.
The separate cumulative-fill AES qualification completed with two Magic spacing
violations and 511 antenna feedback entries; its other seven native gates passed.
A six-rectangle M4 removal passes native preview checks but needs fresh Magic and
antenna verification. Diagnostic metal-node queries timed out, and grouping feedback
as raw metal was rejected by its coverage guard; neither supplies accepted repair targets.

A subsequent [exact pin correlation](../qualification/evidence/PHYS-01/aes-cumulative-antenna-exact-pin-correlation-local-v1.json)
matched all 82,952 extracted instance transforms to OpenDB and correlated 58
gate-shaped antenna feedback boxes to 27 physical input pins. The
[local buffer slot plan](../qualification/evidence/PHYS-01/aes-antenna-local-buffer-slot-plan-local-v1.json)
finds nearby slots affecting 55 physical fill/decap cells without moving functional
cells. This remains a read-only plan pending complete pinned Magic debug coverage;
no buffer repair or antenna closure is claimed.
A [paired electrical-repair study](../qualification/evidence/PHYS-01/aes-cofactor-paired-electrical-repair-preparation-local-v1.json)
is prepared and running with identical slew/cap repair margins of 30/20 for the
original baseline and provider cofactor candidate. Requirements, RTL, PDK and
all nine timing views remain unchanged. Preparation does not establish closure
or preservation of the earlier relative improvement.

[Full feedback material classification](../qualification/evidence/PHYS-01/aes-antenna-full-feedback-gate-metal-classification-local-v1.json)
now independently verifies that 58 feedback boxes exactly equal rectangular
source GDS poly/active gate-channel components, while all 453 remaining boxes
are covered by their reported drawn metal layers. Together with exact instance
correlation, this resolves the 27 candidate input pins. The
[ground keepout plan](../qualification/evidence/PHYS-01/aes-antenna-buffer-native-ground-keepout-plan-local-v1.json)
removes only 115 declared added M1 fingers and preserves full M1 ground coverage
of all 194 nearby native via landings. An isolated 27-buffer preview passes ERC
but reports 28 n-well spacing markers where whole physical fillers were removed.
A second preview restores only local physical filler gaps under placement,
connection, PG geometry and footprint guards. Full fresh routing and native
qualification remain pending; neither preview establishes antenna closure.

The [restored-filler 27-buffer preview](../qualification/evidence/PHYS-01/aes-local-buffer-restored-filler-native-preview-local-v1.json)
completed with native ERC, KLayout DRC and every pinned density check reporting
zero violations. It restored 76 physical filler cells entirely inside the 55
removed filler/decap footprints, preserving all prior placements, connections and
PG wire objects. The [fresh qualification project](../qualification/evidence/PHYS-01/aes-local-buffer-fresh-project-preparation-local-v1.json)
clears only the 54 affected signal nets and guards every other route/guide,
placement, connection and PG shape. Qualification now runs actual global/detail
routing, complete equivalence, all nine original timing views and every native
layout check. The passing preview is not final routed verification or signoff.

Fresh qualification of the 27-buffer candidate completed routing with zero
routing DRC and passed both complete equivalence stages (129 outputs and 530
next-state bits each). Nine-view electrical timing remains positive: setup
90.32012116 ns, hold 0.23001018 ns, cap 23.49565897%, slew 21.11340761%.
Four native antenna findings keep overall physical closure open. The
[read-only native report](../qualification/evidence/PHYS-01/aes-local-buffer-four-native-antenna-targets-local-v1.json)
identifies the exact four pins. A separate
[jumper-only control](../qualification/evidence/PHYS-01/aes-local-buffer-native-jumper-no-improvement-control-local-v1.json)
preserved all cell/port/net/PG invariants but left all four findings unchanged.
The [four-diode slot plan](../qualification/evidence/PHYS-01/aes-local-buffer-four-native-diode-slot-plan-local-v1.json)
finds nearby slots affecting five physical fillers, at most 2.95 micrometres
from the affected sink. An isolated four-diode candidate has since been built; its geometry preview is
running. Fresh routing and full qualification remain pending.
The [completed source Magic debug replay](../qualification/evidence/PHYS-01/aes-cumulative-magic-debug-exact-pin-corroboration-local-v1.json)
reproduced all 511 feedback entries byte for byte, with 29 electrical error
records covering exactly the 27 input pins identified geometrically.
The stricter paired electrical study stopped at a helper error: reference.v
was passed to mapped equivalence instead of the flow-read mapped.v. Its
[failed record](../qualification/evidence/PHYS-01/aes-cofactor-paired-electrical-wrong-proof-reference-control-local-v1.json)
is retained unchanged. A separate recovery bound the actual mapped input to
its mapping certificate and passed a fresh complete baseline final proof;
the candidate is now measuring under the same stricter repair margins.
This does not establish electrical closure, a new accepted improvement or signoff.

The [four-diode ground-preservation plan](../qualification/evidence/PHYS-01/aes-local-buffer-four-diode-ground-preservation-plan-local-v1.json)
needs no power-metal removal and preserves full M1 coverage of all 22 nearby
native ground-via landings. The isolated diode preview removes only five
physical filler cells and restores 14 fillers entirely inside those footprints.
All existing signal connections, other placements and PG objects are guarded
unchanged. ERC and KLayout DRC pass with zero violations; density, actual
rerouting and complete qualification remain pending. No antenna closure or signoff is claimed.

The [four-diode preview](../qualification/evidence/PHYS-01/aes-local-buffer-four-diode-native-preview-local-v1.json)
completed with native ERC, KLayout DRC and all pinned density checks at zero.
Its [fresh qualification project](../qualification/evidence/PHYS-01/aes-local-buffer-four-diode-fresh-project-preparation-local-v1.json)
clears only the four affected signal nets, preserving every other route/guide,
placement, connection and PG object. Actual fresh routing and complete native
qualification are running; the preview does not establish antenna closure.
An [isolated qualification guard fix](../qualification/evidence/PHYS-01/qualification-nine-native-gate-guard-isolated-review-local-v1.json)
reproduced four false-success cases for failed/unknown timing or density. The
fixed copy passes seven targeted tests plus lint and formatting, and now serves
as this new project's frozen qualification entry. It requires all nine native
gates while leaving owner approval unknown. Production script/test application
waits for the older original entry worker to terminate; running files remain
unchanged. Requirements, timing constraints and acceptance limits are preserved.

Fresh four-diode routing reached zero native routing DRC and reduced native
antenna findings from four pins to one. All nine electrical timing views remain
positive (setup 90.32012116 ns, hold 0.23001012 ns, cap 23.49565897%, slew
21.11340761%). The [remaining native finding](../qualification/evidence/PHYS-01/aes-local-buffer-four-diode-remaining-native-antenna-pin-local-v1.json)
is hold433/A on text_in[83]: metal-1 sidewall ratio 487.31 against limit 400.
A [read-only one-buffer slot plan](../qualification/evidence/PHYS-01/aes-local-buffer-final-pin-large-gate-slot-plan-local-v1.json)
finds a BUF6 slot 2.95 micrometres from the sink, affecting two physical fillers.
Its measured library antenna input area is 0.495 versus 0.126 square micrometres
for the delay input. This supports a repair hypothesis; no buffer insertion or
antenna closure is claimed. Complete routed layout verification remains running.

The [remaining-pin buffer preview](../qualification/evidence/PHYS-01/aes-local-buffer-final-pin-native-preview-local-v1.json)
passes ERC, KLayout DRC and every density check. Two physical fillers are
replaced and three restored only inside their footprints, with no PG removal;
[all 13 nearby ground-via landings remain covered](../qualification/evidence/PHYS-01/aes-local-buffer-final-pin-ground-preservation-plan-local-v1.json).
The [fresh project](../qualification/evidence/PHYS-01/aes-local-buffer-final-pin-fresh-project-preparation-local-v1.json)
clears only the input and new buffer-output nets. Actual fresh routing now
reports zero routing DRC and zero native antenna net/pin violations. Independent
timing, complete proofs and final Magic/layout checks remain running.
The [corrected paired provider study](../qualification/evidence/PHYS-01/aes-cofactor-paired-electrical-recovered-native-study-local-v1.json)
completed with fresh complete final proofs for both designs. The unchanged
selection rule accepts +0.37197623 ns setup margin with +0.43662873% area;
capacitance is positive at 13.39474820%, while slew remains -6.51931117%.
An [exact worst-slew replay and native driver correlation](../qualification/evidence/PHYS-01/aes-cofactor-exact-remaining-slew-driver-local-v1.json)
locates all 129 violating inputs on net807, driven by load_slew807/X (BUF16),
with worst transition 1.597790 ns against the original 1.5 ns limit. No slew
repair or complete electrical/layout closure is claimed for that variant.

Independent native replay for the final-pin candidate now reports timing closed
in all nine views: setup 90.32012116 ns, hold 0.23001012 ns, cap 23.49565897%,
slew 21.11340761%, area 92124.601562 square micrometres, routing DRC zero and
native antenna net/pin findings zero. Complete equivalence and final Magic,
LVS/ERC and density verification remain running; timing closure is not signoff.

The final-pin repaired AES passed both complete source/final proofs (129
outputs and 530 next-state bits each) and routed KLayout DRC with zero findings.
Its [fresh routed known-answer capture](../qualification/evidence/PHYS-01/aes-final-pin-routed-known-answer-switching-capture-local-v1.json)
passes all three original AES vectors at 100 ns, 45 clock rises and 4500 ns.
[Independent nine-view activity replay](../qualification/evidence/PHYS-01/aes-final-pin-routed-known-answer-activity-replay-local-v1.json)
has 100% annotation coverage in every view, unchanged timing and maximum
estimated benchmark power 0.001725288224407 W. It is not approved mission activity.
For the provider variant, a [BUF16 slot proposal was rejected](../qualification/evidence/PHYS-01/aes-cofactor-slew-buf16-distance-guard-control-local-v1.json)
by the unchanged 55-micrometre proximity guard (nearest tested slot 63.67).
The [smaller BUF12 plan](../qualification/evidence/PHYS-01/aes-cofactor-slew-buf12-balanced-branch-slot-plan-local-v1.json)
places two branches within 50.81 micrometres, replacing six ordinary fillers.
The [frozen repair preparation](../qualification/evidence/PHYS-01/aes-cofactor-two-branch-physical-repair-preparation-local-v1.json)
binds slots by exact representative sink and preserves unselected loads,
source driver, other cells/connections, ports and PG objects.
[Fresh native repair measurement and complete proof](../qualification/evidence/PHYS-01/aes-cofactor-two-branch-native-electrical-closure-local-v1.json)
now close all nine views: setup 89.70921073 ns, hold 0.22515423 ns, cap
13.39474820%, slew 13.96109042%, area 87247.429688 square micrometres,
native DRC/antenna zero. A fresh mapped-to-routed proof passes 129 outputs
and 530 next-state bits. This is post-selection physical repair of unchanged
optimized RTL, not a new RTL proposal or a new controlled paired RTL claim.
Layout/power qualification and approved signoff remain unestablished for that variant.

The older 27-buffer qualification completed: Magic DRC, routed KLayout DRC,
LVS, ERC and density pass, while Magic antenna reports 69 feedback entries and
OpenROAD reports four pin violations. Its two complete proofs passed; no release
approval is claimed. Newer four-diode and remaining-pin repairs are separately
running full verification, preserving the completed older record.
Once the original entry worker terminated, the reviewed qualification success
guard was applied to scripts/qualification/sky130.py and its regression tests.
Timing and density are now mandatory alongside the other seven native gates.
All seven targeted tests pass; full make check and make test are running.

The production qualification guard preserves the existing tiny installation
fixture through explicit `--tool-smoke` mode, now used by native CI and its docs.
The CLI summary and evidence label that scope, retain failed/unknown closure
statuses, and never call it full qualification or signoff. Normal qualification
requires all nine native gates. Ten targeted tests cover strict-mode failures,
smoke scope, mandatory native proofs and ambiguous Python argument rejection;
all 323 repository tests and make check pass. See the
[production validation](../qualification/evidence/PHYS-01/qualification-nine-gate-production-and-smoke-compatibility-validation-local-v1.json)
and [real native protocol smoke](../qualification/evidence/PHYS-01/qualification-explicit-tool-smoke-native-protocol-validation-local-v1.json).
The [four-diode full control](../qualification/evidence/PHYS-01/aes-local-buffer-four-diode-completed-magic-zero-control-local-v1.json)
completed with Magic antenna/DRC, KLayout DRC, LVS/ERC and density all passing;
its one OpenROAD antenna finding keeps the overall timing gate failed.
The newer inline-buffer candidate, which clears that finding, remains running
final verification. The [older 69-feedback material diagnosis](../qualification/evidence/PHYS-01/aes-local-buffer-69-feedback-gate-metal-diagnosis-local-v1.json)
finds ten gate channels and 59 conductor boxes. Its
[exact poly/instance correlation](../qualification/evidence/PHYS-01/aes-local-buffer-69-feedback-exact-four-pin-correlation-local-v1.json)
matches all 83,000 extracted instances and resolves exactly the same four
input pins as OpenROAD, with no extra or missing targets. It is an older-control
diagnosis, not proof of the newest candidate's Magic result.

The [completed final-pin AES qualification](../qualification/evidence/PHYS-01/aes-final-pin-completed-nine-native-gate-qualification-local-v1.json)
now passes all nine native gates: both complete proofs, nine-view timing,
Magic/KLayout DRC, Magic antenna, density and uniquely matched LVS/ERC. All
reported layout violations are zero and all five formal mutations are rejected.
This joins the already completed full 8x8 INT8/INT32 matrix qualification.
The [owner handoff index](../qualification/evidence/PHYS-01/native-benchmarks-owner-handoff-readiness-local-v1.json)
verifies both canonical release hashes and lists the unchanged missing area,
power, IR/EM, mission, boundary, source-location and conductor inputs plus public
signing trust and independent approvals. No values or production authority are
invented; frozen historical projects must not be edited to approve them.
The separate provider variant is electrically closed and completely proven but
not layout-qualified. Its actual die is 474.225 micrometres square, below the
pinned 700x700 whole-chip density window. It needs a compatible approved physical
context before full layout qualification; its earlier paired PPA results must
not be attributed to a different floorplan. Approved signoff remains incomplete.
