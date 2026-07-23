"""Fail when tracked source contains common live credential formats."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{32,}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def main() -> int:
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.split(b"\0")
    findings: list[str] = []
    for encoded in files:
        if not encoded:
            continue
        relative = Path(encoded.decode("utf-8"))
        try:
            content = (ROOT / relative).read_bytes()
        except OSError:
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{relative}: possible {name}")
    for finding in findings:
        print(finding)
    if findings:
        return 1
    print(f"secret scan passed ({len(files) - 1} tracked paths checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
