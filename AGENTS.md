# OpenROAD workflow

This is an ASIC physical-design tool. OpenROAD/OpenSTA are the implementation and timing backend.
The approved SKY130 sign-off workflow also uses Yosys equivalence and Magic/KLayout/Netgen verification.
Do not restore proprietary implementation or FPGA/board adapters.

- Start with `rg` or the local code graph; read only the files needed for the task.
- Prefix shell commands with `rtk`; use `rtk proxy` for unfiltered output.
- Preserve `.code-review-graph/`, RTK instructions, Headroom integration, and their tests. They reduce model context and tokens.
- Never print `.env` or API credentials. The local application key is named `API_KEY`.
- Keep AI context bounded; retain evidence IDs and immutable timing requirements when compressing prompts.

## Code map

- `src/dv_platform/physical_design.py` and `.tcl`: project validation, fixed native repair commands, metrics, acceptance rules.
- `src/dv_platform/ai/physical_design.py`: evidence-based repair proposals using measured gaps and iteration history.
- `src/dv_platform/enterprise/physical_design.py`: native OpenROAD execution, independent OpenSTA replay, bounded iteration and artifacts.
- `src/dv_platform/ai/`: provider gateway, signed routing, Headroom, local code graph.
- `src/dv_platform/{product,entitlement,signing}.py` and `infrastructure/`: entitlement, signature, plugin, audit, and credential boundaries.
- `scripts/qualification/openroad*.py`: native qualification and independent equivalence checking.
- `src/dv_platform/{sky130,signoff,release}.py` and `enterprise/{timing,equivalence,layout,power,signoff,cpu}.py`: pinned v2 CPU preparation, complete timing replay, native verification, and independently approved releases.
- `scripts/qualification/sky130*.py` and `docs/sky130-signoff.md`: reproducible SKY130 provisioning and qualification.
- `qualification/evidence/PHYS-01/`: current local Luna execution records and their digest-bound artifacts.

## Checks

Use `make check` for lint, formatting, typing, and portable repository checks; `make test` for tests. Use `make verify-evidence` to require every retained local artifact and verify all hashes. See `docs/verification.md` for native qualification.
Preserve the pinned source fixture in `.dv-platform/openroad-live/fixture/`. Do not change retained evidence artifacts: their SHA-256 hashes are checked.
Timing closure is measured against the original constraints. It does not grant sign-off approval.
