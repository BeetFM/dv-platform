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

Python package dependencies are declared in `pyproject.toml`; resolved versions
are locked in `uv.lock`.

## System Tools

Install the current system tool dependencies:

```bash
sudo apt-get install verilator iverilog
```

Tool usage:

- `verilator`: required for `dv-platform analyze-rtl` to produce Verilator XML
  RTL facts.
- `iverilog`: required for the cocotb/Icarus simulation path once generated
  cocotb tests are run.

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
