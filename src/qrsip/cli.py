"""QRSIP command-line interface (L7 Presentation).

Canonical entry point::

    qrsip

Derived from the registered script entry point in pyproject.toml::

    qrsip = "qrsip.cli:main"

A small, explicit CLI using argparse. It is intentionally minimal: commands are
added as the platform grows. No interactive features, no hidden magic.

Public commands:
- qrsip init        — create a local project scaffold in an existing repo
- qrsip doctor      — run health checks
- qrsip status      — show current PROJECT_STATUS.md if present
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qrsip.doctor import Doctor

__all__ = ["build_parser", "main", "run_command"]


def build_parser() -> argparse.ArgumentParser:
    """Build the public QRSIP argument parser."""
    parser = argparse.ArgumentParser(
        prog="qrsip",
        description="QRSIP — Quantitative Research & Strategy Intelligence Platform CLI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    sub = parser.add_subparsers(dest="command", help="available commands")

    _build_init_parser(sub)
    _build_doctor_parser(sub)
    _build_status_parser(sub)

    return parser


def _build_init_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("init", help="initialize a QRSIP project scaffold")
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing scaffold files where safe",
    )
    p.set_defaults(func=_cmd_init)


def _build_doctor_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "doctor",
        help="run environment health checks (non-destructive)",
    )
    p.set_defaults(func=_cmd_doctor)


def _build_status_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "status",
        help="show the current PROJECT_STATUS.md if present",
    )
    p.set_defaults(func=_cmd_status)


def run_command(args: argparse.Namespace, *, repo_root: Path | None = None) -> int:
    """Dispatch a parsed CLI command to its handler."""
    repo_root = repo_root or Path.cwd()
    func = getattr(args, "func", None)
    if func is None:
        print("No command provided. Use --help for usage.", file=sys.stderr)
        return 1
    try:
        result: int = func(args, repo_root=repo_root)
        return result
    except KeyboardInterrupt:
        return 130


def main(argv: list[str] | None = None) -> int:
    """Entry point for the qrsip console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_command(args)


# ------------------------------------------------------------------
# Command implementations
# ------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace, *, repo_root: Path) -> int:
    """Create an initial scaffold: configs/, examples/, docs skeleton.

    The operation is idempotent where possible and never touches existing
    source code.
    """
    scaffold = [
        ("configs", True),
        ("configs/environments", True),
        ("configs/datasets", True),
        ("configs/strategies", True),
        ("configs/risk", True),
        ("configs/execution", True),
        ("configs/experiments", True),
        ("examples", True),
        ("docs/architecture", True),
        ("docs/specifications", True),
        ("docs/research-methodology", True),
        ("docs/operations", True),
        ("docs/security", True),
        ("docs/decisions", True),
        ("reports", True),
        ("scripts", True),
        ("migrations", True),
        ("notebooks", True),
        ("data/README.md", False),
    ]

    for path, is_dir in scaffold:
        full = repo_root / path
        if is_dir:
            full.mkdir(parents=True, exist_ok=True)
        else:
            full.parent.mkdir(parents=True, exist_ok=True)
            if not full.exists() or getattr(args, "force", False):
                full.write_text(
                    "# QRSIP data directory\n\nSee docs/data_strategy.md.\n", encoding="utf-8"
                )

    print(f"scaffold initialized at {repo_root}")
    return 0


def _cmd_doctor(args: argparse.Namespace, *, repo_root: Path) -> int:
    """Run health checks and print the result."""
    doctor = Doctor(repo_root=repo_root)
    result = doctor.run()
    print(result.summary())
    return 0 if result.passed else 1


def _cmd_status(args: argparse.Namespace, *, repo_root: Path) -> int:
    """Print PROJECT_STATUS.md if it exists."""
    path = repo_root / "PROJECT_STATUS.md"
    if not path.is_file():
        print("PROJECT_STATUS.md not found at repo root", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0
