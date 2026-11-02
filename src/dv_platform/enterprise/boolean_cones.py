"""Strict Boolean eligibility and exact, universally quantified AIG cone miters."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

_GATES = {
    "$_NOT_": {"A"},
    "$_AND_": {"A", "B"},
    "$_OR_": {"A", "B"},
    "$_XOR_": {"A", "B"},
    "$_MUX_": {"A", "B", "S"},
}


def _boolean_cell(cell, drivers):
    inputs = _GATES.get(cell["type"])
    connections = cell["connections"]
    if inputs is None or set(connections) != inputs | {"Y"}:
        return None
    if any(len(bits) != 1 for bits in connections.values()):
        return None
    if any(type(bit) is not int and bit not in {"0", "1"} for bits in connections.values() for bit in bits):
        return None
    if cell["port_directions"] != {port: "output" if port == "Y" else "input" for port in connections}:
        return None
    output = connections["Y"][0]
    if type(output) is not int or output in drivers:
        return None
    return output, {connections[port][0] for port in inputs}


def is_defined_boolean(module: dict[str, Any]) -> bool:
    """Reject undefined, multiply driven, undriven, cyclic or non-scalar logic."""
    ports = module["ports"]
    inputs = [bit for port in ports.values() if port["direction"] == "input" for bit in port["bits"]]
    if any(type(bit) is not int for bit in inputs) or len(set(inputs)) != len(inputs):
        return False
    known = set(inputs) | {"0", "1"}
    drivers = set(known)
    outputs: list[int] = []
    unresolved: list[int] = []
    consumers: dict[Any, list[int]] = defaultdict(list)
    queue: deque[int] = deque()
    for cell in module["cells"].values():
        logic = _boolean_cell(cell, drivers)
        if logic is None:
            return False
        output, dependencies = logic
        drivers.add(output)
        dependencies -= known
        index = len(outputs)
        outputs.append(output)
        unresolved.append(len(dependencies))
        for bit in dependencies:
            consumers[bit].append(index)
        if not dependencies:
            queue.append(index)
    while queue:
        output = outputs[queue.popleft()]
        known.add(output)
        for consumer in consumers[output]:
            unresolved[consumer] -= 1
            if unresolved[consumer] == 0:
                queue.append(consumer)
    return all(count == 0 for count in unresolved) and all(
        bit in known for port in ports.values() if port["direction"] == "output" for bit in port["bits"]
    )


def load_aag(path: Path) -> dict[str, Any]:
    """Parse only complete combinational ASCII AIGs with explicit unique symbols."""
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Boolean AIG exceeds its 128 MiB parsing bound")
    lines = path.read_text().splitlines()
    header = lines[0].split()
    if len(header) != 6 or header[0] != "aag":
        raise ValueError("unsupported Boolean AIG header")
    maximum, inputs, latches, outputs, gates = map(int, header[1:])
    if latches or min(maximum, inputs, outputs, gates) < 0 or maximum != inputs + gates:
        raise ValueError("Boolean AIG must contain only contiguous inputs and AND gates")
    if list(map(int, lines[1 : 1 + inputs])) != list(range(2, 2 * inputs + 1, 2)):
        raise ValueError("Boolean AIG input bindings are incomplete")
    co = list(map(int, lines[1 + inputs : 1 + inputs + outputs]))
    if len(co) != outputs or any(not 0 <= literal <= 2 * maximum + 1 for literal in co):
        raise ValueError("Boolean AIG output bindings are incomplete")
    nodes = {}
    for index, line in enumerate(lines[1 + inputs + outputs : 1 + inputs + outputs + gates], inputs + 1):
        lhs, a, b = map(int, line.split())
        if lhs != 2 * index or not lhs > a >= 0 or not lhs > b >= 0:
            raise ValueError("Boolean AIG is not a complete acyclic AND graph")
        nodes[index] = (a, b)
    if len(nodes) != gates:
        raise ValueError("Boolean AIG gates are incomplete")
    symbols = _aag_symbols(lines[1 + inputs + outputs + gates :], inputs, outputs)
    return {"inputs": inputs, "outputs": co, "nodes": nodes, "symbols": symbols}


def _aag_symbols(lines, inputs, outputs):
    symbols: dict[str, dict[int, str]] = {"i": {}, "o": {}}
    for line in lines:
        if line == "c":
            break
        tag, name = line.split(" ", 1)
        kind, index = tag[0], int(tag[1:])
        if kind not in symbols or index in symbols[kind] or not name:
            raise ValueError("Boolean AIG has invalid or duplicate symbols")
        symbols[kind][index] = name
    for kind, count in (("i", inputs), ("o", outputs)):
        names = symbols[kind]
        if set(names) != set(range(count)) or len(set(names.values())) != count:
            raise ValueError("Boolean AIG symbols are incomplete or ambiguous")
    return symbols


def _reachable(inputs, nodes, literal):
    seen, order, pending = set(), [], [literal // 2]
    while pending:
        var = pending.pop()
        if var == 0 or var in seen:
            continue
        seen.add(var)
        if var <= inputs:
            order.append(var)
        else:
            a, b = nodes[var]
            pending.extend((b // 2, a // 2))
    return seen, order


def _conjunction(a, b, inputs, nodes, unique):
    if a == 0 or b == 0 or a == (b ^ 1):
        return 0
    if a == 1 or a == b:
        return b
    if b == 1:
        return a
    pair = tuple(sorted((a, b)))
    if pair not in unique:
        nodes[len(nodes) + inputs + 1] = pair
        unique[pair] = 2 * (inputs + len(nodes))
    return unique[pair]


def _rebuild(model, output, bindings, nodes, unique):
    seen, _ = _reachable(model["inputs"], model["nodes"], output)
    memo = {0: 0, **bindings}
    for var in sorted(seen - set(memo)):
        a, b = model["nodes"][var]
        memo[var] = _conjunction(memo[a // 2] ^ (a & 1), memo[b // 2] ^ (b & 1), len(bindings), nodes, unique)
    return memo[output // 2] ^ (output & 1)


def _serialize_miter(inputs, nodes, output):
    used, _ = _reachable(len(inputs), nodes, output)
    kept = [var for var in range(1, len(inputs) + 1) if var in used]
    renamed = {0: 0, **{var: index + 1 for index, var in enumerate(kept)}}
    gates: list[tuple[int, int]] = []
    for var in sorted(used - set(renamed)):
        a, b = nodes[var]
        renamed[var] = len(kept) + len(gates) + 1
        gates.append((2 * renamed[a // 2] + (a & 1), 2 * renamed[b // 2] + (b & 1)))
    lines = [f"aag {len(kept) + len(gates)} {len(kept)} 0 1 {len(gates)}"]
    lines += [str(2 * index) for index in range(1, len(kept) + 1)]
    lines += [str(2 * renamed[output // 2] + (output & 1))]
    lines += [f"{2 * index} {a} {b}" for index, (a, b) in enumerate(gates, len(kept) + 1)]
    lines += [f"i{index} input_{index}" for index in range(len(kept))]
    lines += ["o0 difference", "c", "Exact reachable cone; shared source/gate input bindings retained"]
    return ("\n".join(lines) + "\n").encode(), [inputs[var - 1] for var in kept]


def cone_miter(gold, gate, left, right):
    """Build the exact XOR of two outputs, retaining a shared input bijection."""
    order = _reachable(gold["inputs"], gold["nodes"], left)[1]
    known = set(order)
    order += [var for var in _reachable(gate["inputs"], gate["nodes"], right)[1] if var not in known]
    bindings = {var: 2 * (index + 1) for index, var in enumerate(order)}
    nodes: dict[int, tuple[int, int]] = {}
    unique: dict[tuple[int, int], int] = {}
    a = _rebuild(gold, left, bindings, nodes, unique)
    b = _rebuild(gate, right, bindings, nodes, unique)
    a_not_b = _conjunction(a, b ^ 1, len(order), nodes, unique)
    not_a_b = _conjunction(a ^ 1, b, len(order), nodes, unique)
    difference = _conjunction(a_not_b ^ 1, not_a_b ^ 1, len(order), nodes, unique) ^ 1
    return _serialize_miter(order, nodes, difference)
