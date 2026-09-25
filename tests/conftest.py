# QRSIP — tests/conftest.py
#
# Pytest fixtures and configuration shared across the test suite.
#
# Design:
# - Fixtures are organized by layer, mirroring the architecture.
# - No fixture imports domain logic unnecessarily.
# - Tests remain deterministic and hermetic.
"""
Pytest configuration and shared fixtures for QRSIP.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the package is importable in tests by adding src to sys.path when
# running without an editable install.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the documented test-tier marker from the test directory."""
    markers = {
        "integration": "integration",
        "contract": "contract",
        "property": "property",
        "regression": "regression",
        "adversarial": "adversarial",
        "acceptance": "acceptance",
    }
    for item in items:
        try:
            relative = item.path.relative_to(_REPO_ROOT)
        except ValueError:
            continue
        if len(relative.parts) >= 2 and relative.parts[0] == "tests":
            marker_name = markers.get(relative.parts[1])
            if marker_name is not None:
                item.add_marker(getattr(pytest.mark, marker_name))
