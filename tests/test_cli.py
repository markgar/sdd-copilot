"""Tests for sdd_copilot.cli — argument parsing, dispatch, and logging."""

import argparse
import logging
from io import StringIO
from unittest.mock import patch

import pytest

from sdd_copilot.cli import _build_parser, _configure_logging, main
from sdd_copilot.runner import DEFAULT_MODEL


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_plan_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert args.command == "plan"

    def test_build_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build"])
        assert args.command == "build"

    def test_status_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_run_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["run"])
        assert args.command == "run"

    def test_no_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_shared_spec_dir_after_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "--spec-dir", "/my/specs"])
        assert str(args.spec_dir) == "/my/specs"

    def test_shared_model_after_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "--model", "gpt-4"])
        assert args.model == "gpt-4"

    def test_shared_verbose_after_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "-v"])
        assert args.verbose == 1

    def test_double_verbose(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "-vv"])
        assert args.verbose == 2

    def test_spec_number_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "--spec", "5"])
        assert args.spec == 5

    def test_project_dir_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan", "--project-dir", "/proj"])
        assert str(args.project_dir) == "/proj"

    def test_default_model_from_runner(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert args.model == DEFAULT_MODEL

    def test_default_spec_dir_is_cwd(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert str(args.spec_dir) == "."


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def setup_method(self) -> None:
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
        root.setLevel(logging.WARNING)

    def test_default_is_warning(self) -> None:
        _configure_logging(0)
        assert logging.getLogger().level == logging.WARNING

    def test_v_sets_info(self) -> None:
        _configure_logging(1)
        assert logging.getLogger().level == logging.INFO

    def test_vv_sets_debug(self) -> None:
        _configure_logging(2)
        assert logging.getLogger().level == logging.DEBUG

    def test_vvv_still_debug(self) -> None:
        _configure_logging(3)
        assert logging.getLogger().level == logging.DEBUG


# ---------------------------------------------------------------------------
# main — dispatch
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_command_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "sdd" in captured.out.lower() or "usage" in captured.out.lower()

    def test_plan_command_runs_stub(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["plan"])
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out

    def test_build_command_runs_stub(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["build"])
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out

    def test_status_command_runs_stub(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["status"])
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out

    def test_run_command_runs_stub(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["run"])
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out
