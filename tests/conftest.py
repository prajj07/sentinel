"""Shared pytest fixtures for integration tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def reset_inventory() -> None:
    """Restore seeded stock after chaos scenarios and prior test runs."""
    subprocess.run(
        ["docker", "compose", "run", "--rm", "seed"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
