# Slang compatibility matrix

The qualified semantic cross-check profile is **Verilator 5 / Slang 11** on
Linux x86-64. Hosted quality CI downloads the official Slang 11.0 archive,
verifies SHA-256
`951a170e10e25e54c91565030acfdfc11c3226714ebf225a18ad4166a898d8a4`,
and runs the matrix with `DV_PLATFORM_QUALIFIED_SLANG_CI=1`.

| Fixture profile | Slang normalization | Cross-frontend result |
| --- | --- | --- |
| Empty structural module | Complete | Passes strict comparison |
| Arithmetic, casts, conditional, `casez`, sync/async reset | Complete | Differences in frontend lowering are reported per field |
| Immediate and concurrent assert/cover | Complete | Verilator-lowered or unavailable property structure fails closed |
| Sequence delay (`##`) | Complete in Slang | Verilator 5 rejects compilation; the workflow fails before generation |
| Enum, nested packed structs, package import, interface array, two modports | Complete | Equivalent layouts compare; lowered expressions remain explicit issues |
| Parameterized hierarchy, loop/conditional generate, memories | Complete | Stable hierarchy is retained; unavailable generate conditions remain explicit issues |
| Inactive conditional generate sweep | Retained as `selected=false` | Cannot disappear as a successful empty comparison |

Unknown expression, branch, property, type, hierarchy, or generate nodes
withdraw the affected capability. Because the qualified profile requires every
declared capability, strict/CI and `required` mode reject that run.

## Qualification budgets

The normalizer uses an iterative document walk rather than recursively
materializing a tuple for every subtree. The regression benchmark normalizes a
synthetic AST with more than 10,000 JSON objects under these per-process limits:

- elapsed time below 5 seconds;
- peak Python allocation below 64 MiB.

The fixture is intentionally small enough for ordinary unit CI. Repository-scale
multi-million-node measurements remain a separate system benchmark.
