"""CLI entrypoint for sdd commands."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from sdd_copilot.builder import build_next
from sdd_copilot.exceptions import SddError
from sdd_copilot.models import SpecStatus
from sdd_copilot.planner import plan_next
from sdd_copilot.runner import DEFAULT_MODEL
from sdd_copilot.spec_loader import load_spec_set

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with shared args on each subcommand."""
    # Shared options — defined once, inherited by every subcommand so that
    # ``sdd plan --spec-dir ./specs`` works (not just ``sdd --spec-dir ./specs plan``).
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--spec-dir",
        type=Path,
        default=Path("."),
        help="Path to the specs directory (default: cwd)",
    )
    shared.add_argument(
        "--spec",
        type=int,
        default=None,
        help="Target a specific spec number",
    )
    shared.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Copilot model (default: {DEFAULT_MODEL})",
    )
    shared.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Working directory for copilot build sessions",
    )
    shared.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )

    parser = argparse.ArgumentParser(
        prog="sdd",
        description="SDD Copilot — orchestrates Spec-Driven Development via Copilot CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("plan", parents=[shared], help="Plan the next spec into tasks")
    subparsers.add_parser("build", parents=[shared], help="Build the next planned spec, task by task")
    subparsers.add_parser("status", parents=[shared], help="Show status of all specs")
    subparsers.add_parser("run", parents=[shared], help="Plan + build in sequence, advancing through specs")

    return parser


def _configure_logging(verbosity: int) -> None:
    """Set up root logging based on ``-v`` / ``-vv`` flags."""
    level = logging.WARNING  # default
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        format="%(levelname)-8s %(name)s: %(message)s",
        level=level,
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_plan(args: argparse.Namespace) -> None:
    """Plan the next (or specified) spec into tasks."""
    spec_set = load_spec_set(args.spec_dir)
    task_list = plan_next(
        spec_set,
        spec_number=args.spec,
        model=args.model,
    )
    print(
        f"Planned spec {task_list.spec_number:02d} into "
        f"{len(task_list.tasks)} tasks → {task_list.path}"
    )


def _cmd_build(args: argparse.Namespace) -> None:
    """Build the next (or specified) planned spec, task by task."""
    spec_set = load_spec_set(args.spec_dir)
    passed = build_next(
        spec_set,
        spec_number=args.spec,
        model=args.model,
        project_dir=args.project_dir,
    )
    if not passed:
        print("Build completed but validation failed.")
        sys.exit(1)
    print("Build completed — validation passed.")


def _cmd_status(args: argparse.Namespace) -> None:
    """Print a table of spec statuses."""
    spec_set = load_spec_set(args.spec_dir)

    if not spec_set.specs:
        print("No specs found.")
        return

    # Column headers
    print(f"{'Spec':>4}  {'Title':<40}  {'Status':<10}  {'Deps'}")
    print(f"{'────':>4}  {'─────':<40}  {'──────':<10}  {'────'}")

    for number in spec_set.build_plan.order:
        spec = spec_set.specs.get(number)
        if spec is None:
            continue
        deps = ", ".join(f"{d:02d}" for d in spec.dependencies) if spec.dependencies else "—"
        title = spec.title[:40]
        print(f"{spec.number:4d}  {title:<40}  {spec.status.value:<10}  {deps}")


def _cmd_run(args: argparse.Namespace) -> None:
    """Plan + build in sequence, advancing through all specs."""
    spec_set = load_spec_set(args.spec_dir)

    for number in spec_set.build_plan.order:
        spec = spec_set.specs.get(number)
        if spec is None:
            continue

        if spec.status == SpecStatus.DONE:
            logger.info("Spec %02d already done — skipping", number)
            continue

        if spec.status == SpecStatus.PENDING:
            print(f"Planning spec {number:02d}: {spec.title}")
            plan_next(
                spec_set,
                spec_number=number,
                model=args.model,
            )
            # Reload to pick up the new status
            spec_set = load_spec_set(args.spec_dir)

        # Now the spec should be planned (or building from a previous run)
        spec = spec_set.specs.get(number)
        if spec is None:
            continue

        if spec.status == SpecStatus.BUILDING:
            print(
                f"Spec {number:02d} has status 'building' from a previous run "
                "— skipping. Use 'sdd build --spec {number}' to retry."
            )
            continue

        if spec.status != SpecStatus.PLANNED:
            logger.warning(
                "Spec %02d has unexpected status '%s' — skipping",
                number,
                spec.status.value,
            )
            continue

        print(f"Building spec {number:02d}: {spec.title}")
        passed = build_next(
            spec_set,
            spec_number=number,
            model=args.model,
            project_dir=args.project_dir,
        )

        if not passed:
            print(f"Spec {number:02d} validation failed — stopping.")
            sys.exit(1)

        # Reload for next iteration
        spec_set = load_spec_set(args.spec_dir)


_DISPATCH: dict[str, Callable[[argparse.Namespace], None]] = {
    "plan": _cmd_plan,
    "build": _cmd_build,
    "status": _cmd_status,
    "run": _cmd_run,
}


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    _configure_logging(getattr(args, "verbose", 0))
    logger.debug("args: %s", args)

    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except SddError as exc:
        logger.debug("SddError: %s", exc, exc_info=True)
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
