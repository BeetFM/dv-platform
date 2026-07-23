# Stage 10 external-design semantic qualification

Two unrelated, pinned open-source designs were elaborated by Verilator 5.020, normalized independently by Slang 11.0, and elaborated to UHDM by Surelog 1.86. Required design-unit, specialization, port/width, parameter, type, and hierarchy facts reconciled exactly.

The records are content-free and bind the upstream repository, commit, selected inputs, license, frontend artifacts, versions, and comparison outcome by SHA-256:

- `external-designs/picorv32-v1.json`
- `external-designs/ibex-counter-v1.json`

The extended comparison also retained five PicoRV32 and six Ibex representation gaps in assignments, procedures, expressions, branches, control domains, and generated scopes as warnings. These fields remain strict-generation blockers when selected as required capabilities; they were not silently merged or promoted into primary facts.

Reproduce with `dv-enterprise qualify-external-design` and verify the resulting records with `dv-enterprise verify-evidence`.
