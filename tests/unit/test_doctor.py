"""
Tests for qrsip.doctor — environment health checks (spec §41).
"""

from __future__ import annotations

from pathlib import Path

from qrsip.doctor import Doctor, DoctorCheck, DoctorResult


class TestDoctorCheck:
    def test_pending_describe(self) -> None:
        check = DoctorCheck(name="python", description="is python ok")
        assert check.status == "pending"
        assert "PENDING" in check.describe()

    def test_pass_describe(self) -> None:
        check = DoctorCheck(name="python", description="is python ok", status="pass", detail="3.12")
        assert "PASS" in check.describe()
        assert "3.12" in check.describe()

    def test_fail_describe(self) -> None:
        check = DoctorCheck(
            name="python", description="is python ok", status="fail", detail="too old"
        )
        assert "FAIL" in check.describe()
        assert "too old" in check.describe()


class TestDoctorResult:
    def test_pass_property(self) -> None:
        result = DoctorResult(checks=[DoctorCheck(name="x", description="x", status="pass")])
        result.overall = "pass"
        assert result.passed is True

    def test_fail_property(self) -> None:
        result = DoctorResult(checks=[DoctorCheck(name="x", description="x", status="fail")])
        result.overall = "fail"
        assert result.passed is False

    def test_summary_contains_overall(self) -> None:
        result = DoctorResult(checks=[])
        result.overall = "pass"
        summary = result.summary()
        assert "Overall: PASS" in summary


class TestDoctor:
    def test_run_produces_checks(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        checks = result.checks
        assert len(checks) >= 1
        names = {c.name for c in checks}
        assert "python_version" in names

    def test_python_check_passes_on_supported_version(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        python_check = next(c for c in result.checks if c.name == "python_version")
        assert python_check.status == "pass"

    def test_import_checks_include_required_modules(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        import_checks = [c for c in result.checks if c.name.startswith("import:")]
        names = {c.name for c in import_checks}
        assert "import:qrsip" in names
        assert "import:qrsip.config" in names
        assert "import:qrsip.errors" in names
        assert "import:qrsip.logging" in names

    def test_config_dir_check_passes_when_dirs_exist(self, tmp_path: Path) -> None:
        for sub in ("environments", "datasets", "strategies", "risk", "execution", "experiments"):
            (tmp_path / "configs" / sub).mkdir(parents=True, exist_ok=True)
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        config_check = next(c for c in result.checks if c.name == "config_directory")
        assert config_check.status == "pass"

    def test_config_dir_check_fails_when_missing(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        config_check = next(c for c in result.checks if c.name == "config_directory")
        assert config_check.status == "fail"

    def test_writable_check_passes_in_tmp(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        writable_check = next(c for c in result.checks if c.name == "filesystem_writable")
        assert writable_check.status == "pass"

    def test_git_check_passes_when_git_available(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        git_check = next(c for c in result.checks if c.name == "git_available")
        assert git_check.status == "pass"


class TestRunDoctor:
    def test_run_doctor_returns_result(self, tmp_path: Path) -> None:
        doctor = Doctor(repo_root=tmp_path)
        result = doctor.run()
        assert isinstance(result, DoctorResult)
        assert len(result.checks) >= 1
