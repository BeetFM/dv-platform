"""Stable repository and fixture roots for reorganized tests."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPOSITORY_ROOT / "tests" / "fixtures"
MUTATIONS_ROOT = FIXTURES_ROOT / "mutations"
