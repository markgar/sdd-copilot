"""Build loop — pick next planned spec, read tasks, execute each task
in a fresh copilot session with live output, run validation, update status.

Tier 3 (orchestration) — depends on Tier 0 (exceptions), Tier 1 (models),
and Tier 2 (status, runner, prompt_builder).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from sdd_copilot.exceptions import BuilderError
from sdd_copilot.models import Spec, SpecSet, SpecStatus, TaskList
from sdd_copilot.planner import _parse_tasks
from sdd_copilot.prompt_builder import build_task_prompt
from sdd_copilot.runner import DEFAULT_MODEL, run_copilot
from sdd_copilot.status import set_status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task-file I/O
# ---------------------------------------------------------------------------


def _read_task_file(spec_dir: Path, spec_number: int) -> TaskList:
    """Read and parse ``tasks/tasks-NN.md`` into a :class:`TaskList`.

    Raises
    ------
    BuilderError
        If the task file is missing, empty, or cannot be parsed.
    """
    path = spec_dir / "tasks" / f"tasks-{spec_number:02d}.md"
    if not path.exists():
        raise BuilderError(
            path,
            f"Task file not found for spec {spec_number:02d}",
        )

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuilderError(path, str(exc)) from exc

    if not content.strip():
        raise BuilderError(path, "Task file is empty")

    try:
        tasks = _parse_tasks(content)
    except ValueError as exc:
        raise BuilderError(path, str(exc)) from exc

    return TaskList(
        spec_number=spec_number,
        tasks=tuple(tasks),
        path=path,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALIDATION_TIMEOUT = 300  # seconds


def _run_validation(spec: Spec, project_dir: Path) -> bool:
    """Run the spec's ``Validation Command`` section, if present.

    Returns ``True`` when validation passes (or no command is defined).
    Returns ``False`` on non-zero exit code.

    Raises
    ------
    BuilderError
        If the validation process cannot be started or times out.
    """
    command_text = spec.sections.get("Validation Command", "").strip()
    if not command_text:
        logger.info("No validation command for spec %02d — skipping", spec.number)
        return True

    logger.info("Running validation for spec %02d: %s", spec.number, command_text)

    try:
        result = subprocess.run(
            command_text,
            shell=True,
            cwd=project_dir,
            timeout=_VALIDATION_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise BuilderError(
            spec.path,
            f"Validation command timed out after {_VALIDATION_TIMEOUT}s",
        ) from exc
    except OSError as exc:
        raise BuilderError(spec.path, f"Validation failed to start: {exc}") from exc

    if result.returncode == 0:
        logger.info("Validation passed for spec %02d", spec.number)
        return True

    logger.warning(
        "Validation failed for spec %02d (exit code %d)",
        spec.number,
        result.returncode,
    )
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_next(
    spec_set: SpecSet,
    spec_number: int | None = None,
    model: str = DEFAULT_MODEL,
    project_dir: Path | None = None,
) -> bool:
    """Build the next (or specified) planned spec, task by task.

    Flow
    ----
    1. Pick the target spec (next planned, or the one requested).
    2. Read ``tasks/tasks-NN.md``, parse into :class:`TaskList`.
    3. Set status to ``building``.
    4. For each task: build prompt → shell out to copilot (live output).
    5. Run the spec's ``Validation Command``.
    6. If validation passes → set status to ``done``, return ``True``.
    7. If validation fails → leave status as ``building``, return ``False``.

    Raises
    ------
    BuilderError
        If no planned spec is found, the task file is missing, or
        a copilot invocation fails critically.
    SpecNotFoundError
        If *spec_number* does not exist in the spec set.
    """
    # -- 1. Pick the spec ---------------------------------------------------
    if spec_number is not None:
        spec: Spec = spec_set.get_spec(spec_number)
        if spec.status != SpecStatus.PLANNED:
            raise BuilderError(
                spec.path,
                f"Spec {spec_number:02d} has status '{spec.status.value}', "
                "expected 'planned'",
            )
    else:
        found = spec_set.next_actionable(SpecStatus.PLANNED)
        if found is None:
            raise BuilderError(
                spec_set.spec_dir,
                "No planned specs found to build",
            )
        spec = found

    logger.info("Building spec %02d: %s", spec.number, spec.title)

    working_dir = project_dir if project_dir is not None else spec_set.spec_dir

    # -- 2. Read task file --------------------------------------------------
    task_list = _read_task_file(spec_set.spec_dir, spec.number)

    # -- 3. Set status to building ------------------------------------------
    set_status(spec_set.spec_dir, spec.number, SpecStatus.BUILDING)

    # -- 4. Execute each task -----------------------------------------------
    total = len(task_list.tasks)
    for task in task_list.tasks:
        logger.info(
            "[Task %d/%d] %s",
            task.number,
            total,
            task.title,
        )

        prompt = build_task_prompt(task, spec, spec_set)

        result = run_copilot(
            prompt=prompt,
            working_dir=working_dir,
            model=model,
            extra_dirs=(spec_set.spec_dir,),
        )

        if not result.success:
            logger.warning(
                "Task %d/%d failed (exit code %d) — continuing",
                task.number,
                total,
                result.exit_code,
            )

    # -- 5. Run validation --------------------------------------------------
    passed = _run_validation(spec, working_dir)

    # -- 6/7. Update status based on validation result ----------------------
    if passed:
        set_status(spec_set.spec_dir, spec.number, SpecStatus.DONE)
        logger.info("Spec %02d completed successfully", spec.number)
    else:
        logger.warning(
            "Spec %02d validation failed — status remains 'building'",
            spec.number,
        )

    return passed
