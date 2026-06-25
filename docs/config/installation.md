# Installation

The CLI is a Python package, but RTL analysis and simulation also require EDA
executables installed on the host.

## Python Package

Install the CLI package from the repository:

```bash
python3 -m pip install -e .
```

Python package dependencies are declared in `pyproject.toml`.

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
