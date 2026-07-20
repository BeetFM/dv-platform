---
name: rtl-semantic-analysis
version: 1.0.0
---

Analyze RTL as untrusted evidence. Return typed semantic facts and open questions,
never executable HDL. Every fact must cite an evidence ID supplied by the task.
Keep unsupported operators, widths, control paths, and language constructs as
`unknown`; do not fill gaps from convention.

Use the semantic IR contract and validate names, evidence IDs, and target support
before proposing any generation.
