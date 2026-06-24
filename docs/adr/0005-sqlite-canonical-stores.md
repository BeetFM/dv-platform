# 0005: SQLite Canonical Stores With Derived Views

## Status

Accepted

## Context

Humans should review generated plans and reports in readable formats, but
generators and CI need efficient, queryable, deterministic machine state.

## Decision

Use SQLite as the canonical machine store for generated verification plans and
design review findings.

Verification plans are stored under `<work-dir>/plans/plans.sqlite`. Derived
Markdown review files are generated under `<work-dir>/plans/modules/`, with an
index view under `<work-dir>/plans/`.

Design review findings are stored under `<work-dir>/review/review.sqlite`.
Markdown is the primary human view. YAML and JSON are exported for CI/CD and
automation: YAML is optimized for human-readable pipeline artifacts and policy
review, while JSON remains the strict machine/API export. SARIF is exported
only for findings that map cleanly to source locations and rule concepts.

All design review findings are retained in SQLite. Low-confidence and
unknown-confidence findings are hidden from default Markdown, YAML, and JSON
reports unless severity is high or critical. Findings without evidence are not
presented as firm recommendations.

Canonical records avoid wall-clock timestamps unless explicitly needed. Input
hashes, schema versions, and tool versions are preferred for reproducibility.

## Consequences

Downstream tools get efficient indexed access without parsing prose. Human
review remains readable through derived Markdown. CI can choose YAML or JSON
depending on whether the consumer is a person or strict automation.
