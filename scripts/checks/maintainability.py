"""Report and enforce bounded implementation units and package dependencies."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src" / "dv_platform"
TEMPLATE_ROOT = SOURCE_ROOT / "generation" / "templates"
ACYCLIC_PACKAGES = {
    "ai",
    "configuration",
    "documentation",
    "domain",
    "execution",
    "formal",
    "generation",
    "infrastructure",
    "rtl",
    "verification",
}
BOUNDED_PACKAGES = ACYCLIC_PACKAGES | {"cli_handlers", "enterprise", "generators", "qualification_assets"}
MAX_MODULE_LINES = 700
MAX_FUNCTION_LINES = 75
MAX_COMPLEXITY = 12
RENDER_TARGETS = ("cocotb", "formal", "systemverilog", "uvm", "verilog", "vhdl")
MODULE_EXCEPTIONS = {
    "src/dv_platform/documentation/indexing.py": (
        "compatibility-sensitive local indexing subsystem whose public formats and atomic store implementations "
        "are intentionally kept together"
    ),
    "src/dv_platform/domain/models.py": (
        "declarative compatibility catalog; kept indivisible so legacy pickle class identities remain stable"
    ),
    "src/dv_platform/verification/protocols/profiles.py": (
        "declarative protocol and register profile catalog with stable legacy class identities"
    ),
}
FUNCTION_EXCEPTIONS = {
    ("src/dv_platform/enterprise/benchmark.py", "run_qualification_benchmark"): (
        "indivisible qualification transaction that owns resource sampling and evidence finalization"
    ),
    ("src/dv_platform/enterprise/cli.py", "build_parser"): (
        "indivisible declarative enterprise argparse command and option catalog"
    ),
    ("src/dv_platform/ai/code_graph.py", "_read_message"): (
        "bounded JSON-RPC message decoder whose branches correspond to mutually exclusive framing failures"
    ),
    ("src/dv_platform/execution/scheduler.py", "run_ordered"): (
        "single scheduler safety transaction covering cancellation, process cleanup, and deterministic result ordering"
    ),
    ("src/dv_platform/cli_handlers/parser.py", "build_parser"): (
        "indivisible declarative argparse command and option catalog"
    ),
    ("src/dv_platform/cli_handlers/dispatch.py", "_load_command_dependencies"): (
        "declarative lazy-import compatibility wiring catalog"
    ),
    ("src/dv_platform/verification/protocols/profiles.py", "production_protocol_profiles"): (
        "indivisible static protocol-profile catalog"
    ),
    ("src/dv_platform/verification/protocols/profiles.py", "_additional_production_profiles"): (
        "indivisible static protocol-profile catalog"
    ),
    ("src/dv_platform/verification/planning/targets.py", "_built_in_registry"): (
        "indivisible declarative target-capability registry"
    ),
    ("src/dv_platform/verification/storage/plan_markdown.py", "_write_module_markdown"): (
        "indivisible static compatibility view whose byte layout is persisted"
    ),
    ("src/dv_platform/configuration/serialization.py", "write_config"): (
        "indivisible declarative TOML compatibility projection"
    ),
    ("src/dv_platform/verification/storage/plan_codec.py", "_plan_to_json"): (
        "indivisible declarative persisted-plan schema projection"
    ),
    ("src/dv_platform/verification/storage/plan_codec.py", "_migrate_plan_json"): (
        "indivisible declarative persisted-schema migration table"
    ),
    ("src/dv_platform/ai/proposals/validation.py", "proposal_json_schema"): (
        "indivisible declarative provider response schema"
    ),
    ("src/dv_platform/rtl/verilator/persistence.py", "write_rtl_facts_summary"): (
        "indivisible static normalized-facts compatibility view"
    ),
    ("src/dv_platform/rtl/verilator/normalization.py", "write_normalized_rtl_facts"): (
        "indivisible declarative normalized RTL-facts schema projection"
    ),
    ("src/dv_platform/formal/generation/contracts.py", "_async_fifo_assertions"): (
        "indivisible static asynchronous-FIFO assertion template"
    ),
    ("src/dv_platform/formal/generation/contracts.py", "_cdc_assertions"): (
        "indivisible static CDC assertion template"
    ),
    ("src/dv_platform/formal/generation/cdc.py", "_cdc_scheme_assertions"): (
        "indivisible static scheme-specific CDC assertion template"
    ),
    ("src/dv_platform/formal/generation/cdc.py", "_reconvergent_cdc_assertions"): (
        "indivisible static bounded reconvergent-CDC assertion template"
    ),
    ("src/dv_platform/formal/generation/memory.py", "_bounded_sram_assertions"): (
        "indivisible static bounded-SRAM assertion template"
    ),
    ("src/dv_platform/formal/generation/sby.py", "_quality_requirements"): (
        "indivisible declarative proof-quality requirement catalog"
    ),
    ("src/dv_platform/verification/scenarios/reset.py", "_reset_scenarios"): (
        "indivisible declarative reset scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/apb.py", "_apb4_scenarios"): (
        "indivisible declarative APB scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/axi.py", "_axi4_lite_scenarios"): (
        "indivisible declarative AXI4-Lite scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/ahb.py", "_ahb_lite_scenarios"): (
        "indivisible declarative AHB-Lite scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/peripheral.py", "_peripheral_scenarios"): (
        "indivisible declarative peripheral scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/memory.py", "_memory_scenarios"): (
        "indivisible declarative memory scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/cdc.py", "_cdc_scenarios"): (
        "indivisible declarative CDC scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/cdc.py", "_async_fifo_scenarios"): (
        "indivisible declarative asynchronous-FIFO scenario catalog"
    ),
    ("src/dv_platform/verification/scenarios/cdc.py", "_reconvergent_cdc_scenarios"): (
        "indivisible declarative reconvergent-CDC scenario catalog"
    ),
    ("src/dv_platform/generators/cocotb/support.py", "_quality_requirements"): (
        "indivisible declarative generated-artifact qualification catalog"
    ),
    ("src/dv_platform/generators/cocotb/support.py", "_ready_valid_test_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/memories.py", "cocotb_memory_scenario_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/resets.py", "cocotb_reset_scenario_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/cdc.py", "_async_fifo_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/cdc.py", "_cocotb_cdc_scenario"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/peripherals.py", "_cocotb_uart_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/peripherals.py", "_cocotb_spi_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/peripherals.py", "_cocotb_i2c_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/peripherals.py", "_cocotb_gpio_timer_interrupt_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/peripherals.py", "formal_peripheral_assertions"): (
        "indivisible byte-stable formal compatibility template"
    ),
    ("src/dv_platform/generators/protocols/common.py", "cocotb_profile_scenario_lines"): (
        "indivisible byte-stable cocotb compatibility template"
    ),
    ("src/dv_platform/generators/protocols/cocotb.py", "cocotb_apb4_scenario_lines"): (
        "indivisible byte-stable cocotb APB compatibility template"
    ),
    ("src/dv_platform/generators/protocols/cocotb.py", "cocotb_axi4_lite_scenario_lines"): (
        "indivisible byte-stable cocotb AXI compatibility template"
    ),
    ("src/dv_platform/generators/protocols/cocotb.py", "cocotb_ahb_lite_scenario_lines"): (
        "indivisible byte-stable cocotb AHB compatibility template"
    ),
    ("src/dv_platform/generators/protocols/formal_standard.py", "formal_ahb_lite_assertions"): (
        "indivisible byte-stable formal AHB compatibility template"
    ),
    ("src/dv_platform/generators/protocols/formal_standard.py", "formal_axi4_lite_assertions"): (
        "indivisible byte-stable formal AXI compatibility template"
    ),
    ("src/dv_platform/generators/protocols/formal_standard.py", "formal_apb4_assertions"): (
        "indivisible byte-stable formal APB compatibility template"
    ),
    ("src/dv_platform/generators/artifacts/__init__.py", "_execution_manifest_artifact"): (
        "indivisible declarative execution-manifest compatibility projection"
    ),
    ("src/dv_platform/enterprise/semantics/modules.py", "_module"): (
        "indivisible declarative external semantic-module schema projection"
    ),
}


@dataclass(frozen=True)
class FunctionMetric:
    path: str
    name: str
    line: int
    code_lines: int
    complexity: int
    digest: str


def _python_files() -> tuple[Path, ...]:
    return tuple(sorted(SOURCE_ROOT.rglob("*.py")))


def _template_files() -> tuple[Path, ...]:
    return tuple(sorted(TEMPLATE_ROOT.rglob("*.j2")))


def _code_lines(path: Path) -> set[int]:
    with path.open("rb") as source:
        tokens = tokenize.tokenize(source.readline)
        return {
            token.start[0]
            for token in tokens
            if token.type
            not in {
                tokenize.COMMENT,
                tokenize.DEDENT,
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.NL,
                tokenize.NEWLINE,
            }
            and token.string.strip()
        }


def _complexity(node: ast.AST) -> int:
    branches = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.Match,
    )
    score = 1
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, branches):
            score += 1
        elif isinstance(child, ast.ExceptHandler):
            score += 1
    return score


def _function_metrics(path: Path, tree: ast.AST, lines: set[int]) -> tuple[FunctionMetric, ...]:
    relative = path.relative_to(ROOT).as_posix()
    metrics = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        end_line = node.end_lineno or node.lineno
        body = ast.dump(node, annotate_fields=True, include_attributes=False)
        metrics.append(
            FunctionMetric(
                relative,
                node.name,
                node.lineno,
                sum(node.lineno <= line <= end_line for line in lines),
                _complexity(node),
                hashlib.sha256(body.encode()).hexdigest(),
            )
        )
    return tuple(metrics)


def _package(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def _dependencies(path: Path, tree: ast.AST) -> set[str]:
    result = set()
    for node in ast.walk(tree):
        module = node.module if isinstance(node, ast.ImportFrom) else None
        names = (alias.name for alias in node.names) if isinstance(node, ast.Import) else ()
        candidates = (module,) if module else names
        for candidate in candidates:
            if candidate and candidate.startswith("dv_platform."):
                result.add(candidate.split(".", 2)[1])
    result.discard(_package(path))
    return result


def _cycles(graph: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    found: set[tuple[str, ...]] = set()

    def visit(origin: str, node: str, path: tuple[str, ...]) -> None:
        for target in graph.get(node, set()):
            if target == origin:
                cycle = path + (origin,)
                rotations = tuple(cycle[index:-1] + cycle[: index + 1] for index in range(len(cycle) - 1))
                found.add(min(rotations))
            elif target not in path:
                visit(origin, target, path + (target,))

    for package in graph:
        visit(package, package, (package,))
    return tuple(sorted(found))


def inspect() -> dict[str, object]:
    modules: dict[str, int] = {}
    functions: list[FunctionMetric] = []
    dependencies: dict[str, set[str]] = defaultdict(set)
    for path in _python_files():
        lines = _code_lines(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT).as_posix()
        modules[relative] = len(path.read_text(encoding="utf-8").splitlines())
        functions.extend(_function_metrics(path, tree, lines))
        package = _package(path)
        if package in ACYCLIC_PACKAGES:
            dependencies[package].update(_dependencies(path, tree) & ACYCLIC_PACKAGES)
    for package in ACYCLIC_PACKAGES:
        dependencies.setdefault(package, set())
    duplicates = {
        digest: [f"{item.path}:{item.line}:{item.name}" for item in functions if item.digest == digest]
        for digest in {item.digest for item in functions}
        if sum(item.digest == digest for item in functions) > 1
    }
    template_lines = {
        path.relative_to(ROOT).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
        for path in _template_files()
    }
    return {
        "module_lines": dict(sorted(modules.items(), key=lambda item: (-item[1], item[0]))),
        "functions": [item.__dict__ for item in sorted(functions, key=lambda item: -item.code_lines)],
        "dependencies": {name: sorted(values) for name, values in sorted(dependencies.items())},
        "cycles": _cycles(dict(dependencies)),
        "duplicate_bodies": duplicates,
        "template_lines": template_lines,
    }


def violations(report: dict[str, object]) -> tuple[str, ...]:
    errors = []
    cycles = report["cycles"]
    assert isinstance(cycles, tuple)
    errors.extend("package dependency cycle: " + " -> ".join(cycle) for cycle in cycles)
    module_lines = report["module_lines"]
    assert isinstance(module_lines, dict)
    for path, line_count in module_lines.items():
        package = Path(path).parts[2]
        if path in MODULE_EXCEPTIONS:
            continue
        if package in BOUNDED_PACKAGES and int(line_count) > MAX_MODULE_LINES:
            errors.append(f"{path}: {line_count} physical lines (maximum {MAX_MODULE_LINES})")
    functions = report["functions"]
    assert isinstance(functions, list)
    for metric in functions:
        assert isinstance(metric, dict)
        package = Path(str(metric["path"])).parts[2]
        if package not in BOUNDED_PACKAGES:
            continue
        if (str(metric["path"]), str(metric["name"])) in FUNCTION_EXCEPTIONS:
            continue
        if int(metric["code_lines"]) > MAX_FUNCTION_LINES:
            errors.append(
                f"{metric['path']}:{metric['line']} {metric['name']}: "
                f"{metric['code_lines']} code lines (maximum {MAX_FUNCTION_LINES})"
            )
        if int(metric["complexity"]) > MAX_COMPLEXITY:
            errors.append(
                f"{metric['path']}:{metric['line']} {metric['name']}: "
                f"complexity {metric['complexity']} (maximum {MAX_COMPLEXITY})"
            )
    errors.extend(_template_violations(report))
    return tuple(errors)


def _template_violations(report: dict[str, object]) -> list[str]:
    errors: list[str] = []
    template_lines = report["template_lines"]
    assert isinstance(template_lines, dict)
    for path, line_count in template_lines.items():
        if int(line_count) > MAX_MODULE_LINES:
            errors.append(f"{path}: {line_count} physical lines (maximum {MAX_MODULE_LINES})")
    for target in RENDER_TARGETS:
        template = TEMPLATE_ROOT / target / "main.j2"
        if not template.is_file():
            errors.append(f"missing package-owned target template: {template.relative_to(ROOT)}")
            continue
        source = template.read_text(encoding="utf-8")
        compact = "".join(source.split())
        if compact in {
            "{{lines|join('\\n')}}",
            "{{presentation.lines|join('\\n')}}",
            "{{content}}",
            "{{presentation.content}}",
        }:
            errors.append(f"{template.relative_to(ROOT)}: pass-through target template is forbidden")
    rendering_source = (SOURCE_ROOT / "generation" / "rendering.py").read_text(encoding="utf-8")
    for contract in ("PackageLoader", "StrictUndefined", "build_target_context"):
        if contract not in rendering_source:
            errors.append(f"generation renderer does not enforce {contract}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when a target subsystem exceeds a bound")
    parser.add_argument("--json", action="store_true", help="emit the full machine-readable report")
    args = parser.parse_args()
    report = inspect()
    errors = violations(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"modules={len(report['module_lines'])} templates={len(report['template_lines'])} "
            f"functions={len(report['functions'])}"
        )
        print(f"cycles={len(report['cycles'])} duplicates={len(report['duplicate_bodies'])}")
        for error in errors:
            print(error)
    return 1 if args.check and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
