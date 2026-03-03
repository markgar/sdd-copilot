"""Tests for sdd_copilot.planner — task parsing and plan_next orchestration."""

import json
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
from sdd_copilot.planner import _extract_subsection, _parse_tasks, plan_next
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
        tasks = _parse_tasks(VALID_TASK_OUTPUT)
        assert len(tasks) == 2
        assert tasks[0].number == 1
        assert tasks[0].title == "Setup project"
        assert "project structure" in tasks[0].description
        assert tasks[1].number == 2
        assert tasks[1].title == "Implement core"

    def test_no_tasks_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="No tasks found"):
            _parse_tasks("No tasks here at all")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="No tasks found"):
            _parse_tasks("")

    def test_single_task(self) -> None:
        text = "## Task 1: Only task\n### Description\nDo it\n### Acceptance Criteria\nDone"
        tasks = _parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].title == "Only task"

    def test_task_with_missing_subsections(self) -> None:
        text = "## Task 1: Minimal\nSome content"
        tasks = _parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].description == ""
        assert tasks[0].acceptance_criteria == ""

    def test_returns_task_objects(self) -> None:
        tasks = _parse_tasks(VALID_TASK_OUTPUT)
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
