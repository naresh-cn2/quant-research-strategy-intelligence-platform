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
import json
import sys
from pathlib import Path

from qrsip.doctor import Doctor
from qrsip.domain.results import PromotionDecision
from qrsip.errors import PromotionGateError, QRSIPError
from qrsip.infrastructure.storage import FileStorage
from qrsip.intelligence import (
    load_experiment_settings,
    rerun_experiment,
    run_experiment,
)

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
    _build_experiment_parser(sub)
    _build_report_parser(sub)
    _build_promote_parser(sub)

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


def _build_experiment_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("experiment", help="run or reproduce a research experiment")
    nested = p.add_subparsers(dest="experiment_command", required=True)
    run = nested.add_parser("run", help="run a YAML experiment")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    run.set_defaults(func=_cmd_experiment_run)
    rerun = nested.add_parser("rerun", help="re-run a recorded experiment")
    rerun.add_argument("--experiment-id", required=True)
    rerun.add_argument("--config", type=Path, required=True)
    rerun.add_argument("--base-dir", type=Path)
    rerun.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    rerun.set_defaults(func=_cmd_experiment_rerun)


def _build_report_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("report", help="show a recorded research report")
    nested = p.add_subparsers(dest="report_command", required=True)
    show = nested.add_parser("show", help="show Markdown or JSON report data")
    show.add_argument("--experiment-id", required=True)
    show.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    show.add_argument("--format", choices=("markdown", "json"), default="markdown")
    show.set_defaults(func=_cmd_report_show)


def _build_promote_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("promote", help="record a human promotion decision")
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--decision", choices=("APPROVE", "REJECT"), required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    p.set_defaults(func=_cmd_promote)


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


def _storage(args: argparse.Namespace, repo_root: Path) -> FileStorage:
    return FileStorage(
        args.artifacts if args.artifacts.is_absolute() else repo_root / args.artifacts
    )


def _cmd_experiment_run(args: argparse.Namespace, *, repo_root: Path) -> int:
    config_path = args.config if args.config.is_absolute() else repo_root / args.config
    settings = load_experiment_settings(config_path)
    run = run_experiment(settings, base_dir=repo_root, storage=_storage(args, repo_root))
    print(run.result_digest)
    return 0


def _cmd_experiment_rerun(args: argparse.Namespace, *, repo_root: Path) -> int:
    config_path = args.config if args.config.is_absolute() else repo_root / args.config
    settings = load_experiment_settings(config_path)
    if settings.id != args.experiment_id:
        raise QRSIPError("configuration experiment_id does not match --experiment-id")
    base_dir = args.base_dir or repo_root
    if not base_dir.is_absolute():
        base_dir = repo_root / base_dir
    replay = rerun_experiment(
        settings,
        base_dir=base_dir,
        storage=_storage(args, repo_root),
    )
    print(replay.result_digest)
    return 0


def _cmd_report_show(args: argparse.Namespace, *, repo_root: Path) -> int:
    storage = _storage(args, repo_root)
    key = f"experiments/{args.experiment_id}/run.json"
    payload = storage.read_json(key)
    if not isinstance(payload, dict):
        raise QRSIPError("stored report artifact is not a JSON object")
    if args.format == "json":
        promotion_key = f"experiments/{args.experiment_id}/promotion.json"
        if storage.exists(promotion_key):
            payload["promotion"] = storage.read_json(promotion_key)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        markdown = storage.read_text(f"experiments/{args.experiment_id}/report.md")
        promotion_key = f"experiments/{args.experiment_id}/promotion.json"
        if storage.exists(promotion_key):
            promotion = storage.read_json(promotion_key)
            decision = (
                promotion.get("decision", "PENDING") if isinstance(promotion, dict) else "PENDING"
            )
            markdown = markdown.replace(
                "- Human decision: PENDING", f"- Human decision: {decision}"
            )
        print(markdown, end="")
    return 0


def _cmd_promote(args: argparse.Namespace, *, repo_root: Path) -> int:
    if not args.reviewer.strip() or not args.rationale.strip():
        raise PromotionGateError("reviewer and rationale are required for a human decision")
    storage = _storage(args, repo_root)
    payload = storage.read_json(f"experiments/{args.experiment_id}/run.json")
    if not isinstance(payload, dict):
        raise QRSIPError("stored experiment artifact is not a JSON object")
    validation = payload.get("validation")
    raw_checks = validation.get("checks", []) if isinstance(validation, dict) else []
    statuses = [item.get("status", "FAIL") for item in raw_checks if isinstance(item, dict)]
    gate = "PASS" if statuses and all(status == "PASS" for status in statuses) else "FAIL"
    gates = {"validation": gate}
    if args.decision == "APPROVE" and gate != "PASS":
        raise PromotionGateError(
            "cannot approve an experiment without passing validation", gates=gates
        )
    decision = PromotionDecision(
        id=f"PROMO-{args.experiment_id}",
        experiment_id=args.experiment_id,
        decision=args.decision,
        gates=gates,
        decided_by=args.reviewer,
        rationale=args.rationale,
    )
    storage.write_json(
        f"experiments/{args.experiment_id}/promotion.json", decision.model_dump(mode="json")
    )
    print(args.decision)
    return 0
