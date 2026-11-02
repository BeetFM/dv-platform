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
ACYCLIC_PACKAGES = {"ai", "configuration", "domain", "infrastructure"}
BOUNDED_PACKAGES = ACYCLIC_PACKAGES | {"enterprise"}
MAX_MODULE_LINES = 700
MAX_FUNCTION_LINES = 75
MAX_COMPLEXITY = 12


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
        ast.ExceptHandler,
    )
    score = 1
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, branches):
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
    return {
        "module_lines": dict(sorted(modules.items(), key=lambda item: (-item[1], item[0]))),
        "functions": [item.__dict__ for item in sorted(functions, key=lambda item: -item.code_lines)],
        "dependencies": {name: sorted(values) for name, values in sorted(dependencies.items())},
        "cycles": _cycles(dict(dependencies)),
        "duplicate_bodies": duplicates,
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
        if package in BOUNDED_PACKAGES and int(line_count) > MAX_MODULE_LINES:
            errors.append(f"{path}: {line_count} physical lines (maximum {MAX_MODULE_LINES})")
    functions = report["functions"]
    assert isinstance(functions, list)
    for metric in functions:
        assert isinstance(metric, dict)
        package = Path(str(metric["path"])).parts[2]
        if package not in BOUNDED_PACKAGES:
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
    return tuple(errors)


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
        print(f"modules={len(report['module_lines'])} functions={len(report['functions'])}")
        print(f"cycles={len(report['cycles'])} duplicates={len(report['duplicate_bodies'])}")
        for error in errors:
            print(error)
    return 1 if args.check and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
