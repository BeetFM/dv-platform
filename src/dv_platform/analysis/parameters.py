"""Deterministic bounded Cartesian parameter-matrix expansion."""

from __future__ import annotations

import ast
import itertools


def expand_parameter_matrix(
    axes: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    constraints: tuple[str, ...] = (),
    maximum_points: int = 64,
) -> tuple[tuple[str, ...], ...]:
    """Expand sorted axes, filter safe constraints, and enforce a hard bound."""

    if not 1 <= maximum_points <= 4096:
        raise ValueError("parameter matrix maximum_points must be between 1 and 4096")
    names = [name for name, _values in axes]
    if not axes or any(not name or not values for name, values in axes) or len(names) != len(set(names)):
        raise ValueError("parameter matrix requires unique non-empty axes and values")
    ordered = tuple(sorted(axes))
    raw_points = 1
    for _name, values in ordered:
        raw_points *= len(values)
        if raw_points > maximum_points * 64:
            raise ValueError("parameter matrix raw Cartesian product exceeds safety guard")
    points: list[tuple[str, ...]] = []
    for values in itertools.product(*(values for _name, values in ordered)):
        environment = {name: _literal(value) for (name, _axis), value in zip(ordered, values, strict=True)}
        if all(_constraint(expression, environment) for expression in constraints):
            points.append(tuple(f"{name}={value}" for (name, _axis), value in zip(ordered, values, strict=True)))
            if len(points) > maximum_points:
                raise ValueError("parameter matrix exceeds maximum_points after constraints")
    if not points:
        raise ValueError("parameter matrix constraints reject every point")
    return tuple(points)


def _literal(value: str) -> int | bool | str:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value, 0)
    except ValueError:
        return value


def _constraint(expression: str, environment: dict[str, int | bool | str]) -> bool:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid parameter constraint: {expression}") from exc
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.UnaryOp,
        ast.Not,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Name,
        ast.Load,
        ast.Constant,
    )
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError(f"unsupported parameter constraint expression: {expression}")
    unknown = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} - set(environment)
    if unknown:
        raise ValueError("parameter constraint references unknown axes: " + ", ".join(sorted(unknown)))
    return bool(eval(compile(tree, "<parameter-constraint>", "eval"), {"__builtins__": {}}, environment))
