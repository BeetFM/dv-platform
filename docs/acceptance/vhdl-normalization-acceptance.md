# Bounded VHDL Normalization Acceptance

Snapshot date: 2026-07-21.

VHDL-only projects have a deterministic source normalizer for one unambiguous
architecture per selected entity. The qualified interface subset includes
integer, natural, and positive generics; numeric overrides and explicit
sweeps; scalar logic/bit/boolean ports; constrained `std_logic_vector`,
`std_ulogic_vector`, `signed`, and `unsigned` ports; and generic-dependent `to`
or `downto` ranges.

Normalized facts retain entity and architecture identity, specialization hash,
generic values, port directions/types/widths, source locations, VHDL-source
evidence, edge-derived clocks, named resets, process facts, asynchronous reset
ownership, simple reset/increment patterns, and concurrent assignments. The
facts round-trip through RTL-facts schema v10 and drive conservative VHDL
planning and deterministic collateral generation without invoking Verilator.

The CLI acceptance analyzes two generic sweep points, plans both entity
specializations, generates byte-identical GHDL-valid VHDL collateral on
repetition, and preserves the original entity in each DUT binding. A separate
observable reset fixture completes analyze, plan, generate, GHDL 4.1.0
analyze/elaborate/run, coverage ingestion, and CI status with one exact
normalized per-check result. Unknown generic overrides,
missing architectures, multiple ambiguous architectures, unresolved expressions,
and unconstrained or unsupported interface types fail closed. Required Slang
cross-check mode also fails closed because the qualified Slang adapter is
SystemVerilog-only.

This accepts bounded normalization and the observable reset execution slice, not
general VHDL sign-off. Mixed-language binding is explicitly rejected, scenarios
outside the registered reset renderer remain scaffolded or unsupported, and
packages, records, subtypes, generate elaboration, and broader behavioral
semantics remain open.
