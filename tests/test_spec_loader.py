"""Tests for sdd_copilot.spec_loader — loading a spec directory."""

import json
from pathlib import Path

import pytest

from sdd_copilot.exceptions import ConstitutionMissingError
from sdd_copilot.models import SpecStatus
from sdd_copilot.spec_loader import (
    _extract_dependencies,
    _extract_title,
    _parse_readme_build_order,
    _parse_sections,
    load_spec_set,
)


# ---------------------------------------------------------------------------
# _parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    def test_single_section(self) -> None:
        text = "## Summary\nThis is the summary."
        result = _parse_sections(text)
        assert "Summary" in result
        assert result["Summary"] == "This is the summary."

    def test_multiple_sections(self) -> None:
        text = "## A\nContent A\n## B\nContent B"
        result = _parse_sections(text)
        assert result["A"] == "Content A"
        assert result["B"] == "Content B"

    def test_preamble_captured(self) -> None:
        text = "# Title\n\nIntro text\n\n## Summary\nBody"
        result = _parse_sections(text)
        assert "_preamble" in result
        assert "Title" in result["_preamble"]

    def test_no_headings(self) -> None:
        text = "Just some text\nwith lines"
        result = _parse_sections(text)
        assert "_preamble" in result
        assert "Just some text" in result["_preamble"]

    def test_empty_string(self) -> None:
        result = _parse_sections("")
        assert result == {}

    def test_heading_with_extra_spaces(self) -> None:
        text = "## My Section  \nContent"
        result = _parse_sections(text)
        assert "My Section" in result

    def test_multiline_section_content(self) -> None:
        text = "## A\nLine 1\nLine 2\nLine 3"
        result = _parse_sections(text)
        assert "Line 1" in result["A"]
        assert "Line 3" in result["A"]


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_finds_h1(self) -> None:
        text = "# My Title\n\nBody"
        assert _extract_title(text) == "My Title"

    def test_returns_empty_when_no_h1(self) -> None:
        text = "## Not H1\nBody"
        assert _extract_title(text) == ""

    def test_strips_whitespace(self) -> None:
        text = "#   Spaced Title  \nBody"
        assert _extract_title(text) == "Spaced Title"


# ---------------------------------------------------------------------------
# _extract_dependencies
# ---------------------------------------------------------------------------


class TestExtractDependencies:
    def test_finds_spec_numbers(self) -> None:
        sections = {"Dependencies": "Depends on **Spec 1** and **Spec 3**"}
        result = _extract_dependencies(sections)
        assert result == [1, 3]

    def test_no_dependencies_section(self) -> None:
        result = _extract_dependencies({"Summary": "s"})
        assert result == []

    def test_empty_dependencies_section(self) -> None:
        result = _extract_dependencies({"Dependencies": "None"})
        assert result == []

    def test_sorted_output(self) -> None:
        sections = {"Dependencies": "**Spec 5**, **Spec 2**, **Spec 1**"}
        result = _extract_dependencies(sections)
        assert result == [1, 2, 5]


# ---------------------------------------------------------------------------
# _parse_readme_build_order
# ---------------------------------------------------------------------------


class TestParseReadmeBuildOrder:
    def test_extracts_spec_numbers(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Specs\n- 01-foundation\n- 02-api\n- 03-ui\n",
            encoding="utf-8",
        )
        result = _parse_readme_build_order(readme)
        assert result == [1, 2, 3]

    def test_no_duplicates(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text(
            "01-foundation\n01-foundation\n02-api\n",
            encoding="utf-8",
        )
        result = _parse_readme_build_order(readme)
        assert result == [1, 2]

    def test_missing_readme_returns_empty(self, tmp_path: Path) -> None:
        result = _parse_readme_build_order(tmp_path / "README.md")
        assert result == []

    def test_readme_with_no_specs_returns_empty(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# Just a readme\nNo specs here.\n", encoding="utf-8")
        result = _parse_readme_build_order(readme)
        assert result == []


# ---------------------------------------------------------------------------
# load_spec_set — integration-style tests with tmp_path
# ---------------------------------------------------------------------------


class TestLoadSpecSet:
    def _setup_spec_dir(
        self,
        tmp_path: Path,
        *,
        specs: dict[str, str] | None = None,
        constitution: str = "Be good.",
        readme: str | None = None,
        status: dict[str, str] | None = None,
        research: dict[str, str] | None = None,
    ) -> Path:
        """Create a minimal spec directory structure."""
        if specs is None:
            specs = {
                "01-foundation.md": "# Foundation\n\n## Summary\nBase layer\n## Dependencies\nNone",
            }
        for name, content in specs.items():
            (tmp_path / name).write_text(content, encoding="utf-8")

        (tmp_path / "CONSTITUTION.md").write_text(constitution, encoding="utf-8")

        if readme is not None:
            (tmp_path / "README.md").write_text(readme, encoding="utf-8")

        if status is not None:
            (tmp_path / ".sdd-status.json").write_text(
                json.dumps(status), encoding="utf-8"
            )

        if research is not None:
            rd = tmp_path / "research"
            rd.mkdir()
            for name, content in research.items():
                (rd / name).write_text(content, encoding="utf-8")

        return tmp_path

    def test_loads_single_spec(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path)
        ss = load_spec_set(spec_dir)
        assert 1 in ss.specs
        assert ss.specs[1].slug == "foundation"
        assert ss.specs[1].title == "Foundation"

    def test_loads_constitution(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path, constitution="Rules here")
        ss = load_spec_set(spec_dir)
        assert ss.constitution.content == "Rules here"

    def test_missing_constitution_raises(self, tmp_path: Path) -> None:
        (tmp_path / "01-test.md").write_text(
            "# Test\n## Summary\nTest", encoding="utf-8"
        )
        with pytest.raises(ConstitutionMissingError):
            load_spec_set(tmp_path)

    def test_merges_statuses(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path, status={"1": "done"}
        )
        ss = load_spec_set(spec_dir)
        assert ss.specs[1].status == SpecStatus.DONE

    def test_default_status_is_pending(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path)
        ss = load_spec_set(spec_dir)
        assert ss.specs[1].status == SpecStatus.PENDING

    def test_build_order_from_readme(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={
                "01-a.md": "# A\n## Summary\na",
                "02-b.md": "# B\n## Summary\nb",
            },
            readme="Order:\n- 02-b\n- 01-a\n",
        )
        ss = load_spec_set(spec_dir)
        assert ss.build_plan.order == (2, 1)

    def test_build_order_fallback_to_numerical(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={
                "02-b.md": "# B\n## Summary\nb",
                "01-a.md": "# A\n## Summary\na",
            },
        )
        ss = load_spec_set(spec_dir)
        assert ss.build_plan.order == (1, 2)

    def test_loads_research_docs(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            research={"notes.md": "research content"},
        )
        ss = load_spec_set(spec_dir)
        assert "notes.md" in ss.research_docs
        assert ss.research_docs["notes.md"] == "research content"

    def test_no_research_dir_ok(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path)
        ss = load_spec_set(spec_dir)
        assert ss.research_docs == {}

    def test_extracts_dependencies(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={
                "01-a.md": "# A\n## Summary\na",
                "02-b.md": "# B\n## Summary\nb\n## Dependencies\n**Spec 1**",
            },
        )
        ss = load_spec_set(spec_dir)
        assert ss.specs[2].dependencies == (1,)

    def test_multiple_specs_loaded(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={
                "01-a.md": "# A\n## Summary\na",
                "02-b.md": "# B\n## Summary\nb",
                "03-c.md": "# C\n## Summary\nc",
            },
        )
        ss = load_spec_set(spec_dir)
        assert len(ss.specs) == 3

    def test_ignores_non_spec_md_files(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path)
        (tmp_path / "notes.md").write_text("not a spec", encoding="utf-8")
        ss = load_spec_set(spec_dir)
        assert len(ss.specs) == 1

    def test_spec_dir_resolved(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(tmp_path)
        ss = load_spec_set(spec_dir)
        assert ss.spec_dir.is_absolute()
