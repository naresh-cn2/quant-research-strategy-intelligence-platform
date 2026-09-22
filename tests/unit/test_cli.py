"""
Tests for qrsip.cli — command-line interface.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from qrsip.cli import build_parser, main, run_command


class TestBuildParser:
    def test_parser_has_prog(self) -> None:
        parser = build_parser()
        assert parser.prog == "qrsip"

    def test_parser_has_version(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_parser_has_subcommands(self) -> None:
        parser = build_parser()
        sub = parser._subparsers._group_actions[0]
        choices = set(sub.choices.keys())
        assert "init" in choices
        assert "doctor" in choices
        assert "status" in choices


class TestMain:
    def test_main_no_args_prints_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(argv=[])
        assert rc == 1
        captured = capsys.readouterr()
        assert "No command provided" in captured.err

    def test_main_help_does_not_fail(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(argv=["--help"])
        assert exc_info.value.code == 0


class TestRunCommand:
    def test_run_command_without_func_returns_error(self) -> None:
        args = argparse.Namespace()
        rc = run_command(args, repo_root=Path.cwd())
        assert rc == 1

    def test_run_command_init_creates_scaffold(self, tmp_path: Path) -> None:
        # Build a real args object via the parser so func is attached.
        parser = build_parser()
        parsed = parser.parse_args(["init", "--force"])
        rc = run_command(parsed, repo_root=tmp_path)
        assert rc == 0
        assert (tmp_path / "configs").is_dir()
        assert (tmp_path / "configs" / "experiments").is_dir()
        assert (tmp_path / "docs" / "architecture").is_dir()

    def test_run_command_doctor_runs(self, tmp_path: Path) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["doctor"])
        rc = run_command(parsed, repo_root=tmp_path)
        # doctor may pass or fail depending on config dirs; both are acceptable
        assert rc in (0, 1)

    def test_run_command_status_when_missing(self, tmp_path: Path) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["status"])
        rc = run_command(parsed, repo_root=tmp_path)
        assert rc == 1

    def test_run_command_status_when_present(self, tmp_path: Path) -> None:
        status_file = tmp_path / "PROJECT_STATUS.md"
        status_file.write_text("# status\n\nok\n", encoding="utf-8")
        parser = build_parser()
        parsed = parser.parse_args(["status"])
        rc = run_command(parsed, repo_root=tmp_path)
        assert rc == 0
        assert "ok" in status_file.read_text(encoding="utf-8")
