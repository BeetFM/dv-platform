"""Fail-closed publication decisions and release recovery records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener


class PublicationConflict(ValueError):
    """Raised when an immutable version already contains different bytes."""


@dataclass(frozen=True)
class PublicationDecision:
    action: str
    reason: str


def decide_publication(expected: dict[str, str], existing: dict[str, str] | None) -> PublicationDecision:
    """Return upload/no-op/conflict without ever hiding a digest mismatch."""
    if existing is None:
        return PublicationDecision("upload", "version is not present at destination")
    if not existing:
        raise PublicationConflict("destination returned an empty subject set")
    if existing == expected:
        return PublicationDecision("noop", "destination subjects match the immutable release")
    differing = sorted(set(existing) | set(expected))
    details = [name for name in differing if existing.get(name) != expected.get(name)]
    raise PublicationConflict("destination version exists with different subjects: " + ", ".join(details))


def verify_reinstall(expected: dict[str, str], observed: dict[str, str]) -> None:
    if expected != observed:
        differing = sorted(set(expected) | set(observed))
        details = [name for name in differing if expected.get(name) != observed.get(name)]
        raise PublicationConflict("reinstalled release subjects differ: " + ", ".join(details))


def subject_digests(directory: Path) -> dict[str, str]:
    root = directory.resolve(strict=True)
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir(), key=lambda item: item.name)
        if path.is_file() and not path.is_symlink() and (path.name.endswith(".whl") or path.name.endswith(".tar.gz"))
    }


def query_simple_index(index_url: str, package: str, expected: dict[str, str]) -> dict[str, str] | None:
    """Read exact filename/hash subjects from a PEP 503 Simple API endpoint."""
    base = index_url.rstrip("/") + "/"
    package_path = re.sub(r"[-_.]+", "-", package).lower() + "/"
    request = Request(urljoin(base, package_path), headers={"Accept": "text/html"})
    try:
        with build_opener().open(request, timeout=30) as response:
            html = response.read(4 * 1024 * 1024).decode("utf-8", errors="strict")
    except HTTPError as error:
        if error.code == 404:
            return None
        raise PublicationConflict(f"package index query failed with HTTP {error.code}") from error
    except (OSError, UnicodeDecodeError, URLError) as error:
        raise PublicationConflict(f"package index query failed: {error}") from error
    parser = _SimpleLinks()
    parser.feed(html)
    parser.close()
    matched = {name: parser.subjects[name] for name in expected if name in parser.subjects}
    if not matched:
        return None
    if set(matched) != set(expected):
        raise PublicationConflict("package index returned an incomplete immutable version")
    return matched


class _SimpleLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.subjects: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not isinstance(href, str) or "#sha256=" not in href:
            return
        name, digest = href.split("#sha256=", 1)
        filename = name.rsplit("/", 1)[-1]
        if filename.endswith((".whl", ".tar.gz")) and re.fullmatch(r"[0-9a-f]{64}", digest):
            self.subjects[filename] = digest


def write_release_record(output: Path, *, status: str, decision: PublicationDecision, subjects: dict[str, str], reinstall: str) -> dict[str, Any]:
    if status not in {"validated", "uploaded", "noop", "failed"}:
        raise ValueError(f"unsupported release record status: {status}")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "publication": {"action": decision.action, "reason": decision.reason},
        "subjects": subjects,
        "reinstall": reinstall,
    }
    unsigned = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["record_sha256"] = hashlib.sha256(unsigned).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "record"))
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--index-url")
    parser.add_argument("--package")
    parser.add_argument("--version")
    parser.add_argument("--expected-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--status", choices=("uploaded", "noop", "failed"))
    parser.add_argument("--action")
    parser.add_argument("--reason")
    parser.add_argument("--reinstall", default="passed")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            if not all((args.index_url, args.package, args.version, args.expected_dir)):
                raise ValueError("preflight requires --index-url, --package, --version, and --expected-dir")
            expected = subject_digests(args.expected_dir)
            observed = query_simple_index(args.index_url, args.package, expected)
            decision = decide_publication(expected, observed)
            print(json.dumps({"action": decision.action, "reason": decision.reason}, sort_keys=True))
            return 0
        if not all((args.output, args.status, args.action, args.reason, args.expected_dir)):
            raise ValueError("record requires --output, --status, --action, --reason, and --expected-dir")
        decision = PublicationDecision(args.action, args.reason)
        write_release_record(args.output, status=args.status, decision=decision, subjects=subject_digests(args.expected_dir), reinstall=args.reinstall)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    print(f"release record written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
