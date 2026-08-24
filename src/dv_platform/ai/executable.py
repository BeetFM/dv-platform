"""Digest-bound executable AI proposals and maintainer approvals."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath

APPROVED_ARTIFACT_CLASSES = frozenset({"verification_collateral", "allowlisted_script", "rtl_patch"})
REQUIRED_VALIDATIONS = frozenset(
    {
        "compile_elaboration",
        "semantic_crosscheck",
        "affected_tests",
        "mutation",
        "coverage",
        "policy",
        "path_containment",
        "secret_scan",
        "license_scan",
        "impact_regression",
    }
)
ALLOWED_COMMANDS = frozenset({"python", "ruff", "mypy", "verilator", "sby", "yosys"})
_SECRET = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9+/_.-]{12,}")
_LICENSE_MARKERS = ("all rights reserved", "proprietary and confidential", "do not distribute")


class ExecutableProposalError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutableProposal:
    proposal_id: str
    artifact_class: str
    source_revision: str
    patch: str
    provider: str
    model_snapshot: str
    context_digest: str
    created_at: str

    @property
    def patch_sha256(self) -> str:
        return sha256(self.patch.encode()).hexdigest()

    @property
    def digest(self) -> str:
        return sha256(_canonical(self.statement())).hexdigest()

    def statement(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "artifact_class": self.artifact_class,
            "source_revision": self.source_revision,
            "patch_sha256": self.patch_sha256,
            "provider": self.provider,
            "model_snapshot": self.model_snapshot,
            "context_digest": self.context_digest,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ValidationReceipt:
    proposal_digest: str
    source_revision: str
    checks: tuple[tuple[str, str], ...]
    patch_sha256: str
    isolated_worktree: str

    @property
    def passed(self) -> bool:
        return set(dict(self.checks)) == REQUIRED_VALIDATIONS and all(value == "passed" for _, value in self.checks)

    @property
    def digest(self) -> str:
        return sha256(_canonical(self.__dict__)).hexdigest()


@dataclass(frozen=True)
class MaintainerApproval:
    maintainer: str
    proposal_digest: str
    source_revision: str
    patch_sha256: str
    validation_digest: str
    provider: str
    model_snapshot: str
    expires_at: str
    signature_identity: str


@dataclass(frozen=True)
class ClosedCommand:
    executable: str
    arguments: tuple[str, ...] = ()
    timeout_seconds: int = 600

    def __post_init__(self) -> None:
        if self.executable not in ALLOWED_COMMANDS:
            raise ExecutableProposalError("script executable is not allowlisted")
        if not 1 <= self.timeout_seconds <= 3600:
            raise ExecutableProposalError("script timeout is outside 1..3600 seconds")
        if any(
            not argument
            or "\0" in argument
            or argument.startswith(("/", "~"))
            or any(character in argument for character in (";", "|", "`", "\n", "\r"))
            for argument in self.arguments
        ):
            raise ExecutableProposalError("script contains an unsafe argument")


@dataclass(frozen=True)
class StagedProposal:
    proposal: ExecutableProposal
    worktree: Path
    changed_paths: tuple[str, ...]


def validate_proposal_paths(proposal: ExecutableProposal, changed_paths: Iterable[str]) -> None:
    if proposal.artifact_class not in APPROVED_ARTIFACT_CLASSES:
        raise ExecutableProposalError("artifact class is not approved")
    paths = tuple(changed_paths)
    if not paths:
        raise ExecutableProposalError("proposal contains no files")
    for raw in paths:
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts or "\0" in raw:
            raise ExecutableProposalError(f"proposal path escapes the isolated worktree: {raw}")


def scan_proposal_content(proposal: ExecutableProposal) -> None:
    if _SECRET.search(proposal.patch):
        raise ExecutableProposalError("proposal contains material resembling a secret")
    lowered = proposal.patch.lower()
    if any(marker in lowered for marker in _LICENSE_MARKERS):
        raise ExecutableProposalError("proposal contains unapproved license markers")


def stage_proposal(proposal: ExecutableProposal, repository: Path, staging_root: Path) -> StagedProposal:
    """Apply a proposal to a detached worktree without editing the active tree."""

    scan_proposal_content(proposal)
    resolved_repository = repository.resolve()
    resolved_staging = staging_root.resolve()
    if not (resolved_repository / ".git").exists():
        raise ExecutableProposalError("proposal repository is not a Git worktree")
    if resolved_staging == resolved_repository or resolved_staging.is_relative_to(resolved_repository):
        raise ExecutableProposalError("isolated worktree must be outside the active repository")
    resolved_staging.parent.mkdir(parents=True, exist_ok=True)
    _git(resolved_repository, "worktree", "add", "--detach", str(resolved_staging), proposal.source_revision)
    try:
        _apply_patch(resolved_staging, proposal.patch)
        changed = _git(resolved_staging, "diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.splitlines()
        validate_proposal_paths(proposal, changed)
        return StagedProposal(proposal, resolved_staging, tuple(changed))
    except Exception:
        remove_staged_worktree(resolved_repository, resolved_staging)
        raise


def remove_staged_worktree(repository: Path, worktree: Path) -> None:
    _git(repository.resolve(), "worktree", "remove", "--force", str(worktree.resolve()))


def execute_closed_command(
    command: ClosedCommand,
    worktree: Path,
    *,
    sandbox_prefix: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    if not sandbox_prefix:
        raise ExecutableProposalError("executable AI validation requires an explicit sandbox")
    return subprocess.run(
        (*sandbox_prefix, command.executable, *command.arguments),
        cwd=worktree,
        capture_output=True,
        text=True,
        check=False,
        timeout=command.timeout_seconds,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def run_isolated_validation(
    proposal: ExecutableProposal,
    worktree: Path,
    validators: dict[str, Callable[[Path], bool]],
) -> ValidationReceipt:
    if not worktree.is_dir() or worktree.is_symlink():
        raise ExecutableProposalError("validation worktree must be an isolated real directory")
    if set(validators) != REQUIRED_VALIDATIONS:
        raise ExecutableProposalError("validator set is incomplete or contains unknown checks")
    checks = tuple((name, "passed" if validators[name](worktree) else "failed") for name in sorted(validators))
    return ValidationReceipt(proposal.digest, proposal.source_revision, checks, proposal.patch_sha256, str(worktree))


def authorize_export(
    proposal: ExecutableProposal,
    validation: ValidationReceipt,
    approval: MaintainerApproval,
    *,
    verify_signature: Callable[[MaintainerApproval], bool],
    now: datetime | None = None,
) -> None:
    expires = datetime.fromisoformat(approval.expires_at.replace("Z", "+00:00"))
    expected = (
        approval.proposal_digest == proposal.digest
        and approval.source_revision == proposal.source_revision == validation.source_revision
        and approval.patch_sha256 == proposal.patch_sha256 == validation.patch_sha256
        and approval.validation_digest == validation.digest
        and approval.provider == proposal.provider
        and approval.model_snapshot == proposal.model_snapshot
    )
    if not expected or not validation.passed:
        raise ExecutableProposalError("approval is not bound to a passing proposal and validation receipt")
    if (now or datetime.now(UTC)) > expires:
        raise ExecutableProposalError("maintainer approval is expired")
    if not approval.maintainer or not approval.signature_identity or not verify_signature(approval):
        raise ExecutableProposalError("maintainer approval signature is invalid")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _apply_patch(worktree: Path, patch: str) -> None:
    for arguments in (("apply", "--check", "--whitespace=error-all", "-"), ("apply", "--index", "-")):
        result = subprocess.run(
            ("git", *arguments),
            cwd=worktree,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode:
            raise ExecutableProposalError(f"proposal patch was rejected: {result.stderr.strip()}")


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ExecutableProposalError(f"isolated Git operation failed: {exc}") from exc
