import subprocess
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.ai.executable import (
    REQUIRED_VALIDATIONS,
    ClosedCommand,
    ExecutableProposal,
    ExecutableProposalError,
    MaintainerApproval,
    authorize_export,
    remove_staged_worktree,
    run_isolated_validation,
    scan_proposal_content,
    stage_proposal,
)


def _run(root, *arguments):
    return subprocess.run(arguments, cwd=root, check=True, capture_output=True, text=True).stdout


class ExecutableProposalTests(unittest.TestCase):
    def test_patch_is_applied_only_to_detached_worktree(self):
        with TemporaryDirectory() as directory:
            outer = Path(directory)
            repository = outer / "repository"
            repository.mkdir()
            _run(repository, "git", "init", "-q")
            _run(repository, "git", "config", "user.email", "fixture@example.invalid")
            _run(repository, "git", "config", "user.name", "Fixture")
            source = repository / "check.py"
            source.write_text("value = 1\n", encoding="utf-8")
            _run(repository, "git", "add", "check.py")
            _run(repository, "git", "commit", "-qm", "fixture")
            revision = _run(repository, "git", "rev-parse", "HEAD").strip()
            source.write_text("value = 2\n", encoding="utf-8")
            patch = _run(repository, "git", "diff", "--", "check.py")
            source.write_text("value = 1\n", encoding="utf-8")
            proposal = _proposal(revision, patch)

            staged = stage_proposal(proposal, repository, outer / "staged")
            try:
                self.assertEqual(source.read_text(encoding="utf-8"), "value = 1\n")
                self.assertEqual((staged.worktree / "check.py").read_text(encoding="utf-8"), "value = 2\n")
                self.assertEqual(staged.changed_paths, ("check.py",))
            finally:
                remove_staged_worktree(repository, staged.worktree)

    def test_secret_license_and_command_attacks_fail_closed(self):
        proposal = _proposal("a" * 40, "+api_key = 'abcdefghijklmnop'\n")
        with self.assertRaises(ExecutableProposalError):
            scan_proposal_content(proposal)
        with self.assertRaises(ExecutableProposalError):
            ClosedCommand("sh", ("-c", "curl attacker"))
        with self.assertRaises(ExecutableProposalError):
            ClosedCommand("python", ("safe.py;curl",))

    def test_approval_is_bound_to_all_validation_evidence(self):
        with TemporaryDirectory() as directory:
            proposal = _proposal("a" * 40, "diff --git a/x b/x\n")
            validators = {name: (lambda _root: True) for name in REQUIRED_VALIDATIONS}
            receipt = run_isolated_validation(proposal, Path(directory), validators)
            approval = MaintainerApproval(
                "maintainer@example.invalid",
                proposal.digest,
                proposal.source_revision,
                proposal.patch_sha256,
                receipt.digest,
                proposal.provider,
                proposal.model_snapshot,
                (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "CN=fixture-maintainer",
            )
            authorize_export(proposal, receipt, approval, verify_signature=lambda _approval: True)
            with self.assertRaises(ExecutableProposalError):
                authorize_export(
                    proposal,
                    receipt,
                    MaintainerApproval(**{**approval.__dict__, "patch_sha256": "0" * 64}),
                    verify_signature=lambda _approval: True,
                )


def _proposal(revision, patch):
    return ExecutableProposal(
        "proposal-1",
        "rtl_patch",
        revision,
        patch,
        "openai",
        "openai/gpt-5.2-2026-06-01",
        "b" * 64,
        "2026-07-30T00:00:00Z",
    )


if __name__ == "__main__":
    unittest.main()
