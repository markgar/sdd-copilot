"""Planning loop — pick next pending spec, build prompt, shell out
to copilot, parse the response into tasks, write task file, update status.

Tier 3 (orchestration) — depends on Tier 0 (exceptions), Tier 1 (models),
and Tier 2 (status, runner, prompt_builder).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sdd_copilot.exceptions import PlannerError
from sdd_copilot.models import Spec, SpecSet, SpecStatus, Task, TaskList
from sdd_copilot.prompt_builder import build_planning_prompt
from sdd_copilot.runner import run_copilot
from sdd_copilot.status import set_status

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4.6"

# ---------------------------------------------------------------------------
# Task-file parsing
# ---------------------------------------------------------------------------

_TASK_HEADING_RE = re.compile(r"^##\s+Task\s+(\d+):\s*(.+)$", re.MULTILINE)


def _extract_subsection(text: str, heading: str) -> str:
    """Return the content under a ``### <heading>`` marker.

    Extracts everything after the heading line up to the next ``###``
    heading or end of string.
    """
    pattern = re.compile(
        rf"###\s+{re.escape(heading)}\s*\n(.*?)(?=###\s|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _parse_tasks(text: str) -> list[Task]:
    """Parse copilot's markdown response into a list of :class:`Task` objects.

    Expects the format::

        ## Task 1: Short title
        ### Description
        …
        ### Acceptance Criteria
        …

    Raises :class:`ValueError` when no tasks are found.
    """
    headings = list(_TASK_HEADING_RE.finditer(text))
    if not headings:
        raise ValueError("No tasks found in copilot response")

    tasks: list[Task] = []
    for i, match in enumerate(headings):
        number = int(match.group(1))
        title = match.group(2).strip()

        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        section_text = text[start:end]

        description = _extract_subsection(section_text, "Description")
        criteria = _extract_subsection(section_text, "Acceptance Criteria")

        tasks.append(
            Task(
                number=number,
                title=title,
                description=description,
                acceptance_criteria=criteria,
            )
        )

    return tasks


# ---------------------------------------------------------------------------
# Task-file I/O
# ---------------------------------------------------------------------------


def _write_task_file(
    spec_dir: Path,
    spec_number: int,
    content: str,
) -> Path:
    """Write *content* to ``tasks/tasks-NN.md`` under *spec_dir*.

    Creates the ``tasks/`` directory if it does not exist.
    """
    tasks_dir = spec_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    path = tasks_dir / f"tasks-{spec_number:02d}.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote task file: %s", path)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan_next(
    spec_set: SpecSet,
    spec_number: int | None = None,
    model: str = _DEFAULT_MODEL,
) -> TaskList:
    """Plan the next (or specified) pending spec into tasks.

    Flow
    ----
    1. Pick the target spec (next pending, or the one requested).
    2. Build a planning prompt via :func:`build_planning_prompt`.
    3. Shell out to ``copilot`` with ``capture=True``.
    4. Parse the markdown response into :class:`Task` objects.
    5. Write the task file to ``tasks/tasks-NN.md``.
    6. Update spec status to ``planned``.
    7. Return the resulting :class:`TaskList`.

    Raises
    ------
    PlannerError
        If no pending spec is found, the copilot invocation fails, or
        the response cannot be parsed into tasks.
    SpecNotFoundError
        If *spec_number* does not exist in the spec set.
    """
    # -- 1. Pick the spec ---------------------------------------------------
    if spec_number is not None:
        spec: Spec = spec_set.get_spec(spec_number)
        if spec.status != SpecStatus.PENDING:
            raise PlannerError(
                spec.path,
                f"Spec {spec_number:02d} has status '{spec.status.value}', "
                "expected 'pending'",
            )
    else:
        found = spec_set.next_actionable(SpecStatus.PENDING)
        if found is None:
            raise PlannerError(
                spec_set.spec_dir,
                "No pending specs found to plan",
            )
        spec = found

    logger.info("Planning spec %02d: %s", spec.number, spec.title)

    # -- 2. Build planning prompt -------------------------------------------
    prompt = build_planning_prompt(spec, spec_set)

    # -- 3. Shell out to copilot --------------------------------------------
    result = run_copilot(
        prompt=prompt,
        working_dir=spec_set.spec_dir,
        model=model,
        capture=True,
    )

    if not result.success:
        raise PlannerError(
            spec.path,
            f"Copilot exited with code {result.exit_code}",
        )

    if not result.output.strip():
        raise PlannerError(
            spec.path,
            "Copilot returned empty output — no tasks to parse",
        )

    # -- 4. Parse the markdown response into tasks --------------------------
    try:
        tasks = _parse_tasks(result.output)
    except ValueError as exc:
        raise PlannerError(spec.path, str(exc)) from exc

    # -- 5. Write task file -------------------------------------------------
    path = _write_task_file(spec_set.spec_dir, spec.number, result.output)

    # -- 6. Update status ---------------------------------------------------
    set_status(spec_set.spec_dir, spec.number, SpecStatus.PLANNED)

    # -- 7. Return TaskList -------------------------------------------------
    task_list = TaskList(
        spec_number=spec.number,
        tasks=tuple(tasks),
        path=path,
    )

    logger.info(
        "Planned spec %02d into %d tasks → %s",
        spec.number,
        len(tasks),
        path,
    )

    return task_list
