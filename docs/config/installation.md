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

## System Tools

Install the current simulation and RTL-analysis dependencies:

```bash
sudo apt-get install verilator iverilog
```

Tool usage:

- `verilator`: required for `dv-platform analyze-rtl` to produce Verilator XML
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

The test suite includes optional real-tool integration tests:

- The Verilator integration test skips when `verilator` is unavailable.
- The SymbiYosys integration test skips unless both `sby` and `verilator` are
  available. It checks `PATH` first and then known local OSS CAD Suite
  extraction paths under `$HOME/.local/opt`.

## Project Configuration

The default Verilator executable is:

```toml
[rtl]
verilator_executable = "verilator"
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
