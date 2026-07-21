# Installation

The CLI is a Python package, but RTL analysis and simulation also require EDA
executables installed on the host.

## Python Package

Create a project-local uv environment and install the CLI package plus Python
dependencies:

```bash
uv sync
```

Run the CLI through the uv environment:

```bash
uv run dv-platform --help
```

The installed package also supports module execution:

```bash
uv run python -m dv_platform --help
```

For direct installation into an isolated environment:

```bash
python -m pip install .
dv-platform --help
```

Python package dependencies are declared in `pyproject.toml`; resolved versions
are locked in `uv.lock`.

The deterministic installation does not include an AI SDK. Install the optional
planning integration only when needed:

```bash
uv sync --extra ai
# or: python -m pip install 'dv-platform[ai]'
```

This installs LiteLLM. Provider API accounts, API billing, and credentials are
bring-your-own; consumer ChatGPT, Claude, or Gemini subscriptions and
interactive OAuth are not used by the CLI.

Live provider smoke tests are opt-in and excluded from standard test runs. Set
`DV_PLATFORM_AI_SMOKE=1` plus one or more model variables such as
`DV_PLATFORM_AI_SMOKE_OPENAI_MODEL`,
`DV_PLATFORM_AI_SMOKE_ANTHROPIC_MODEL`,
`DV_PLATFORM_AI_SMOKE_GEMINI_MODEL`,
`DV_PLATFORM_AI_SMOKE_DEEPSEEK_MODEL`,
`DV_PLATFORM_AI_SMOKE_MOONSHOT_MODEL`, or
`DV_PLATFORM_AI_SMOKE_OLLAMA_MODEL`, then run:

```bash
uv run --extra ai python -m unittest tests.test_ai_smoke
```

## System Tools

Install the current simulation and RTL-analysis dependencies:

```bash
sudo apt-get install verilator iverilog yosys z3
```

Tool usage:

- `verilator`: required for `dv-platform analyze-rtl` to produce Verilator XML
- `slang`: required when `[rtl].semantic_crosscheck` is `report` or `required`;
  the qualified CI pairing is Slang 11 with Verilator 5
  RTL facts.
- `iverilog`: required for the cocotb/Icarus simulation path once generated
  cocotb tests are run.
- `sby`: required for `dv-platform run --target formal`.
- `yosys`: required by SymbiYosys for formal elaboration and proof setup.
- `z3` or another supported SMT solver: required by the SymbiYosys `smtbmc`
  engine.

Many Linux package repositories do not ship a complete, current SymbiYosys
stack. For local development, the OSS CAD Suite provides `sby`, `yosys`, and
SMT solvers in one toolchain. After extracting it, place its `bin` directory on
`PATH` before running formal commands:

```bash
export PATH="$HOME/.local/opt/oss-cad-suite/oss-cad-suite/bin:$PATH"
```

The test suite includes real-tool integration tests:

- The Verilator integration test skips when `verilator` is unavailable.
- The Slang integration test skips locally when either frontend is unavailable.
  Set `DV_PLATFORM_QUALIFIED_SLANG_CI=1` in the qualified job to make both tools
  and a passing strict cross-check mandatory.
- The SymbiYosys integration test skips unless both `sby` and `verilator` are
  available. It checks `PATH` first and then known local OSS CAD Suite
  extraction paths under `$HOME/.local/opt`.

Hosted CI additionally installs a pinned SymbiYosys source revision and treats
the formal integration test as mandatory. The explicit test step prevents a
missing hosted toolchain from being reported as a successful skip.

## Project Configuration

The default Verilator executable is:

```toml
[rtl]
verilator_executable = "verilator"
slang_executable = "slang"
semantic_crosscheck = "report"
```

For cocotb simulation with Icarus:

```toml
[[simulators]]
target = "cocotb"
name = "icarus"
command = "iverilog"
```

For formal execution with SymbiYosys:

```toml
[[formal_tools]]
name = "symbiyosys"
command = "sby"
```
