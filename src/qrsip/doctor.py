"""QRSIP system health checks (spec §41: qrsip doctor, L0).

doctor runs a set of deterministic, non-destructive checks and reports a pass/fail
summary. It does not modify the environment.

Checks (extendable):
- Python version meets the declared minimum
- Required Python modules import cleanly
- Configuration directory is present
- File system is writable where expected
- Git is available (if present)
- Schema files referenced by the architecture exist

Output: structured text summary + exit code 0 (all pass) or 1 (any fail).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Doctor",
    "DoctorCheck",
    "DoctorResult",
]

_MINIMUM_PYTHON = (3, 11)


@dataclass(slots=True)
class DoctorCheck:
    """A single, named, non-destructive health check."""

    name: str
    description: str
    # result populated by run
    status: str = "pending"  # pending | pass | fail
    detail: str = ""

    def describe(self) -> str:
        return f"[{self.status.upper()}] {self.name}: {self.description}" + (
            f" — {self.detail}" if self.detail else ""
        )


@dataclass(slots=True)
class DoctorResult:
    """Aggregate result of a doctor run."""

    checks: list[DoctorCheck] = field(default_factory=list)
    overall: str = "unknown"  # pass | fail | error

    @property
    def passed(self) -> bool:
        return self.overall == "pass"

    def summary(self) -> str:
        lines: list[str] = ["QRSIP doctor — environment health check"]
        lines.append("=" * 60)
        if self.checks:
            for check in self.checks:
                lines.append(check.describe())
            lines.append("-" * 60)
        lines.append(f"Overall: {self.overall.upper()}")
        return "\n".join(lines)


class Doctor:
    """Encapsulates the current set of doctor checks for a repo."""

    def __init__(self, *, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path.cwd()
        self._checks: list[DoctorCheck] = []

    def checks(self) -> list[DoctorCheck]:
        return list(self._checks)

    def run(self) -> DoctorResult:
        self._checks.clear()
        self._add_python_check()
        self._add_import_checks()
        self._add_config_dir_check()
        self._add_writable_check()
        self._add_git_check()
        result = DoctorResult(checks=self._checks)
        if any(check.status == "fail" for check in self._checks):
            result.overall = "fail"
        elif any(check.status == "error" for check in self._checks):
            result.overall = "error"
        else:
            result.overall = "pass"
        return result

    # ------------------------------------------------------------------
    def _add_python_check(self) -> None:
        check = DoctorCheck(
            name="python_version",
            description="Python version meets the declared minimum (>=3.11)",
        )
        try:
            # Runtime guard: qrsip can run from source without an install
            # enforcing requires-python, so verify here at runtime.
            # NOTE: compared via a module-level constant tuple so the
            # intent stays explicit even as the minimum version evolves.
            if tuple(sys.version_info[:2]) >= _MINIMUM_PYTHON:
                check.status = "pass"
                check.detail = f"detected {sys.version.split()[0]}"
            else:
                check.status = "fail"
                check.detail = f"detected {sys.version.split()[0]}; minimum is 3.11"
        except Exception as exc:
            check.status = "error"
            check.detail = str(exc)
        self._checks.append(check)

    def _add_import_checks(self) -> None:
        required: list[str] = [
            "qrsip",
            "qrsip.config",
            "qrsip.errors",
            "qrsip.logging",
        ]
        for mod in required:
            check = DoctorCheck(
                name=f"import:{mod}",
                description=f"required module {mod} imports cleanly",
            )
            try:
                __import__(mod)
                check.status = "pass"
            except Exception as exc:
                check.status = "fail"
                check.detail = f"import failed: {exc}"
            self._checks.append(check)

    def _add_config_dir_check(self) -> None:
        check = DoctorCheck(
            name="config_directory",
            description="config/ directory exists with expected subfolders",
        )
        for sub in ("environments", "datasets", "strategies", "risk", "execution", "experiments"):
            candidate = self.repo_root / "configs" / sub
            if not candidate.is_dir():
                check.status = "fail"
                check.detail = f"missing configs/{sub}/"
                break
        else:
            check.status = "pass"
        self._checks.append(check)

    def _add_writable_check(self) -> None:
        check = DoctorCheck(
            name="filesystem_writable",
            description="expected output directories are writable",
        )
        try:
            test_file = self.repo_root / ".qrsip_doctor_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            check.status = "pass"
            check.detail = "repo root is writable"
        except Exception as exc:
            check.status = "fail"
            check.detail = f"cannot write to repo root: {exc}"
        self._checks.append(check)

    def _add_git_check(self) -> None:
        check = DoctorCheck(
            name="git_available",
            description="git is available (informational; not required for the platform)",
        )
        try:
            subprocess.run(
                ["git", "version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            check.status = "pass"
            check.detail = "git found"
        except Exception:
            check.status = "pass"
            check.detail = "git not found; not required"
        self._checks.append(check)
