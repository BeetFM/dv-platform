#!/usr/bin/env python3
"""Execute one generated ready/valid UVM project with Vivado Simulator."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from dv_platform.qualification_assets.vivado_xsim_runner import _resolve_tools, _run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vivado-bin", type=Path, required=True)
    parser.add_argument("--cmd-exe", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("generated_dir", type=Path)
    args = parser.parse_args(argv)
    generated = args.generated_dir.resolve()
    manifest = json.loads((generated / "execution-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("target") != "uvm":
        raise SystemExit("execution manifest is not a UVM project")
    module = str(manifest["module"])
    project = manifest["project"]
    rtl = tuple(str(Path(item["path"]).resolve()) for item in project["hdl_files"] if item["language"] != "vhdl")
    generated_sv = tuple(
        str((generated / item["path"]).resolve())
        for item in manifest["generated_files"]
        if str(item["path"]).endswith(".sv")
    )
    interface = tuple(path for path in generated_sv if path.endswith("_if.sv"))
    package = tuple(path for path in generated_sv if path.endswith("_pkg.sv"))
    top_source = tuple(path for path in generated_sv if Path(path).name.startswith("tb_"))
    if len(interface) != 1 or len(package) != 1 or len(top_source) != 1 or not rtl:
        raise SystemExit("generated UVM project has incomplete interface/package/RTL/top sources")
    tools = _resolve_tools(args.vivado_bin, windows=args.cmd_exe is not None)
    top = f"tb_{module}_uvm"
    result = _run_pipeline(
        tools,
        generated,
        (*interface, *package, *rtl, *top_source),
        top,
        f"veriforge_{module}_snapshot",
        args.cmd_exe,
        args.timeout_seconds,
        uvm=True,
    )
    print(result.output)
    passed = result.return_code == 0 and _project_passed(result.output, module)
    for trace_id in _trace_ids(manifest):
        status = "passed" if passed else "failed"
        print(f'DV_PLATFORM_RESULT_V1 {{"trace_id":"{trace_id}","status":"{status}"}}')
    return 0 if passed else (result.return_code or 1)


def _project_passed(output: str, module: str) -> bool:
    return all(
        (
            f"Running test {module}_test" in output,
            re.search(r"UVM_ERROR\s*:\s*0\b", output) is not None,
            re.search(r"UVM_FATAL\s*:\s*0\b", output) is not None,
            "no transactions were compared" not in output.lower(),
        )
    )


def _trace_ids(manifest: dict[str, object]) -> tuple[str, ...]:
    generated = manifest.get("generated_files", ())
    if not isinstance(generated, list):
        return ()
    traces: list[str] = []
    for item in generated:
        if not isinstance(item, dict):
            continue
        values = item.get("trace_ids", ())
        if not isinstance(values, list):
            continue
        traces.extend(value for value in values if isinstance(value, str) and value)
    return tuple(dict.fromkeys(traces))


if __name__ == "__main__":
    raise SystemExit(main())
