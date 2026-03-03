"""CLI entrypoint for sdd commands."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from collections.abc import Callable

from sdd_copilot.runner import DEFAULT_MODEL


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
# Subcommand handlers (stubs — wired up in later stories)
# ---------------------------------------------------------------------------

def _cmd_plan(args: argparse.Namespace) -> None:
    print("Command 'plan' is not yet implemented.")


def _cmd_build(args: argparse.Namespace) -> None:
    print("Command 'build' is not yet implemented.")


def _cmd_status(args: argparse.Namespace) -> None:
    print("Command 'status' is not yet implemented.")


def _cmd_run(args: argparse.Namespace) -> None:
    print("Command 'run' is not yet implemented.")


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

    handler(args)


if __name__ == "__main__":
    main()
