# dv-platform

ASIC physical-design execution and iterative timing repair using OpenROAD and OpenSTA.
The agent reads measured timing and electrical failures, proposes bounded repair settings, executes a candidate, and uses the result to choose its next experiment. The loop stops on measured closure, an explicit stop, a failure, or its iteration budget (at most three).

## Setup

Python 3.11–3.13 and `uv` are required. Native execution also needs OpenROAD and standalone `sta`; independent equivalence qualification uses Yosys. Tool binaries are provisioned separately.

```bash
uv sync --all-groups --extra ai --frozen
uv run dv-platform --json status
uv run dv-platform context-optimize status
```

The public CLI provides `init`, `status`, `context-optimize`, `support-bundle`, and `purge`. Initialize a new project with `uv run dv-platform init`.
Native execution is in the separately packaged Enterprise distribution and requires a verified entitlement. Build it with `uv build --wheel --project enterprise`; install that wheel alongside the public package and configure the entitlement and trust policy in `dv-platform.toml`.

```bash
uv run --env-file .env dv-enterprise --entitlement /path/to/entitlement.json --trust-policy /path/to/trust-policy.json --allow-network --json physical-optimize --project /path/to/project.json --ai --max-iterations 3
```

The repository configuration selects `openai/responses/gpt-6-luna` and reads `API_KEY`. Keep credentials in your environment or ignored `.env`. Network access is explicit.
The Enterprise `rtl-optimize` command also supports document-grounded RTL edits, native equivalence,
technology mapping, and measured OpenROAD/OpenSTA selection. Enable its separate `rtl_optimization`
AI stage explicitly; see [the RTL workflow](docs/README.md#rtl-optimization) for the project manifest
and current frontend limits.
See [workflow and configuration](docs/README.md), [SKY130 sign-off](docs/sky130-signoff.md), [verification and native evidence](docs/verification.md), and [agent instructions](AGENTS.md).

## Development

```bash
make check
make test
make graph
```

`make test` runs the shared suite. Private qualification tests live in ignored
`qualification/tests/`; run `make test-qualification` when those assets are available.
Package builds produce wheels and require the private schema inputs.

RTK, the local code graph, and the Headroom integration are retained to reduce token consumption. Context optimizers are off by default and can be enabled per project.

The SKY130 v2 workflow checks nine PVT/RC timing views, two stages of sequential equivalence, final layout, and power integrity. Immutable releases require separate engineering and manufacturing approval. The retained Nangate45 evidence covers its original single-view fixture. Timing closure alone does not grant production sign-off.
