"""Dataclasses for the SDD Copilot domain model."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


from sdd_copilot.exceptions import SpecNotFoundError


# ---------------------------------------------------------------------------
# Status enum — single source of truth for the spec lifecycle
# ---------------------------------------------------------------------------


class SpecStatus(enum.StrEnum):
    """Lifecycle states for a specification.

    Flow: pending → planned → building → done
    """

    PENDING = "pending"
    PLANNED = "planned"
    BUILDING = "building"
    DONE = "done"


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Constitution:
    """Project constitution loaded from CONSTITUTION.md."""

    path: Path
    content: str  # full raw text


@dataclass(frozen=True)
class Task:
    """A single implementation task within a spec's task list."""

    number: int  # 1, 2, 3, ...
    title: str
    description: str
    acceptance_criteria: str  # relevant GIVEN/WHEN/THEN

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"Task number must be >= 1, got {self.number}")
        if not self.title.strip():
            raise ValueError("Task title must not be empty")


@dataclass
class Spec:
    """A single numbered specification."""

    number: int  # 01, 02, ...
    slug: str  # "foundation", "connection-managers"
    title: str  # "Foundation & Data Model"
    path: Path  # absolute path to the spec .md file
    sections: dict[str, str] = field(repr=False)  # heading → content
    dependencies: tuple[int, ...] = field(default_factory=tuple)
    status: SpecStatus = SpecStatus.PENDING

    def __post_init__(self) -> None:
        if self.number < 0:
            raise ValueError(f"Spec number must be >= 0, got {self.number}")
        if not self.slug.strip():
            raise ValueError("Spec slug must not be empty")
        if not isinstance(self.dependencies, tuple):
            self.dependencies = tuple(self.dependencies)
        if not isinstance(self.status, SpecStatus):
            # Allow string construction for convenience (e.g. from JSON)
            self.status = SpecStatus(self.status)

    def __repr__(self) -> str:  # noqa: D105
        return (
            f"Spec(number={self.number}, slug={self.slug!r}, "
            f"title={self.title!r}, status={self.status.value!r})"
        )


@dataclass(frozen=True)
class BuildPlan:
    """Ordered list of spec numbers reflecting the build order."""

    order: tuple[int, ...]  # immutable; specs in build order

    def __post_init__(self) -> None:
        if not isinstance(self.order, tuple):
            object.__setattr__(self, "order", tuple(self.order))
        if len(self.order) != len(set(self.order)):
            raise ValueError("BuildPlan contains duplicate spec numbers")


@dataclass(frozen=True)
class TaskList:
    """The full set of tasks produced by the planner for a given spec."""

    spec_number: int
    tasks: tuple[Task, ...]  # immutable
    path: Path  # tasks/tasks-NN.md

    def __post_init__(self) -> None:
        if self.spec_number < 0:
            raise ValueError(f"TaskList spec_number must be >= 0, got {self.spec_number}")
        if not isinstance(self.tasks, tuple):
            object.__setattr__(self, "tasks", tuple(self.tasks))
        if not self.tasks:
            raise ValueError("TaskList must contain at least one task")


@dataclass
class SpecSet:
    """Everything loaded from a spec directory."""

    specs: dict[int, Spec]  # number → Spec
    constitution: Constitution
    build_plan: BuildPlan  # ordered list of spec numbers
    research_docs: dict[str, str] = field(repr=False)  # filename → content
    spec_dir: Path = field(default=Path("."))

    # -- Query helpers (moved here from status.py — they query SpecSet) -----

    def next_actionable(self, target_status: SpecStatus) -> Spec | None:
        """Return the first spec (build-plan order) matching *target_status*."""
        for number in self.build_plan.order:
            spec = self.specs.get(number)
            if spec is not None and spec.status == target_status:
                return spec
        return None

    def get_spec(self, spec_number: int) -> Spec:
        """Return a spec by number or raise ``KeyError``."""
        try:
            return self.specs[spec_number]
        except KeyError:
            raise SpecNotFoundError(spec_number) from None
