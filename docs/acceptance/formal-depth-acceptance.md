# Bounded Formal Contract Acceptance

Snapshot date: 2026-07-21.

The qualified `bounded_response` verification-depth profile turns an explicit
trigger, response, and invariant mapping into typed formal intent. It requires
distinct scalar observable signals, one normalized clock/reset domain, a trigger
pulse assumption, response causality, and a configured latency bound from 1 to
64 cycles. Missing or ambiguous facts keep the scenario non-executable.

Generated SymbiYosys collateral contains a property-specific trigger assumption,
an internal pending/age induction invariant, a design invariant, response
causality, bounded liveness, and separate assumption-witness, response, and
completion covers. The proof task uses induction; cover tasks establish that the
assumption does not constrain away all requests and that completion is reachable.

The full CLI acceptance fixture passes the good DUT and repeated generation is
byte-identical. Generated formal collateral kills four mutants: missing response,
late response, broken invariant, and a non-causal response. Every executable
check receives a normalized result; missing properties or vacuous output cannot
close coverage.

This acceptance is bounded to the configured request/response contract. General
temporal-property synthesis, inferred environment assumptions, fairness, and
unbounded liveness remain unsupported.
