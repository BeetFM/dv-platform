"""Fail-closed release channel and exact tag-target policy."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "qualification" / "policies" / "release-channels-v1.json"
VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)(?:(?P<pre>a|b|rc)(?P<serial>[1-9][0-9]*))?$"
)
TAG_RE = re.compile(r"^v(?P<version>.+)$")


class ReleasePolicyError(ValueError):
    """Raised when a release is malformed, unapproved, or contextually stale."""


@dataclass(frozen=True)
class ReleaseDecision:
    version: str
    tag: str
    channel: str
    minimum_stage: int
    publish: bool
    destination: str
    environment: str

    def as_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "tag": self.tag,
            "channel": self.channel,
            "minimum_stage": self.minimum_stage,
            "publish": self.publish,
            "destination": self.destination,
            "environment": self.environment,
        }


def load_policy(path: Path = POLICY_PATH) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleasePolicyError(f"release channel policy is unreadable: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ReleasePolicyError("unsupported release channel policy")
    channels = payload.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise ReleasePolicyError("release channel policy has no channels")
    return payload


def resolve_release(tag: str, package_version: str, policy: dict[str, object] | None = None) -> ReleaseDecision:
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        raise ReleasePolicyError(f"release tag must be an exact v-prefixed version: {tag}")
    match = TAG_RE.fullmatch(tag)
    assert match is not None
    version = match.group("version")
    if version != package_version:
        raise ReleasePolicyError(f"release tag {tag} does not match project version {package_version}")
    parsed = VERSION_RE.fullmatch(version)
    if parsed is None:
        raise ReleasePolicyError(f"unsupported release version: {version}")
    channel = _channel(parsed)
    channels = (policy or load_policy()).get("channels")
    if not isinstance(channels, dict) or channel not in channels:
        raise ReleasePolicyError(f"release channel is not approved: {channel}")
    raw = channels[channel]
    if not isinstance(raw, dict):
        raise ReleasePolicyError(f"release channel policy is invalid: {channel}")
    minimum_stage = raw.get("minimum_stage")
    if not isinstance(minimum_stage, int) or not 6 <= minimum_stage <= 13:
        raise ReleasePolicyError(f"release channel minimum stage is invalid: {channel}")
    publish = raw.get("publish")
    if not isinstance(publish, bool):
        raise ReleasePolicyError(f"release channel publication policy is invalid: {channel}")
    return ReleaseDecision(
        version=version,
        tag=tag,
        channel=channel,
        minimum_stage=minimum_stage,
        publish=publish,
        destination=_string(raw.get("destination"), "destination"),
        environment=_string(raw.get("environment"), "environment"),
    )


def verify_exact_tag(root: Path, tag: str, expected_sha: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        raise ReleasePolicyError("expected release SHA is invalid")
    if not re.fullmatch(r"v[0-9A-Za-z.-]+", tag):
        raise ReleasePolicyError("release tag contains unsupported characters")
    ref = f"refs/tags/{tag}"
    tag_type = _git(root, "cat-file", "-t", ref)
    if tag_type not in {"commit", "tag"}:
        raise ReleasePolicyError(f"release tag does not resolve to a commit or annotated tag: {tag}")
    target = _git(root, "rev-parse", f"{ref}^{{commit}}")
    if target != expected_sha:
        raise ReleasePolicyError(f"release tag target mismatch: {target} != {expected_sha}")
    head = _git(root, "rev-parse", "HEAD")
    if head != expected_sha:
        raise ReleasePolicyError(f"checked-out release SHA mismatch: {head} != {expected_sha}")
    return target


def project_version(root: Path = ROOT) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = payload.get("project", {}).get("version") if isinstance(payload.get("project"), dict) else None
    if not isinstance(version, str):
        raise ReleasePolicyError("project version is missing")
    return version


def _channel(match: re.Match[str]) -> str:
    major = int(match.group("major"))
    pre = match.group("pre")
    if major == 0 and pre is None:
        return "development"
    if pre == "a":
        return "alpha"
    if pre == "b":
        return "beta"
    if pre == "rc":
        return "rc"
    return "ga" if major == 1 and match.group("minor") == "0" and match.group("patch") == "0" else "patch"


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleasePolicyError(f"release channel {field} is missing")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(("git", *args), cwd=root, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise ReleasePolicyError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-sha")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        decision = resolve_release(args.tag, project_version(args.root))
        if args.expected_sha:
            verify_exact_tag(args.root, args.tag, args.expected_sha)
    except (OSError, ReleasePolicyError) as error:
        print(error)
        return 1
    print(json.dumps(decision.as_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
