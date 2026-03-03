"""Tests for sdd_copilot.cli — argument parsing, dispatch, and logging."""

import argparse
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd_copilot.cli import _build_parser, _configure_logging, main
from sdd_copilot.exceptions import (
    BuilderError,
    ConstitutionMissingError,
    PlannerError,
)
from sdd_copilot.models import (
    BuildPlan,
    Constitution,
    Spec,
    SpecSet,
    SpecStatus,
    Task,
    TaskList,
)
from sdd_copilot.runner import DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec_dir(tmp_path: Path) -> Path:
    """Create a minimal spec directory with constitution, README, and one spec."""
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "CONSTITUTION.md").write_text("Be good.\n")
    (spec_dir / "README.md").write_text("01-foundation\n02-api\n")
    (spec_dir / "01-foundation.md").write_text(
        "# Foundation\n\n## Summary\nSetup.\n\n## What to Build\nDo stuff.\n"
    )
    (spec_dir / "02-api.md").write_text(
        "# API\n\n## Summary\nAPI.\n\n## What to Build\nBuild API.\n"
        "## Dependencies\n**Spec 1**\n"
    )
    return spec_dir


def _make_spec_set(spec_dir: Path | None = None) -> SpecSet:
    """Build a minimal SpecSet for testing."""
    d = spec_dir or Path("/fake")
    return SpecSet(
        specs={
            1: Spec(
                number=1,
                slug="foundation",
                title="Foundation",
                path=d / "01-foundation.md",
                sections={"Summary": "Setup."},
                status=SpecStatus.DONE,
            ),
            2: Spec(
                number=2,
                slug="api",
                title="API",
                path=d / "02-api.md",
                sections={"Summary": "API."},
                dependencies=(1,),
                status=SpecStatus.PENDING,
            ),
        },
        constitution=Constitution(path=d / "CONSTITUTION.md", content="Be good."),
        build_plan=BuildPlan(order=(1, 2)),
        research_docs={},
        spec_dir=d,
    )


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

    def test_sdd_error_prints_to_stderr_and_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("sdd_copilot.cli.load_spec_set") as mock_load:
            mock_load.side_effect = ConstitutionMissingError(Path("/fake"))
            with pytest.raises(SystemExit) as exc_info:
                main(["status", "--spec-dir", "/fake"])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "CONSTITUTION.md" in captured.err


# ---------------------------------------------------------------------------
# _cmd_status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def test_status_prints_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_dir = _make_spec_dir(tmp_path)
        main(["status", "--spec-dir", str(spec_dir)])
        captured = capsys.readouterr()
        assert "Foundation" in captured.out
        assert "API" in captured.out
        assert "pending" in captured.out
        assert "Spec" in captured.out
        assert "Status" in captured.out

    def test_status_shows_deps(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_dir = _make_spec_dir(tmp_path)
        main(["status", "--spec-dir", str(spec_dir)])
        captured = capsys.readouterr()
        assert "01" in captured.out  # dep of spec 02

    def test_status_with_done_spec(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_dir = _make_spec_dir(tmp_path)
        status_file = spec_dir / ".sdd-status.json"
        status_file.write_text(json.dumps({"1": "done"}))
        main(["status", "--spec-dir", str(spec_dir)])
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_status_no_specs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_dir = tmp_path / "empty"
        spec_dir.mkdir()
        (spec_dir / "CONSTITUTION.md").write_text("Be good.\n")
        main(["status", "--spec-dir", str(spec_dir)])
        captured = capsys.readouterr()
        assert "No specs found" in captured.out


# ---------------------------------------------------------------------------
# _cmd_plan
# ---------------------------------------------------------------------------


class TestCmdPlan:
    def test_plan_calls_plan_next(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_set = _make_spec_set()
        task_list = TaskList(
            spec_number=2,
            tasks=(Task(number=1, title="Do it", description="d", acceptance_criteria="ac"),),
            path=Path("/fake/tasks/tasks-02.md"),
        )
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=spec_set),
            patch("sdd_copilot.cli.plan_next", return_value=task_list) as mock_plan,
        ):
            main(["plan", "--spec-dir", "/fake", "--spec", "2"])
            mock_plan.assert_called_once_with(
                spec_set, spec_number=2, model=DEFAULT_MODEL,
            )
        captured = capsys.readouterr()
        assert "Planned spec 02" in captured.out
        assert "1 tasks" in captured.out

    def test_plan_error_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sdd_copilot.cli.load_spec_set") as mock_load:
            mock_load.side_effect = ConstitutionMissingError(Path("/fake"))
            with pytest.raises(SystemExit) as exc_info:
                main(["plan", "--spec-dir", "/fake"])
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _cmd_build
# ---------------------------------------------------------------------------


class TestCmdBuild:
    def test_build_calls_build_next_success(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_set = _make_spec_set()
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=spec_set),
            patch("sdd_copilot.cli.build_next", return_value=True) as mock_build,
        ):
            main(["build", "--spec-dir", "/fake", "--spec", "2", "--project-dir", "/proj"])
            mock_build.assert_called_once_with(
                spec_set,
                spec_number=2,
                model=DEFAULT_MODEL,
                project_dir=Path("/proj"),
            )
        captured = capsys.readouterr()
        assert "validation passed" in captured.out

    def test_build_validation_failure_exits_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec_set = _make_spec_set()
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=spec_set),
            patch("sdd_copilot.cli.build_next", return_value=False),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["build", "--spec-dir", "/fake"])
            assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "validation failed" in captured.out

    def test_build_sdd_error_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("sdd_copilot.cli.load_spec_set") as mock_load,
        ):
            mock_load.side_effect = BuilderError(Path("/fake"), "no task file")
            with pytest.raises(SystemExit) as exc_info:
                main(["build", "--spec-dir", "/fake"])
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _cmd_run
# ---------------------------------------------------------------------------


class TestCmdRun:
    def test_run_skips_done_specs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All specs done → no calls to plan or build."""
        d = Path("/fake")
        spec_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.DONE,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1,)),
            research_docs={},
            spec_dir=d,
        )
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=spec_set),
            patch("sdd_copilot.cli.plan_next") as mock_plan,
            patch("sdd_copilot.cli.build_next") as mock_build,
        ):
            main(["run", "--spec-dir", "/fake"])
            mock_plan.assert_not_called()
            mock_build.assert_not_called()

    def test_run_plans_then_builds(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        d = Path("/fake")
        pending_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.PENDING,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1,)),
            research_docs={},
            spec_dir=d,
        )
        planned_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.PLANNED,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1,)),
            research_docs={},
            spec_dir=d,
        )
        done_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.DONE,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1,)),
            research_docs={},
            spec_dir=d,
        )
        # load_spec_set called 3 times: initial, after plan, after build
        with (
            patch(
                "sdd_copilot.cli.load_spec_set",
                side_effect=[pending_set, planned_set, done_set],
            ),
            patch("sdd_copilot.cli.plan_next") as mock_plan,
            patch("sdd_copilot.cli.build_next", return_value=True) as mock_build,
        ):
            main(["run", "--spec-dir", "/fake"])
            mock_plan.assert_called_once()
            mock_build.assert_called_once()

    def test_run_stops_on_build_failure(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        d = Path("/fake")
        planned_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.PLANNED,
                ),
                2: Spec(
                    number=2, slug="b", title="B", path=d / "02-b.md",
                    sections={}, status=SpecStatus.PENDING,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1, 2)),
            research_docs={},
            spec_dir=d,
        )
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=planned_set),
            patch("sdd_copilot.cli.build_next", return_value=False),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["run", "--spec-dir", "/fake"])
            assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "validation failed" in captured.out

    def test_run_skips_building_status(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Specs with status 'building' are skipped with a message."""
        d = Path("/fake")
        spec_set = SpecSet(
            specs={
                1: Spec(
                    number=1, slug="a", title="A", path=d / "01-a.md",
                    sections={}, status=SpecStatus.BUILDING,
                ),
            },
            constitution=Constitution(path=d / "CONSTITUTION.md", content="ok"),
            build_plan=BuildPlan(order=(1,)),
            research_docs={},
            spec_dir=d,
        )
        with (
            patch("sdd_copilot.cli.load_spec_set", return_value=spec_set),
            patch("sdd_copilot.cli.plan_next") as mock_plan,
            patch("sdd_copilot.cli.build_next") as mock_build,
        ):
            main(["run", "--spec-dir", "/fake"])
            mock_plan.assert_not_called()
            mock_build.assert_not_called()
        captured = capsys.readouterr()
        assert "building" in captured.out


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestParserDefaults:
    def test_default_spec_is_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert args.spec is None

    def test_default_project_dir_is_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert args.project_dir is None

    def test_default_verbose_is_zero(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["plan"])
        assert args.verbose == 0

    def test_all_subcommands_have_shared_args(self) -> None:
        parser = _build_parser()
        for cmd in ("plan", "build", "status", "run"):
            args = parser.parse_args([cmd, "--spec-dir", "/x", "--model", "m", "-v"])
            assert str(args.spec_dir) == "/x"
            assert args.model == "m"
            assert args.verbose == 1
