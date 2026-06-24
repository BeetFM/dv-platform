# 0006: Requirements-Driven Generation Targets

## Status

Accepted

## Context

The platform must generate based on client requirements. Cocotb is useful for
early validation, but the architecture must also support SystemVerilog,
standard Verilog, UVM, VHDL, and formal targets.

## Decision

Generation targets are selected from client requirements, verification plans,
and project configuration. Cocotb may be the first implemented simulation
backend because it is fast to validate, but it is not the assumed product
direction.

Simulation generation must support target-specific output roots:
`<output-dir>/simulation/<target>/modules/<module>/`.

Runtime state, logs, temporary build products, and failure summaries live under
`<work-dir>/runs/simulation/<target>/<module>/`.

Simulator configuration is target-specific and project-specific. If no
simulator is configured, `generate` may still emit artifacts, but `run` fails
with an actionable message. Strict and CI mode require explicit simulator
configuration. No global client-project simulator is assumed.

Every generated target/module directory includes a provenance manifest tying
files back to plan IDs, claim IDs, and evidence refs.

## Consequences

The first backend can be implemented pragmatically without constraining client
target choice. Generated source and runtime state stay separated, and execution
requirements are explicit.
