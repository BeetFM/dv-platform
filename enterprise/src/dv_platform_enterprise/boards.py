"""Entitlement-gated Vivado and protected Arty A7 lab execution."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.boards.arty_a7 import ARTY_A7_PROFILES, VIVADO_VERSION, validate_board_evidence
from dv_platform.product import ResolvedProductPlan, require_capability


@dataclass(frozen=True)
class VivadoBoardInvocation:
    profile_id: str
    workspace: Path
    tcl_script: Path
    result_manifest: Path
    timeout_seconds: int = 7200


def run_vivado_board(
    invocation: VivadoBoardInvocation,
    plan: ResolvedProductPlan,
    *,
    executable: str = "vivado",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Run only a contained generated Tcl program after entitlement gating."""

    require_capability(plan, "board.arty_a7.qualify")
    if invocation.profile_id not in ARTY_A7_PROFILES:
        raise ValueError("unknown Arty A7 profile")
    root = invocation.workspace.resolve()
    script = invocation.tcl_script.resolve()
    result = invocation.result_manifest.resolve()
    if (
        not root.is_dir()
        or not script.is_file()
        or not script.is_relative_to(root)
        or not result.is_relative_to(root)
        or not 1 <= invocation.timeout_seconds <= 14_400
    ):
        raise ValueError("Vivado board invocation escapes its workspace or has an invalid timeout")
    version = runner(
        (executable, "-version"),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if version.returncode or f"v{VIVADO_VERSION}" not in version.stdout:
        raise ValueError(f"Vivado {VIVADO_VERSION} is required")
    completed = runner(
        (executable, "-mode", "batch", "-nojournal", "-nolog", "-source", str(script)),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=invocation.timeout_seconds,
    )
    if completed.returncode:
        raise ValueError("Vivado board qualification failed")
    document = json.loads(result.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Vivado result manifest must be an object")
    return document


def import_protected_lab_evidence(
    document: dict[str, Any],
    plan: ResolvedProductPlan,
    *,
    expected_source_revision: str,
    expected_bitstream_sha256: str,
    max_age,
    verify_signature: Callable[[dict[str, Any]], bool],
) -> None:
    require_capability(plan, "board.arty_a7.qualify")
    profile_id = document.get("profile_id")
    if profile_id not in ARTY_A7_PROFILES:
        raise ValueError("unknown Arty A7 evidence profile")
    validate_board_evidence(
        document,
        ARTY_A7_PROFILES[str(profile_id)],
        expected_source_revision=expected_source_revision,
        expected_bitstream_sha256=expected_bitstream_sha256,
        max_age=max_age,
        verify_signature=verify_signature,
    )
