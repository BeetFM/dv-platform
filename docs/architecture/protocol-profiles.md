# Protocol Profile Contract

Protocol-profile schema v1 is the shared transaction vocabulary for recognition,
planning, generators, coverage, formal properties, result traces, and future UVM
agents. The machine-readable interchange shape is
[protocol-profile-v1.schema.json](../../schemas/verification/protocol-profile-v1.schema.json).

The built-in catalog defines bounded profiles for AXI4-Lite, full AXI4,
packet-complete AXI4-Stream, Wishbone B4, Avalon-MM, Avalon-ST, burst-capable
AHB, and non-coherent TileLink UL/UH. Each profile declares endpoint roles,
canonical channel signals and widths, optional sidebands, acceptance and
completion rules, burst/outstanding/timeout bounds, ordering and error policy,
scoreboard keys, required coverage bins, formal properties, result traces, and
intended targets.

Accepted transaction traces use `protocol-trace-v1.schema.json` and can be
reconciled independently with `dv-enterprise verify-protocol-trace --input
TRACE.json`. The shared reference models enforce burst boundaries and lengths,
AXI IDs/last beats, packet framing/routing/masks, Wishbone response exclusivity,
Avalon pending responses, AHB accepted transfers, and TileLink source matching.

Recognition is deterministic and fail-closed. A match requires every mandatory
signal with compatible endpoint directions. Flat canonical signals may share
one explicit prefix. Non-standard names require an explicit one-to-one alias
map. Multiple instances require an explicit instance identity or alias map;
partial and direction-ambiguous signatures are not inferred from approximate
names. SystemVerilog interface/modport facts remain available in normalized RTL
evidence and must be resolved to explicit member aliases before profile binding.

The contract and recognition layer are implemented. This does not qualify the
new broad protocols for execution: their drivers, monitors, reference models,
scoreboards, coverage, formal properties, native benches, result decoders, UVM
agents, mutation matrices, and external-design evidence remain required before
their generation state can advance beyond `unsupported`. Existing bounded
AXI4-Lite, APB4, AHB-Lite, and paired ready/valid qualification is unchanged.
