"""Tests for sdd_copilot.models — domain dataclasses and enum."""

from pathlib import Path

import pytest

from sdd_copilot.exceptions import SpecNotFoundError
from sdd_copilot.models import (
    BuildPlan,
    Constitution,
    Spec,
    SpecSet,
    SpecStatus,
    Task,
    TaskList,
)


# ---------------------------------------------------------------------------
# SpecStatus enum
# ---------------------------------------------------------------------------


class TestSpecStatus:
    def test_values(self) -> None:
        assert SpecStatus.PENDING.value == "pending"
        assert SpecStatus.PLANNED.value == "planned"
        assert SpecStatus.BUILDING.value == "building"
        assert SpecStatus.DONE.value == "done"

    def test_str_enum_comparison(self) -> None:
        assert SpecStatus.PENDING == "pending"

    def test_construct_from_value(self) -> None:
        assert SpecStatus("done") is SpecStatus.DONE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SpecStatus("invalid")

    def test_all_members(self) -> None:
        assert len(SpecStatus) == 4


# ---------------------------------------------------------------------------
# Constitution
# ---------------------------------------------------------------------------


class TestConstitution:
    def test_frozen(self) -> None:
        c = Constitution(path=Path("/c.md"), content="text")
        with pytest.raises(AttributeError):
            c.content = "changed"  # type: ignore[misc]

    def test_fields(self) -> None:
        c = Constitution(path=Path("/c.md"), content="abc")
        assert c.path == Path("/c.md")
        assert c.content == "abc"


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class TestTask:
    def test_valid_task(self) -> None:
        t = Task(number=1, title="Setup", description="desc", acceptance_criteria="ac")
        assert t.number == 1
        assert t.title == "Setup"

    def test_frozen(self) -> None:
        t = Task(number=1, title="T", description="d", acceptance_criteria="a")
        with pytest.raises(AttributeError):
            t.number = 2  # type: ignore[misc]

    def test_number_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            Task(number=0, title="T", description="d", acceptance_criteria="a")

    def test_negative_number_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            Task(number=-1, title="T", description="d", acceptance_criteria="a")

    def test_empty_title_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Task(number=1, title="", description="d", acceptance_criteria="a")

    def test_whitespace_only_title_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Task(number=1, title="   ", description="d", acceptance_criteria="a")

    def test_empty_description_allowed(self) -> None:
        t = Task(number=1, title="T", description="", acceptance_criteria="")
        assert t.description == ""


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


class TestSpec:
    def _make_spec(self, **overrides) -> Spec:
        defaults = dict(
            number=1,
            slug="foundation",
            title="Foundation",
            path=Path("/specs/01-foundation.md"),
            sections={"Summary": "text"},
        )
        defaults.update(overrides)
        return Spec(**defaults)

    def test_valid_spec(self) -> None:
        s = self._make_spec()
        assert s.number == 1
        assert s.slug == "foundation"
        assert s.status == SpecStatus.PENDING

    def test_negative_number_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            self._make_spec(number=-1)

    def test_zero_number_allowed(self) -> None:
        s = self._make_spec(number=0)
        assert s.number == 0

    def test_empty_slug_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            self._make_spec(slug="")

    def test_whitespace_slug_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            self._make_spec(slug="   ")

    def test_dependencies_coerced_from_list(self) -> None:
        s = self._make_spec(dependencies=[1, 2, 3])
        assert isinstance(s.dependencies, tuple)
        assert s.dependencies == (1, 2, 3)

    def test_dependencies_tuple_kept(self) -> None:
        s = self._make_spec(dependencies=(4, 5))
        assert s.dependencies == (4, 5)

    def test_status_coerced_from_string(self) -> None:
        s = self._make_spec(status="done")
        assert s.status is SpecStatus.DONE

    def test_status_enum_kept(self) -> None:
        s = self._make_spec(status=SpecStatus.BUILDING)
        assert s.status is SpecStatus.BUILDING

    def test_mutable_status(self) -> None:
        s = self._make_spec()
        s.status = SpecStatus.DONE
        assert s.status is SpecStatus.DONE

    def test_repr_concise(self) -> None:
        s = self._make_spec()
        r = repr(s)
        assert "number=1" in r
        assert "slug='foundation'" in r
        assert "sections" not in r  # suppressed in repr

    def test_sections_not_in_repr(self) -> None:
        s = self._make_spec(sections={"A": "very long content" * 100})
        assert "very long content" not in repr(s)


# ---------------------------------------------------------------------------
# BuildPlan
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def test_valid_plan(self) -> None:
        bp = BuildPlan(order=(1, 2, 3))
        assert bp.order == (1, 2, 3)

    def test_frozen(self) -> None:
        bp = BuildPlan(order=(1,))
        with pytest.raises(AttributeError):
            bp.order = (2,)  # type: ignore[misc]

    def test_coerces_list_to_tuple(self) -> None:
        bp = BuildPlan(order=[1, 2])  # type: ignore[arg-type]
        assert isinstance(bp.order, tuple)
        assert bp.order == (1, 2)

    def test_duplicate_numbers_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            BuildPlan(order=(1, 2, 1))

    def test_empty_order_allowed(self) -> None:
        bp = BuildPlan(order=())
        assert bp.order == ()


# ---------------------------------------------------------------------------
# TaskList
# ---------------------------------------------------------------------------


class TestTaskList:
    def _make_task(self, number: int = 1) -> Task:
        return Task(
            number=number,
            title=f"Task {number}",
            description="desc",
            acceptance_criteria="ac",
        )

    def test_valid_task_list(self) -> None:
        tl = TaskList(
            spec_number=1,
            tasks=(self._make_task(),),
            path=Path("/tasks/tasks-01.md"),
        )
        assert tl.spec_number == 1
        assert len(tl.tasks) == 1

    def test_frozen(self) -> None:
        tl = TaskList(
            spec_number=1,
            tasks=(self._make_task(),),
            path=Path("/t.md"),
        )
        with pytest.raises(AttributeError):
            tl.spec_number = 2  # type: ignore[misc]

    def test_negative_spec_number_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            TaskList(
                spec_number=-1,
                tasks=(self._make_task(),),
                path=Path("/t.md"),
            )

    def test_empty_tasks_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one task"):
            TaskList(spec_number=0, tasks=(), path=Path("/t.md"))

    def test_coerces_list_to_tuple(self) -> None:
        tl = TaskList(
            spec_number=1,
            tasks=[self._make_task()],  # type: ignore[arg-type]
            path=Path("/t.md"),
        )
        assert isinstance(tl.tasks, tuple)


# ---------------------------------------------------------------------------
# SpecSet
# ---------------------------------------------------------------------------


class TestSpecSet:
    def _make_spec_set(self, **overrides) -> SpecSet:
        spec = Spec(
            number=1,
            slug="foundation",
            title="Foundation",
            path=Path("/specs/01-foundation.md"),
            sections={"Summary": "s"},
            status=SpecStatus.PENDING,
        )
        spec2 = Spec(
            number=2,
            slug="api",
            title="API",
            path=Path("/specs/02-api.md"),
            sections={"Summary": "s"},
            status=SpecStatus.DONE,
        )
        defaults = dict(
            specs={1: spec, 2: spec2},
            constitution=Constitution(path=Path("/c.md"), content="c"),
            build_plan=BuildPlan(order=(1, 2)),
            research_docs={},
            spec_dir=Path("/specs"),
        )
        defaults.update(overrides)
        return SpecSet(**defaults)

    def test_get_spec_found(self) -> None:
        ss = self._make_spec_set()
        s = ss.get_spec(1)
        assert s.slug == "foundation"

    def test_get_spec_not_found_raises(self) -> None:
        ss = self._make_spec_set()
        with pytest.raises(SpecNotFoundError):
            ss.get_spec(99)

    def test_next_actionable_finds_pending(self) -> None:
        ss = self._make_spec_set()
        result = ss.next_actionable(SpecStatus.PENDING)
        assert result is not None
        assert result.number == 1

    def test_next_actionable_finds_done(self) -> None:
        ss = self._make_spec_set()
        result = ss.next_actionable(SpecStatus.DONE)
        assert result is not None
        assert result.number == 2

    def test_next_actionable_none_when_no_match(self) -> None:
        ss = self._make_spec_set()
        result = ss.next_actionable(SpecStatus.BUILDING)
        assert result is None

    def test_next_actionable_follows_build_plan_order(self) -> None:
        spec1 = Spec(
            number=1, slug="a", title="A", path=Path("/1.md"),
            sections={}, status=SpecStatus.PENDING,
        )
        spec2 = Spec(
            number=2, slug="b", title="B", path=Path("/2.md"),
            sections={}, status=SpecStatus.PENDING,
        )
        ss = self._make_spec_set(
            specs={1: spec1, 2: spec2},
            build_plan=BuildPlan(order=(2, 1)),
        )
        result = ss.next_actionable(SpecStatus.PENDING)
        assert result is not None
        assert result.number == 2  # build plan says 2 first

    def test_next_actionable_skips_missing_spec_numbers(self) -> None:
        ss = self._make_spec_set(
            build_plan=BuildPlan(order=(99, 1, 2)),
        )
        result = ss.next_actionable(SpecStatus.PENDING)
        assert result is not None
        assert result.number == 1

    def test_next_actionable_empty_build_plan(self) -> None:
        ss = self._make_spec_set(build_plan=BuildPlan(order=()))
        result = ss.next_actionable(SpecStatus.PENDING)
        assert result is None

    def test_get_spec_returns_correct_among_multiple(self) -> None:
        ss = self._make_spec_set()
        s = ss.get_spec(2)
        assert s.slug == "api"


# ---------------------------------------------------------------------------
# Edge cases — Constitution
# ---------------------------------------------------------------------------


class TestConstitutionEdgeCases:
    def test_empty_content_allowed(self) -> None:
        c = Constitution(path=Path("/c.md"), content="")
        assert c.content == ""


# ---------------------------------------------------------------------------
# Edge cases — Task
# ---------------------------------------------------------------------------


class TestTaskEdgeCases:
    def test_large_number_allowed(self) -> None:
        t = Task(number=999, title="Big", description="", acceptance_criteria="")
        assert t.number == 999

    def test_title_with_special_characters(self) -> None:
        t = Task(number=1, title="Foo: bar — baz", description="d", acceptance_criteria="a")
        assert t.title == "Foo: bar — baz"


# ---------------------------------------------------------------------------
# Edge cases — Spec
# ---------------------------------------------------------------------------


class TestSpecEdgeCases:
    def test_invalid_status_string_raises(self) -> None:
        with pytest.raises(ValueError):
            Spec(
                number=1,
                slug="test",
                title="T",
                path=Path("/t.md"),
                sections={},
                status="bogus",
            )

    def test_empty_dependencies_tuple(self) -> None:
        s = Spec(
            number=1,
            slug="test",
            title="T",
            path=Path("/t.md"),
            sections={},
            dependencies=(),
        )
        assert s.dependencies == ()

    def test_repr_includes_status(self) -> None:
        s = Spec(
            number=1,
            slug="test",
            title="T",
            path=Path("/t.md"),
            sections={},
            status=SpecStatus.DONE,
        )
        r = repr(s)
        assert "done" in r


# ---------------------------------------------------------------------------
# Edge cases — BuildPlan
# ---------------------------------------------------------------------------


class TestBuildPlanEdgeCases:
    def test_single_element(self) -> None:
        bp = BuildPlan(order=(1,))
        assert bp.order == (1,)

    def test_tuple_stays_tuple(self) -> None:
        bp = BuildPlan(order=(1, 2))
        assert type(bp.order) is tuple


# ---------------------------------------------------------------------------
# Edge cases — TaskList
# ---------------------------------------------------------------------------


class TestTaskListEdgeCases:
    def test_zero_spec_number_allowed(self) -> None:
        t = Task(number=1, title="T", description="d", acceptance_criteria="a")
        tl = TaskList(spec_number=0, tasks=(t,), path=Path("/t.md"))
        assert tl.spec_number == 0

    def test_multiple_tasks(self) -> None:
        t1 = Task(number=1, title="A", description="d", acceptance_criteria="a")
        t2 = Task(number=2, title="B", description="d", acceptance_criteria="a")
        tl = TaskList(spec_number=1, tasks=(t1, t2), path=Path("/t.md"))
        assert len(tl.tasks) == 2


# ---------------------------------------------------------------------------
# SpecSet — get_spec exception chaining
# ---------------------------------------------------------------------------


class TestSpecSetGetSpecChaining:
    def test_get_spec_not_found_suppresses_cause(self) -> None:
        """SpecSet.get_spec uses 'from None' — cause should be suppressed."""
        ss = SpecSet(
            specs={},
            constitution=Constitution(path=Path("/c.md"), content="c"),
            build_plan=BuildPlan(order=()),
            research_docs={},
            spec_dir=Path("/specs"),
        )
        with pytest.raises(SpecNotFoundError) as exc_info:
            ss.get_spec(99)
        assert exc_info.value.__cause__ is None


# ---------------------------------------------------------------------------
# Spec — invalid status type
# ---------------------------------------------------------------------------


class TestSpecInvalidStatusType:
    def test_non_string_non_enum_status_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            Spec(
                number=1,
                slug="test",
                title="T",
                path=Path("/t.md"),
                sections={},
                status=42,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# SpecStatus — lifecycle ordering
# ---------------------------------------------------------------------------


class TestSpecStatusLifecycle:
    def test_all_expected_statuses_exist(self) -> None:
        expected = {"pending", "planned", "building", "done"}
        actual = {s.value for s in SpecStatus}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        assert issubclass(SpecStatus, str)
