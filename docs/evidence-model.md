# Evidence and Claim Model

The platform represents planner, checker, and reviewer conclusions as explicit
claims. Claims are validated before generated collateral depends on them.

## Claim Fields

Each `VerificationClaim` records:

- `claim_id`: stable claim identifier within a plan or report
- `scope`: module, interface, or report scope
- `statement`: human-readable claim
- `claim_type`: one of `rtl_structure`, `rtl_behavior`, `documentation_intent`,
  `planned_check`, or `design_recommendation`
- `severity`: `info`, `low`, `medium`, `high`, or `critical`
- `generation_precondition`: whether executable generated behavior depends on
  the claim
- `status`: current validation state
- `evidence_refs`: source-backed evidence references

## Statuses

Claim statuses are:

- `unchecked`: not validated yet
- `supported`: required evidence exists and matches the claim
- `contradicted`: deterministic evidence contradicts the claim
- `missing_evidence`: required evidence is absent or unavailable

Automatic contradiction is reserved for deterministic mismatches. Heuristic
concerns should be represented as warnings, suspected conflicts, or open
questions.

## Evidence References

`EvidenceRef` identifies the source backing a claim:

- `kind`: `verilator_ast`, `document_chunk`, `tool_log`, or
  `generated_artifact`
- `source_id`: source artifact path or stable source identifier
- `locator`: platform-owned locator inside the source artifact
- `summary`: optional human-readable summary

Verilator XML locators include fact categories and source locations when
available. Documentation requirement locators use chunk IDs plus exact sentence
offsets, so deduplicated requirements can retain every precise source occurrence.

Executable artifacts add an `ArtifactTrace` layer. Each generated symbol maps
back to plan check indexes, requirement IDs, RTL behavior IDs, claim IDs, and
evidence refs. Generation rejects executable artifacts without this mapping;
run summaries use it for generated-symbol execution coverage, triage, and
failed-result feedback. A symbol result is not an independent result for every
plan record mapped to that symbol.

## Checkers

The current deterministic checkers validate whether a claim has evidence of the
required kind:

- `check_ast_claim`: requires `verilator_ast` evidence
- `check_documentation_claim`: requires `document_chunk` evidence

If matching evidence is present and available, the claim becomes `supported`.
If no required evidence is present or available, the claim becomes
`missing_evidence`. If a source is explicitly marked contradicted, the claim
becomes `contradicted`.

## Generation Gating

Generation gating follows ADR-0004:

- Supported claims allow generation.
- Critical unsupported, unchecked, missing, or contradicted claims block.
- Semantic-construct support is evaluated against each requested target; a
  case statement or internal memory may be safe for an exercised black-box
  cocotb/formal path while remaining blocked for an unsupported target.
- Elaborated parameters, control domains, hierarchy connections, and protocol
  channels remain structured plan facts rather than prose-only assumptions.
- High-severity contradicted claims block.
- High-severity missing or unchecked claims warn locally and block in strict or
  CI mode.
- Medium claims warn by default.
- Medium generation preconditions block until supported.
- Low and info claims are annotated by default, except contradicted claims warn.

`gate_generation` returns an aggregate decision containing all validations,
blocked validations, warnings, and whether generation is allowed.

## Reports

Claim reports can be emitted as:

- JSON for CI and automation
- Markdown for human review

The current report filenames are `claims.json` and `claims.md` when written via
`write_claim_reports`.
