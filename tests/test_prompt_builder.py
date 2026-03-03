"""Tests for sdd_copilot.prompt_builder — XML prompt assembly."""

from pathlib import Path

import pytest

from sdd_copilot.models import (
    BuildPlan,
    Constitution,
    Spec,
    SpecSet,
    SpecStatus,
    Task,
)
from sdd_copilot.prompt_builder import (
    _build_dependency_context,
    _collect_research,
    _full_spec_text,
    build_planning_prompt,
    build_task_prompt,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_spec(
    number: int = 1,
    slug: str = "foundation",
    title: str = "Foundation",
    sections: dict[str, str] | None = None,
    dependencies: tuple[int, ...] = (),
    status: SpecStatus = SpecStatus.PENDING,
) -> Spec:
    return Spec(
        number=number,
        slug=slug,
        title=title,
        path=Path(f"/specs/{number:02d}-{slug}.md"),
        sections=sections or {"Summary": "summary text", "What to Build": "build this"},
        dependencies=dependencies,
        status=status,
    )


def _make_spec_set(
    specs: dict[int, Spec] | None = None,
    constitution_content: str = "Be excellent.",
    research_docs: dict[str, str] | None = None,
    build_plan_order: tuple[int, ...] = (1,),
) -> SpecSet:
    if specs is None:
        specs = {1: _make_spec()}
    return SpecSet(
        specs=specs,
        constitution=Constitution(path=Path("/c.md"), content=constitution_content),
        build_plan=BuildPlan(order=build_plan_order),
        research_docs=research_docs or {},
        spec_dir=Path("/specs"),
    )


# ---------------------------------------------------------------------------
# _full_spec_text
# ---------------------------------------------------------------------------


class TestFullSpecText:
    def test_includes_sections(self) -> None:
        spec = _make_spec(sections={"Summary": "summary", "Details": "details"})
        text = _full_spec_text(spec)
        assert "## Summary" in text
        assert "summary" in text
        assert "## Details" in text

    def test_includes_preamble(self) -> None:
        spec = _make_spec(sections={"_preamble": "# Title\n\nIntro", "Summary": "s"})
        text = _full_spec_text(spec)
        assert "# Title" in text

    def test_preamble_not_headed(self) -> None:
        spec = _make_spec(sections={"_preamble": "preamble text", "A": "a"})
        text = _full_spec_text(spec)
        assert "## _preamble" not in text


# ---------------------------------------------------------------------------
# _collect_research
# ---------------------------------------------------------------------------


class TestCollectResearch:
    def test_no_reference_section(self) -> None:
        spec = _make_spec(sections={"Summary": "s"})
        ss = _make_spec_set(specs={1: spec})
        assert _collect_research(spec, ss) == {}

    def test_finds_referenced_research(self) -> None:
        spec = _make_spec(
            sections={"Reference": "See research/api-design.md for details"}
        )
        ss = _make_spec_set(
            specs={1: spec},
            research_docs={"api-design.md": "API design content"},
        )
        result = _collect_research(spec, ss)
        assert "api-design.md" in result
        assert result["api-design.md"] == "API design content"

    def test_missing_research_returns_empty(self) -> None:
        spec = _make_spec(
            sections={"Reference": "See research/missing.md"}
        )
        ss = _make_spec_set(specs={1: spec}, research_docs={})
        result = _collect_research(spec, ss)
        assert result == {}

    def test_multiple_references(self) -> None:
        spec = _make_spec(
            sections={
                "Reference": "See research/a.md and research/b.md"
            }
        )
        ss = _make_spec_set(
            specs={1: spec},
            research_docs={"a.md": "A", "b.md": "B"},
        )
        result = _collect_research(spec, ss)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _build_dependency_context
# ---------------------------------------------------------------------------


class TestBuildDependencyContext:
    def test_no_dependencies(self) -> None:
        spec = _make_spec(dependencies=())
        ss = _make_spec_set(specs={1: spec})
        assert _build_dependency_context(spec, ss) == ""

    def test_done_dependency_included(self) -> None:
        dep = _make_spec(
            number=1,
            title="Dep",
            sections={"Summary": "dep summary", "Acceptance Criteria": "ac"},
            status=SpecStatus.DONE,
        )
        spec = _make_spec(number=2, dependencies=(1,))
        ss = _make_spec_set(
            specs={1: dep, 2: spec},
            build_plan_order=(1, 2),
        )
        ctx = _build_dependency_context(spec, ss)
        assert "dep summary" in ctx
        assert "Spec 01" in ctx

    def test_pending_dependency_excluded(self) -> None:
        dep = _make_spec(number=1, status=SpecStatus.PENDING)
        spec = _make_spec(number=2, dependencies=(1,))
        ss = _make_spec_set(
            specs={1: dep, 2: spec},
            build_plan_order=(1, 2),
        )
        ctx = _build_dependency_context(spec, ss)
        assert ctx == ""

    def test_missing_dependency_returns_empty_string(self) -> None:
        spec = _make_spec(number=2, dependencies=(99,))
        ss = _make_spec_set(specs={2: spec}, build_plan_order=(2,))
        ctx = _build_dependency_context(spec, ss)
        assert ctx == ""


# ---------------------------------------------------------------------------
# build_planning_prompt
# ---------------------------------------------------------------------------


class TestBuildPlanningPrompt:
    def test_contains_required_xml_sections(self) -> None:
        spec = _make_spec()
        ss = _make_spec_set(specs={1: spec})
        prompt = build_planning_prompt(spec, ss)

        assert "<system>" in prompt
        assert "</system>" in prompt
        assert "<constitution>" in prompt
        assert "Be excellent." in prompt
        assert "<spec>" in prompt
        assert "<instructions>" in prompt

    def test_contains_spec_content(self) -> None:
        spec = _make_spec(sections={"What to Build": "Build the widget"})
        ss = _make_spec_set(specs={1: spec})
        prompt = build_planning_prompt(spec, ss)
        assert "Build the widget" in prompt

    def test_includes_research_when_referenced(self) -> None:
        spec = _make_spec(
            sections={
                "Reference": "See research/notes.md",
                "Summary": "s",
            }
        )
        ss = _make_spec_set(
            specs={1: spec},
            research_docs={"notes.md": "Research content here"},
        )
        prompt = build_planning_prompt(spec, ss)
        assert "<research>" in prompt
        assert "Research content here" in prompt

    def test_no_research_tag_when_none(self) -> None:
        spec = _make_spec(sections={"Summary": "s"})
        ss = _make_spec_set(specs={1: spec})
        prompt = build_planning_prompt(spec, ss)
        assert "<research>" not in prompt

    def test_includes_dependency_context(self) -> None:
        dep = _make_spec(
            number=1,
            title="Dep",
            sections={"Summary": "dep sum", "Acceptance Criteria": "ac"},
            status=SpecStatus.DONE,
        )
        spec = _make_spec(number=2, dependencies=(1,))
        ss = _make_spec_set(
            specs={1: dep, 2: spec},
            build_plan_order=(1, 2),
        )
        prompt = build_planning_prompt(spec, ss)
        assert "<completed_dependencies>" in prompt
        assert "dep sum" in prompt

    def test_no_dependency_tag_when_none(self) -> None:
        spec = _make_spec(dependencies=())
        ss = _make_spec_set(specs={1: spec})
        prompt = build_planning_prompt(spec, ss)
        assert "<completed_dependencies>" not in prompt


# ---------------------------------------------------------------------------
# build_task_prompt
# ---------------------------------------------------------------------------


class TestBuildTaskPrompt:
    def _make_task(self) -> Task:
        return Task(
            number=1,
            title="Implement widget",
            description="Build the widget module",
            acceptance_criteria="GIVEN widget WHEN called THEN works",
        )

    def test_contains_required_xml_sections(self) -> None:
        task = self._make_task()
        spec = _make_spec()
        ss = _make_spec_set(specs={1: spec})
        prompt = build_task_prompt(task, spec, ss)

        assert "<system>" in prompt
        assert "<constitution>" in prompt
        assert "<spec_context>" in prompt
        assert "<task>" in prompt
        assert "<instructions>" in prompt

    def test_contains_task_details(self) -> None:
        task = self._make_task()
        spec = _make_spec()
        ss = _make_spec_set(specs={1: spec})
        prompt = build_task_prompt(task, spec, ss)
        assert "Implement widget" in prompt
        assert "Build the widget module" in prompt
        assert "GIVEN widget" in prompt

    def test_contains_spec_context(self) -> None:
        task = self._make_task()
        spec = _make_spec(
            sections={"Summary": "Spec summary", "Dependencies": "None"},
        )
        ss = _make_spec_set(specs={1: spec})
        prompt = build_task_prompt(task, spec, ss)
        assert "Spec summary" in prompt

    def test_contains_constitution(self) -> None:
        task = self._make_task()
        spec = _make_spec()
        ss = _make_spec_set(
            specs={1: spec}, constitution_content="Rule #1"
        )
        prompt = build_task_prompt(task, spec, ss)
        assert "Rule #1" in prompt
