"""End-to-end tests — exercise the full CLI flow against real spec directories.

Only the copilot runner is mocked (no real binary available).  Everything
else — spec loading, status persistence, task-file I/O, prompt assembly —
runs against actual files on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdd_copilot.cli import main
from sdd_copilot.models import SpecStatus
from sdd_copilot.runner import CopilotResult
from sdd_copilot.status import load_all_statuses


# ---------------------------------------------------------------------------
# Fixtures — build realistic spec directories on disk
# ---------------------------------------------------------------------------

COPILOT_TASK_RESPONSE = """\
## Task 1: Create data model
### Description
Define the core data structures for the foundation module.
### Acceptance Criteria
GIVEN the module is imported WHEN data classes are used THEN they validate inputs

## Task 2: Add persistence layer
### Description
Implement JSON-based persistence for the data model.
### Acceptance Criteria
GIVEN data is saved WHEN it is reloaded THEN it matches the original
"""


@pytest.fixture()
def spec_dir(tmp_path: Path) -> Path:
    """Create a realistic spec directory with constitution, README, and specs."""
    d = tmp_path / "specs"
    d.mkdir()

    (d / "CONSTITUTION.md").write_text(
        "# Project Constitution\n\nBuild with care. Test everything.\n"
    )

    (d / "README.md").write_text(
        "# Project Specs\n\n"
        "Build order:\n"
        "- 01-foundation\n"
        "- 02-api\n"
    )

    (d / "01-foundation.md").write_text(
        "# Foundation\n\n"
        "## Summary\nCore data model and utilities.\n\n"
        "## What to Build\nCreate data model classes and helpers.\n\n"
        "## Acceptance Criteria\n"
        "GIVEN the module WHEN imported THEN classes are available.\n\n"
        "## Validation Command\necho ok\n"
    )

    (d / "02-api.md").write_text(
        "# API Layer\n\n"
        "## Summary\nREST API on top of the foundation.\n\n"
        "## What to Build\nBuild API endpoints.\n\n"
        "## Dependencies\nRequires **Spec 1** (Foundation).\n\n"
        "## Acceptance Criteria\n"
        "GIVEN the API WHEN called THEN returns JSON.\n\n"
        "## Validation Command\necho ok\n"
    )

    # research directory with one doc
    research = d / "research"
    research.mkdir()
    (research / "api-patterns.md").write_text("# API Patterns\n\nUse REST.\n")

    return d


@pytest.fixture()
def spec_dir_three(tmp_path: Path) -> Path:
    """Spec directory with three specs for multi-spec run tests."""
    d = tmp_path / "specs"
    d.mkdir()

    (d / "CONSTITUTION.md").write_text("# Constitution\nBuild well.\n")
    (d / "README.md").write_text("01-alpha\n02-beta\n03-gamma\n")

    for num, name in [(1, "alpha"), (2, "beta"), (3, "gamma")]:
        deps = ""
        if num == 2:
            deps = "## Dependencies\n**Spec 1**\n\n"
        if num == 3:
            deps = "## Dependencies\n**Spec 1** and **Spec 2**\n\n"
        (d / f"{num:02d}-{name}.md").write_text(
            f"# {name.title()}\n\n"
            f"## Summary\n{name} module.\n\n"
            f"## What to Build\nBuild {name}.\n\n"
            f"{deps}"
            f"## Validation Command\necho ok\n"
        )

    return d


# ---------------------------------------------------------------------------
# sdd status
# ---------------------------------------------------------------------------


class TestE2EStatus:
    def test_status_shows_all_specs(
        self, spec_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        assert "Foundation" in out
        assert "API" in out
        assert "pending" in out

    def test_status_reflects_persisted_state(
        self, spec_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (spec_dir / ".sdd-status.json").write_text(
            json.dumps({"1": "done", "2": "planned"})
        )
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        assert "done" in out
        assert "planned" in out

    def test_status_shows_dependencies(
        self, spec_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        # Spec 02 depends on spec 01
        lines = out.strip().splitlines()
        api_line = [l for l in lines if "API" in l][0]
        assert "01" in api_line


# ---------------------------------------------------------------------------
# sdd plan
# ---------------------------------------------------------------------------


class TestE2EPlan:
    @patch("sdd_copilot.planner.run_copilot")
    def test_plan_creates_task_file_and_updates_status(
        self, mock_run: MagicMock, spec_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )

        main(["plan", "--spec-dir", str(spec_dir), "--spec", "1"])

        # Task file was written
        task_file = spec_dir / "tasks" / "tasks-01.md"
        assert task_file.exists()
        content = task_file.read_text(encoding="utf-8")
        assert "Task 1" in content
        assert "Task 2" in content

        # Status was updated on disk
        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.PLANNED

        # CLI output confirms planning
        out = capsys.readouterr().out
        assert "Planned spec 01" in out
        assert "2 tasks" in out

    @patch("sdd_copilot.planner.run_copilot")
    def test_plan_auto_picks_next_pending(
        self, mock_run: MagicMock, spec_dir: Path
    ) -> None:
        mock_run.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )

        main(["plan", "--spec-dir", str(spec_dir)])

        # Should have planned spec 01 (first pending in build order)
        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.PLANNED

    @patch("sdd_copilot.planner.run_copilot")
    def test_plan_passes_constitution_in_prompt(
        self, mock_run: MagicMock, spec_dir: Path
    ) -> None:
        mock_run.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )

        main(["plan", "--spec-dir", str(spec_dir), "--spec", "1"])

        prompt = mock_run.call_args[1]["prompt"]
        assert "Build with care" in prompt


# ---------------------------------------------------------------------------
# sdd build
# ---------------------------------------------------------------------------


class TestE2EBuild:
    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    def test_build_executes_tasks_and_marks_done(
        self,
        mock_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Pre-condition: spec must be planned with task file on disk
        self._setup_planned_spec(spec_dir, 1)
        mock_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main(["build", "--spec-dir", str(spec_dir), "--spec", "1"])

        # Copilot was called once per task
        assert mock_copilot.call_count == 2

        # Status should be done
        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.DONE

        out = capsys.readouterr().out
        assert "validation passed" in out

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    def test_build_validation_failure_leaves_building(
        self,
        mock_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
    ) -> None:
        self._setup_planned_spec(spec_dir, 1)
        mock_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 1})()

        with pytest.raises(SystemExit) as exc_info:
            main(["build", "--spec-dir", str(spec_dir), "--spec", "1"])
        assert exc_info.value.code == 1

        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.BUILDING

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    def test_build_with_project_dir(
        self,
        mock_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
        tmp_path: Path,
    ) -> None:
        self._setup_planned_spec(spec_dir, 1)
        project = tmp_path / "project"
        project.mkdir()
        mock_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main([
            "build", "--spec-dir", str(spec_dir),
            "--spec", "1", "--project-dir", str(project),
        ])

        # All copilot calls used project_dir as working_dir
        for c in mock_copilot.call_args_list:
            assert c.kwargs["working_dir"] == project

    @staticmethod
    def _setup_planned_spec(spec_dir: Path, spec_number: int) -> None:
        """Write task file and set status to planned."""
        tasks_dir = spec_dir / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        (tasks_dir / f"tasks-{spec_number:02d}.md").write_text(
            COPILOT_TASK_RESPONSE, encoding="utf-8"
        )
        status_file = spec_dir / ".sdd-status.json"
        data: dict[str, str] = {}
        if status_file.exists():
            data = json.loads(status_file.read_text(encoding="utf-8"))
        data[str(spec_number)] = SpecStatus.PLANNED.value
        status_file.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# sdd run — full cycle
# ---------------------------------------------------------------------------


class TestE2ERun:
    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_run_plans_and_builds_single_spec(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main(["run", "--spec-dir", str(spec_dir)])

        # Both specs should end up done
        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.DONE
        assert statuses[2] == SpecStatus.DONE

        # Task files for both specs should exist
        assert (spec_dir / "tasks" / "tasks-01.md").exists()
        assert (spec_dir / "tasks" / "tasks-02.md").exists()

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_run_three_specs_sequentially(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir_three: Path,
    ) -> None:
        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main(["run", "--spec-dir", str(spec_dir_three)])

        statuses = load_all_statuses(spec_dir_three)
        assert statuses[1] == SpecStatus.DONE
        assert statuses[2] == SpecStatus.DONE
        assert statuses[3] == SpecStatus.DONE

        # 3 planning calls (one per spec)
        assert mock_planner_copilot.call_count == 3
        # 6 build calls (2 tasks per spec × 3 specs)
        assert mock_builder_copilot.call_count == 6

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_run_stops_on_build_failure(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir_three: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        # Validation fails for spec 02
        call_count = {"n": 0}

        def validation_side_effect(*args, **kwargs):
            call_count["n"] += 1
            result = type("R", (), {"returncode": 0 if call_count["n"] <= 1 else 1})()
            return result

        mock_subprocess.side_effect = validation_side_effect

        with pytest.raises(SystemExit) as exc_info:
            main(["run", "--spec-dir", str(spec_dir_three)])
        assert exc_info.value.code == 1

        statuses = load_all_statuses(spec_dir_three)
        assert statuses[1] == SpecStatus.DONE
        assert statuses[2] == SpecStatus.BUILDING
        # Spec 3 should not have been touched
        assert statuses.get(3, SpecStatus.PENDING) == SpecStatus.PENDING

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_run_resumes_with_done_specs(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
    ) -> None:
        # Pre-mark spec 1 as done
        (spec_dir / ".sdd-status.json").write_text(
            json.dumps({"1": "done"})
        )

        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main(["run", "--spec-dir", str(spec_dir)])

        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.DONE
        assert statuses[2] == SpecStatus.DONE

        # Only spec 2 should have been planned
        assert mock_planner_copilot.call_count == 1

    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_run_forwards_model_flag(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
    ) -> None:
        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        main(["run", "--spec-dir", str(spec_dir), "--model", "gpt-4o"])

        for c in mock_planner_copilot.call_args_list:
            assert c.kwargs["model"] == "gpt-4o"
        for c in mock_builder_copilot.call_args_list:
            assert c.kwargs["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# Full cycle: status → plan → build → status
# ---------------------------------------------------------------------------


class TestE2EFullCycle:
    @patch("sdd_copilot.builder.subprocess.run")
    @patch("sdd_copilot.builder.run_copilot")
    @patch("sdd_copilot.planner.run_copilot")
    def test_complete_lifecycle_on_disk(
        self,
        mock_planner_copilot: MagicMock,
        mock_builder_copilot: MagicMock,
        mock_subprocess: MagicMock,
        spec_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Walk through the complete lifecycle step by step."""
        mock_planner_copilot.return_value = CopilotResult(
            exit_code=0, output=COPILOT_TASK_RESPONSE
        )
        mock_builder_copilot.return_value = CopilotResult(exit_code=0)
        mock_subprocess.return_value = type("R", (), {"returncode": 0})()

        # Step 1: status — everything pending
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        assert out.count("pending") == 2

        # Step 2: plan spec 1
        main(["plan", "--spec-dir", str(spec_dir), "--spec", "1"])
        capsys.readouterr()  # consume output

        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.PLANNED

        # Step 3: build spec 1
        main(["build", "--spec-dir", str(spec_dir), "--spec", "1"])
        capsys.readouterr()

        statuses = load_all_statuses(spec_dir)
        assert statuses[1] == SpecStatus.DONE

        # Step 4: status — spec 1 done, spec 2 still pending
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        assert "done" in out
        assert "pending" in out

        # Step 5: plan spec 2
        main(["plan", "--spec-dir", str(spec_dir), "--spec", "2"])
        capsys.readouterr()

        statuses = load_all_statuses(spec_dir)
        assert statuses[2] == SpecStatus.PLANNED

        # Step 6: build spec 2
        main(["build", "--spec-dir", str(spec_dir), "--spec", "2"])
        capsys.readouterr()

        statuses = load_all_statuses(spec_dir)
        assert statuses[2] == SpecStatus.DONE

        # Step 7: final status — all done
        main(["status", "--spec-dir", str(spec_dir)])
        out = capsys.readouterr().out
        assert out.count("done") == 2
        assert "pending" not in out
