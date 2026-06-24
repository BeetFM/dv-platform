# 0004: Claim Validation and Generation Gating

## Status

Accepted

## Context

Agents and deterministic planners will produce conclusions about RTL structure,
behavior, documentation intent, planned checks, and recommendations. Generated
artifacts must not silently depend on unsupported or contradicted assumptions.

## Decision

Critical claims block generation when missing evidence, contradicted, or
unchecked. High-severity contradicted claims block generation. High-severity
missing or unchecked claims warn during local exploratory use and block in
strict or CI mode.

Medium claims warn by default, but may block when they are explicit generation
preconditions. Low and info claims are annotated or warned without blocking by
default.

Claims that directly affect executable generated behavior are generation
preconditions. Critical preconditions must be supported before generation.
Missing documentation intent produces open questions instead of invented
requirements.

Automatic `contradicted` status requires deterministic evidence mismatch.
Heuristic or confidence-based conflicts are represented as warnings, open
questions, or suspected conflicts, and must not automatically block generation
without explicit evidence.

## Consequences

Local exploration remains possible while CI is conservative. The distinction
between deterministic contradiction and heuristic suspicion keeps failures
explainable and reduces false blockers.
