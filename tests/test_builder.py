"""Tests for sdd_copilot.builder — task-file reading, validation, and build_next orchestration."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from sdd_copilot.exceptions import BuilderError, SpecNotFoundError
from sdd_copilot.models import (
    BuildPlan,
    Constitution,
    Spec,
    SpecSet,
    SpecStatus,
    Task,
    TaskList,
)
from sdd_copilot.builder import _read_task_file, _run_validation, build_next
from sdd_copilot.runner import CopilotResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TASK_FILE = """\
# Tasks: Spec 01 — Test Spec

## Task 1: Setup project
### Description
Create project structure
### Acceptance Criteria
GIVEN setup WHEN run THEN works

## Task 2: Implement core
### Description
Build the core module
### Acceptance Criteria
GIVEN core WHEN tested THEN passes
"""


def _make_spec(
    number: int = 1,
    status: SpecStatus = SpecStatus.PLANNED,
    sections: dict[str, str] | None = None,
) -> Spec:
    default_sections = {"Summary": "summary", "What to Build": "stuff"}
    if sections is not None:
        default_sections.update(sections)
    return Spec(
        number=number,
        slug="test",
        title="Test Spec",
        path=Path(f"/specs/{number:02d}-test.md"),
        sections=default_sections,
        status=status,
    )


def _make_spec_set(
    specs: dict[int, Spec] | None = None,
    spec_dir: Path | None = None,
) -> SpecSet:
    if specs is None:
        specs = {1: _make_spec()}
    return SpecSet(
        specs=specs,
        constitution=Constitution(path=Path("/c.md"), content="Be good."),
        build_plan=BuildPlan(order=tuple(specs.keys())),
        research_docs={},
        spec_dir=spec_dir or Path("/specs"),
    )


def _write_task_file(spec_dir: Path, spec_number: int, content: str) -> Path:
    """Helper to write a task file under spec_dir/tasks/."""
    tasks_dir = spec_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"tasks-{spec_number:02d}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _read_task_file
# ---------------------------------------------------------------------------


class TestReadTaskFile:
    def test_reads_valid_task_file(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)
        result = _read_task_file(tmp_path, 1)
        assert isinstance(result, TaskList)
        assert result.spec_number == 1
        assert len(result.tasks) == 2
        assert result.tasks[0].title == "Setup project"
        assert result.tasks[1].title == "Implement core"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(BuilderError, match="Task file not found"):
            _read_task_file(tmp_path, 1)

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, "   \n  ")
        with pytest.raises(BuilderError, match="Task file is empty"):
            _read_task_file(tmp_path, 1)

    def test_unparseable_file_raises(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, "No task headings here")
        with pytest.raises(BuilderError, match="No tasks found"):
            _read_task_file(tmp_path, 1)

    def test_unparseable_chains_cause(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, "No task headings here")
        with pytest.raises(BuilderError) as exc_info:
            _read_task_file(tmp_path, 1)
        assert exc_info.value.__cause__ is not None

    def test_returns_tuple_of_tasks(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)
        result = _read_task_file(tmp_path, 1)
        assert isinstance(result.tasks, tuple)

    def test_correct_path_in_result(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)
        result = _read_task_file(tmp_path, 1)
        assert result.path == tmp_path / "tasks" / "tasks-01.md"


# ---------------------------------------------------------------------------
# _run_validation
# ---------------------------------------------------------------------------


class TestRunValidation:
    @patch("sdd_copilot.builder.subprocess.run")
    def test_passes_on_zero_exit(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        spec = _make_spec(sections={"Validation Command": "pytest tests/"})
        assert _run_validation(spec, Path("/project")) is True

    @patch("sdd_copilot.builder.subprocess.run")
    def test_fails_on_nonzero_exit(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        spec = _make_spec(sections={"Validation Command": "pytest tests/"})
        assert _run_validation(spec, Path("/project")) is False

    def test_no_validation_command_returns_true(self) -> None:
        spec = _make_spec()
        assert _run_validation(spec, Path("/project")) is True

    def test_empty_validation_command_returns_true(self) -> None:
        spec = _make_spec(sections={"Validation Command": "   "})
        assert _run_validation(spec, Path("/project")) is True

    @patch("sdd_copilot.builder.subprocess.run")
    def test_uses_shell_with_correct_cwd(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        spec = _make_spec(sections={"Validation Command": "make test"})
        _run_validation(spec, Path("/my-project"))
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["shell"] is True
        assert kwargs["cwd"] == Path("/my-project")

    @patch("sdd_copilot.builder.subprocess.run")
    def test_timeout_raises_builder_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
        spec = _make_spec(sections={"Validation Command": "slow-test"})
        with pytest.raises(BuilderError, match="timed out"):
            _run_validation(spec, Path("/project"))

    @patch("sdd_copilot.builder.subprocess.run")
    def test_timeout_chains_cause(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
        spec = _make_spec(sections={"Validation Command": "slow-test"})
        with pytest.raises(BuilderError) as exc_info:
            _run_validation(spec, Path("/project"))
        assert exc_info.value.__cause__ is not None

    @patch("sdd_copilot.builder.subprocess.run")
    def test_oserror_raises_builder_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("No such command")
        spec = _make_spec(sections={"Validation Command": "bad-cmd"})
        with pytest.raises(BuilderError, match="Validation failed to start"):
            _run_validation(spec, Path("/project"))

    @patch("sdd_copilot.builder.subprocess.run")
    def test_oserror_chains_cause(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("No such command")
        spec = _make_spec(sections={"Validation Command": "bad-cmd"})
        with pytest.raises(BuilderError) as exc_info:
            _run_validation(spec, Path("/project"))
        assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# build_next — happy path
# ---------------------------------------------------------------------------


class TestBuildNextHappyPath:
    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_builds_next_planned_spec(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        result = build_next(ss)

        assert result is True
        # Status should have been set to BUILDING then DONE
        assert mock_set_status.call_args_list == [
            call(tmp_path, 1, SpecStatus.BUILDING),
            call(tmp_path, 1, SpecStatus.DONE),
        ]

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_calls_copilot_for_each_task(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss)

        # Two tasks → two copilot invocations
        assert mock_run.call_count == 2

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_builds_specific_spec_number(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 2, VALID_TASK_FILE)

        spec2 = _make_spec(number=2)
        ss = _make_spec_set(
            specs={1: _make_spec(number=1, status=SpecStatus.DONE), 2: spec2},
            spec_dir=tmp_path,
        )
        result = build_next(ss, spec_number=2)
        assert result is True

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_uses_project_dir_as_working_dir(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        project = tmp_path / "project"
        project.mkdir()
        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss, project_dir=project)

        # All copilot calls should use project_dir
        for c in mock_run.call_args_list:
            assert c.kwargs.get("working_dir") == project

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_defaults_working_dir_to_spec_dir(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss)

        for c in mock_run.call_args_list:
            assert c.kwargs.get("working_dir") == tmp_path


# ---------------------------------------------------------------------------
# build_next — validation failure
# ---------------------------------------------------------------------------


class TestBuildNextValidationFailure:
    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_returns_false_on_validation_failure(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = False
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        result = build_next(ss)

        assert result is False

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_status_stays_building_on_validation_failure(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = False
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss)

        # Only set to BUILDING, never to DONE
        assert mock_set_status.call_args_list == [
            call(tmp_path, 1, SpecStatus.BUILDING),
        ]


# ---------------------------------------------------------------------------
# build_next — error cases
# ---------------------------------------------------------------------------


class TestBuildNextErrors:
    def test_no_planned_specs_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(
            specs={1: _make_spec(status=SpecStatus.DONE)},
            spec_dir=tmp_path,
        )
        with pytest.raises(BuilderError, match="No planned specs"):
            build_next(ss)

    def test_specific_spec_not_planned_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(
            specs={1: _make_spec(status=SpecStatus.PENDING)},
            spec_dir=tmp_path,
        )
        with pytest.raises(BuilderError, match="expected 'planned'"):
            build_next(ss, spec_number=1)

    def test_spec_not_found_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(SpecNotFoundError):
            build_next(ss, spec_number=99)

    def test_missing_task_file_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(BuilderError, match="Task file not found"):
            build_next(ss)

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_continues_after_task_failure(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A failed copilot task logs a warning but continues to the next task."""
        mock_run.return_value = CopilotResult(exit_code=1)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        # Should NOT raise — continues through all tasks
        result = build_next(ss)

        # Both tasks were attempted
        assert mock_run.call_count == 2
        # Validation still ran and passed
        assert result is True


# ---------------------------------------------------------------------------
# build_next — copilot invocation details
# ---------------------------------------------------------------------------


class TestBuildNextCopilotArgs:
    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_passes_model(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss, model="gpt-4o")

        for c in mock_run.call_args_list:
            assert c.kwargs.get("model") == "gpt-4o"

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_passes_spec_dir_as_extra_dir(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss)

        for c in mock_run.call_args_list:
            assert c.kwargs.get("extra_dirs") == (tmp_path,)

    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_does_not_capture_output(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Build tasks use live output (capture=False is the default)."""
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 1, VALID_TASK_FILE)

        ss = _make_spec_set(spec_dir=tmp_path)
        build_next(ss)

        for c in mock_run.call_args_list:
            # capture should not be passed (defaults to False in runner)
            assert "capture" not in c.kwargs or c.kwargs["capture"] is False


# ---------------------------------------------------------------------------
# _read_task_file — additional edge cases
# ---------------------------------------------------------------------------


class TestReadTaskFileEdgeCases:
    def test_correct_spec_number_in_result(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 3, VALID_TASK_FILE)
        result = _read_task_file(tmp_path, 3)
        assert result.spec_number == 3

    def test_path_includes_spec_number(self, tmp_path: Path) -> None:
        _write_task_file(tmp_path, 5, VALID_TASK_FILE)
        result = _read_task_file(tmp_path, 5)
        assert "tasks-05.md" in result.path.name


# ---------------------------------------------------------------------------
# build_next — auto spec selection
# ---------------------------------------------------------------------------


class TestBuildNextAutoSelection:
    @patch("sdd_copilot.builder._run_validation")
    @patch("sdd_copilot.builder.set_status")
    @patch("sdd_copilot.builder.run_copilot")
    def test_picks_first_planned_in_build_order(
        self,
        mock_run: MagicMock,
        mock_set_status: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0)
        mock_validate.return_value = True
        _write_task_file(tmp_path, 2, VALID_TASK_FILE)

        spec1 = _make_spec(number=1, status=SpecStatus.DONE)
        spec2 = _make_spec(number=2, status=SpecStatus.PLANNED)
        ss = _make_spec_set(specs={1: spec1, 2: spec2}, spec_dir=tmp_path)
        result = build_next(ss)
        assert result is True
        # set_status called with spec 2
        assert mock_set_status.call_args_list[0] == call(tmp_path, 2, SpecStatus.BUILDING)


# ---------------------------------------------------------------------------
# _run_validation — command text
# ---------------------------------------------------------------------------


class TestRunValidationCommand:
    @patch("sdd_copilot.builder.subprocess.run")
    def test_command_text_passed_directly(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        spec = _make_spec(sections={"Validation Command": "pytest tests/ -v"})
        _run_validation(spec, Path("/project"))
        assert mock_run.call_args[0][0] == "pytest tests/ -v"
