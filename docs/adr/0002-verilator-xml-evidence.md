# 0002: Verilator XML as RTL Evidence Source

## Status

Accepted

## Context

For Verilog and SystemVerilog, generated verification collateral must be backed
by structural RTL evidence rather than fragile source-text parsing or unchecked
natural-language analysis.

## Decision

Stage 2 standardizes on Verilator XML output generated with `--xml-only`.

Raw Verilator XML artifacts are persisted under the configured work directory
and treated as source evidence artifacts. The platform writes a separate
normalized RTL facts JSON containing only platform-owned facts required by
planning, claim-checking, and early generators.

The normalized facts must include stable evidence locators back to the raw XML
artifact. The CLI records the detected Verilator version with AST artifacts.
Stage 2 supports a documented minimum Verilator version; version-specific
compatibility adapters are deferred until fixtures show incompatible XML
shapes.

## Consequences

The raw AST remains available for debugging and re-normalization, while the
platform consumes a smaller stable schema. Multi-version support is evidence
driven instead of speculative.
