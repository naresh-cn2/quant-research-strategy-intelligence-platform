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


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers (mirrored from pyproject.toml)."""
    config.addinivalue_line(
        "markers", "adversarial: tests that deliberately attempt to break the system"
    )
    config.addinivalue_line("markers", "acceptance: end-to-end acceptance tests")
    config.addinivalue_line("markers", "contract: tests against external contracts (P01)")
    config.addinivalue_line("markers", "integration: cross-module integration tests")
    config.addinivalue_line("markers", "property: invariant/property-based tests")
    config.addinivalue_line("markers", "regression: regression tests for fixed defects")
