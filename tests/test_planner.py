"""Tests for sdd_copilot.planner — task parsing and plan_next orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdd_copilot.exceptions import ConstitutionMissingError, PlannerError, SpecNotFoundError
from sdd_copilot.models import (
    BuildPlan,
    Constitution,
    Spec,
    SpecSet,
    SpecStatus,
    Task,
    TaskList,
)
from sdd_copilot.planner import _extract_subsection, parse_tasks, plan_next
from sdd_copilot.runner import CopilotResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    number: int = 1,
    status: SpecStatus = SpecStatus.PENDING,
) -> Spec:
    return Spec(
        number=number,
        slug="test",
        title="Test Spec",
        path=Path(f"/specs/{number:02d}-test.md"),
        sections={"Summary": "summary", "What to Build": "stuff"},
        status=status,
    )


def _make_spec_set(
    specs: dict[int, Spec] | None = None,
    constitution_content: str = "Be good.",
    spec_dir: Path | None = None,
) -> SpecSet:
    if specs is None:
        specs = {1: _make_spec()}
    return SpecSet(
        specs=specs,
        constitution=Constitution(path=Path("/c.md"), content=constitution_content),
        build_plan=BuildPlan(order=tuple(specs.keys())),
        research_docs={},
        spec_dir=spec_dir or Path("/specs"),
    )


VALID_TASK_OUTPUT = """\
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


# ---------------------------------------------------------------------------
# _extract_subsection
# ---------------------------------------------------------------------------


class TestExtractSubsection:
    def test_extracts_description(self) -> None:
        text = "### Description\nSome text here\n### Acceptance Criteria\nCriteria"
        result = _extract_subsection(text, "Description")
        assert result == "Some text here"

    def test_extracts_acceptance_criteria(self) -> None:
        text = "### Description\nDesc\n### Acceptance Criteria\nGIVEN x WHEN y THEN z"
        result = _extract_subsection(text, "Acceptance Criteria")
        assert "GIVEN x" in result

    def test_missing_subsection_returns_empty(self) -> None:
        text = "### Description\nDesc"
        result = _extract_subsection(text, "Missing")
        assert result == ""

    def test_multiline_content(self) -> None:
        text = "### Description\nLine 1\nLine 2\nLine 3\n### Next"
        result = _extract_subsection(text, "Description")
        assert "Line 1" in result
        assert "Line 3" in result


# ---------------------------------------------------------------------------
# _parse_tasks
# ---------------------------------------------------------------------------


class TestParseTasks:
    def test_parses_valid_output(self) -> None:
        tasks = parse_tasks(VALID_TASK_OUTPUT)
        assert len(tasks) == 2
        assert tasks[0].number == 1
        assert tasks[0].title == "Setup project"
        assert "project structure" in tasks[0].description
        assert tasks[1].number == 2
        assert tasks[1].title == "Implement core"

    def test_no_tasks_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="No tasks found"):
            parse_tasks("No tasks here at all")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="No tasks found"):
            parse_tasks("")

    def test_single_task(self) -> None:
        text = "## Task 1: Only task\n### Description\nDo it\n### Acceptance Criteria\nDone"
        tasks = parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].title == "Only task"

    def test_task_with_missing_subsections(self) -> None:
        text = "## Task 1: Minimal\nSome content"
        tasks = parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].description == ""
        assert tasks[0].acceptance_criteria == ""

    def test_returns_task_objects(self) -> None:
        tasks = parse_tasks(VALID_TASK_OUTPUT)
        for t in tasks:
            assert isinstance(t, Task)


# ---------------------------------------------------------------------------
# plan_next — happy path (mocked runner)
# ---------------------------------------------------------------------------


class TestPlanNextHappyPath:
    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_plans_next_pending_spec(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)

        ss = _make_spec_set(spec_dir=tmp_path)
        result = plan_next(ss)

        assert isinstance(result, TaskList)
        assert result.spec_number == 1
        assert len(result.tasks) == 2
        mock_set_status.assert_called_once_with(tmp_path, 1, SpecStatus.PLANNED)

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_writes_task_file(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)

        ss = _make_spec_set(spec_dir=tmp_path)
        result = plan_next(ss)

        assert result.path.exists()
        assert result.path.name == "tasks-01.md"
        content = result.path.read_text(encoding="utf-8")
        assert "Task 1" in content

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_plans_specific_spec_number(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)

        spec2 = _make_spec(number=2)
        ss = _make_spec_set(
            specs={1: _make_spec(status=SpecStatus.DONE), 2: spec2},
            spec_dir=tmp_path,
        )
        result = plan_next(ss, spec_number=2)
        assert result.spec_number == 2


# ---------------------------------------------------------------------------
# plan_next — error cases
# ---------------------------------------------------------------------------


class TestPlanNextErrors:
    def test_no_pending_specs_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(
            specs={1: _make_spec(status=SpecStatus.DONE)},
            spec_dir=tmp_path,
        )
        with pytest.raises(PlannerError, match="No pending specs"):
            plan_next(ss)

    def test_specific_spec_not_pending_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(
            specs={1: _make_spec(status=SpecStatus.DONE)},
            spec_dir=tmp_path,
        )
        with pytest.raises(PlannerError, match="expected 'pending'"):
            plan_next(ss, spec_number=1)

    def test_spec_not_found_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(SpecNotFoundError):
            plan_next(ss, spec_number=99)

    def test_empty_constitution_raises(self, tmp_path: Path) -> None:
        ss = _make_spec_set(
            constitution_content="",
            spec_dir=tmp_path,
        )
        with pytest.raises(ConstitutionMissingError):
            plan_next(ss)

    @patch("sdd_copilot.planner.run_copilot")
    def test_copilot_failure_raises(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=1, output="")
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(PlannerError, match="exited with code 1"):
            plan_next(ss)

    @patch("sdd_copilot.planner.run_copilot")
    def test_empty_output_raises(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output="")
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(PlannerError, match="empty output"):
            plan_next(ss)

    @patch("sdd_copilot.planner.run_copilot")
    def test_unparseable_output_raises(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(
            exit_code=0, output="Random text with no task headings"
        )
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(PlannerError, match="No tasks found"):
            plan_next(ss)

    @patch("sdd_copilot.planner.run_copilot")
    def test_parse_error_chains_from(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(
            exit_code=0, output="No tasks"
        )
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(PlannerError) as exc_info:
            plan_next(ss)
        assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# parse_tasks — additional edge cases
# ---------------------------------------------------------------------------


class TestParseTasksEdgeCases:
    def test_numbering_gap(self) -> None:
        text = (
            "## Task 1: First\n### Description\nD1\n### Acceptance Criteria\nAC1\n\n"
            "## Task 3: Third\n### Description\nD3\n### Acceptance Criteria\nAC3\n"
        )
        tasks = parse_tasks(text)
        assert len(tasks) == 2
        assert tasks[0].number == 1
        assert tasks[1].number == 3

    def test_preamble_before_first_task_ignored(self) -> None:
        text = (
            "# Some preamble\n\nIntro text here\n\n"
            "## Task 1: Only\n### Description\nD\n### Acceptance Criteria\nAC\n"
        )
        tasks = parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].title == "Only"

    def test_task_with_rich_description(self) -> None:
        text = (
            "## Task 1: Complex\n"
            "### Description\n"
            "- Step one\n"
            "- Step two\n"
            "- Step three\n"
            "### Acceptance Criteria\n"
            "GIVEN x WHEN y THEN z\n"
        )
        tasks = parse_tasks(text)
        assert "Step one" in tasks[0].description
        assert "Step three" in tasks[0].description


# ---------------------------------------------------------------------------
# _extract_subsection — additional edge cases
# ---------------------------------------------------------------------------


class TestExtractSubsectionEdgeCases:
    def test_last_section_no_trailing_heading(self) -> None:
        text = "### Description\nLine 1\nLine 2"
        result = _extract_subsection(text, "Description")
        assert "Line 1" in result
        assert "Line 2" in result

    def test_empty_subsection_body(self) -> None:
        text = "### Description\n### Acceptance Criteria\nAC"
        result = _extract_subsection(text, "Description")
        assert result == ""


# ---------------------------------------------------------------------------
# plan_next — runner arguments
# ---------------------------------------------------------------------------


class TestPlanNextRunnerArgs:
    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_capture_true_passed_to_runner(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        plan_next(ss)
        assert mock_run.call_args[1]["capture"] is True

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_model_forwarded_to_runner(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        plan_next(ss, model="gpt-4o")
        assert mock_run.call_args[1]["model"] == "gpt-4o"

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_working_dir_is_spec_dir(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        plan_next(ss)
        assert mock_run.call_args[1]["working_dir"] == tmp_path


# ---------------------------------------------------------------------------
# plan_next — whitespace-only output
# ---------------------------------------------------------------------------


class TestPlanNextWhitespaceOutput:
    @patch("sdd_copilot.planner.run_copilot")
    def test_whitespace_only_output_raises(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output="   \n  \n  ")
        ss = _make_spec_set(spec_dir=tmp_path)
        with pytest.raises(PlannerError, match="empty output"):
            plan_next(ss)


# ---------------------------------------------------------------------------
# plan_next — task directory creation
# ---------------------------------------------------------------------------


class TestPlanNextCreatesTaskDir:
    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_creates_tasks_directory(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        assert not (tmp_path / "tasks").exists()
        plan_next(ss)
        assert (tmp_path / "tasks").is_dir()

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_existing_tasks_dir_not_error(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        (tmp_path / "tasks").mkdir()
        ss = _make_spec_set(spec_dir=tmp_path)
        result = plan_next(ss)
        assert result.path.exists()


# ---------------------------------------------------------------------------
# plan_next — default model
# ---------------------------------------------------------------------------


class TestPlanNextDefaultModel:
    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_default_model_used_when_not_specified(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        from sdd_copilot.runner import DEFAULT_MODEL
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        plan_next(ss)
        assert mock_run.call_args[1]["model"] == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# plan_next — task list structure
# ---------------------------------------------------------------------------


class TestPlanNextTaskList:
    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_task_list_tasks_are_tuple(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        result = plan_next(ss)
        assert isinstance(result.tasks, tuple)

    @patch("sdd_copilot.planner.set_status")
    @patch("sdd_copilot.planner.run_copilot")
    def test_task_file_content_matches_copilot_output(
        self, mock_run: MagicMock, mock_set_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = CopilotResult(exit_code=0, output=VALID_TASK_OUTPUT)
        ss = _make_spec_set(spec_dir=tmp_path)
        result = plan_next(ss)
        content = result.path.read_text(encoding="utf-8")
        assert content == VALID_TASK_OUTPUT
