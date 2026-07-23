# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dv_platform.core.config import (
    ConfigDiagnostic,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class _CommandOutcome:
    command: str
    ok: bool
    data: dict[str, object]
    text_lines: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    diagnostics: tuple[ConfigDiagnostic, ...] = ()


def _print_diagnostics(diagnostics: tuple[ConfigDiagnostic, ...]) -> None:
    for diagnostic in diagnostics:
        print(f"{diagnostic.severity}={diagnostic.message}")


def _emit_success(
    args: argparse.Namespace,
    command: str,
    data: dict[str, object],
    text_lines: tuple[str, ...],
) -> None:
    _emit_outcome(args, _CommandOutcome(command, True, data, text_lines))


def _emit_error(
    args: argparse.Namespace,
    command: str,
    code: str,
    message: str,
    data: dict[str, object] | None = None,
    diagnostics: tuple[ConfigDiagnostic, ...] = (),
) -> None:
    _emit_outcome(
        args,
        _CommandOutcome(
            command,
            False,
            data or {},
            error_code=code,
            error_message=message,
            diagnostics=diagnostics,
        ),
    )


def _emit_outcome(args: argparse.Namespace, outcome: _CommandOutcome) -> None:
    if getattr(args, "json_output", False):
        payload: dict[str, object] = {"ok": outcome.ok, "command": outcome.command}
        if outcome.ok:
            payload["data"] = outcome.data
        else:
            payload["error"] = {
                "code": outcome.error_code or "error",
                "message": outcome.error_message or "Command failed",
            }
            if outcome.data:
                payload["data"] = outcome.data
            if outcome.diagnostics:
                payload["diagnostics"] = _diagnostics_json(outcome.diagnostics)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if outcome.ok:
        for line in outcome.text_lines:
            print(line)
        return
    print(f"error={outcome.error_message}")


def _diagnostics_json(diagnostics: tuple[ConfigDiagnostic, ...]) -> list[dict[str, str]]:
    return [{"severity": diagnostic.severity, "message": diagnostic.message} for diagnostic in diagnostics]
