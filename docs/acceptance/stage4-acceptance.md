# Stage 4 Verification-Depth Acceptance

Snapshot date: 2026-07-21.

Stage 4 is complete for the bounded profiles below. “Complete” means every
roadmap item has a deterministic implementation and an explicit fail-closed
boundary; it does not broaden a bounded profile into general RTL sign-off.

| Roadmap item | Implemented qualification | Acceptance evidence |
| --- | --- | --- |
| Pulse/toggle/handshake synchronizers | Two-flop, pulse-stretch, toggle, and round-trip request/acknowledge policies with ordered observable stages | Generated cocotb/formal good-DUT and four-mutant matrices, trace closure, non-vacuity, deterministic bytes |
| Async FIFOs and Gray pointers | Power-of-two, dual-clock bounded FIFO with normalized storage/access facts and two ordered Gray synchronizers | Queue scoreboard, formal pointer/flag properties, seven simulation and five formal mutants |
| Reset-domain dependencies and RDC | Observable asynchronous assertion, ordered release, acyclic dependencies, two-stage ready crossing, bounded recovery/removal intent | Generated cocotb/formal good-DUT and six-mutant matrices |
| Memory semantics | Bounded synchronous byte-addressable SRAM with byte enables, collision policy, two-requester round-robin arbitration, zero initialization, and parity | Exhaustive scoreboard, bounded formal reference word, eight-mutant simulation/formal matrices |
| Assumptions, invariants, and liveness | Property-specific pulse assumption, causal bounded response, induction state/design invariants, and assumption-consistency covers | Real induction proof plus four formal mutants and non-vacuity covers |
| Parameter sweeps | Per-point identities plus coverage-schema-v3 semantic cross-point aggregation | Real WIDTH=4/WIDTH=9 analyze-to-CI pipeline and incomplete-cross-point negative tests |
| VHDL normalization | VHDL-only entity/generic/architecture/process normalization with generic sweeps and source evidence | Parser fail-closed tests and deterministic analyze-to-VHDL-generation CLI acceptance |

The detailed contracts are documented in the linked acceptance documents from
the project README. General CDC/RDC/memory structures, inferred formal
environments, implicit parameter products, mixed-language elaboration, and VHDL
execution remain later-stage capabilities and are never reported as supported.
