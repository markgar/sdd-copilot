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

    def test_empty_spec_dir_has_no_specs(self, tmp_path: Path) -> None:
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        assert len(ss.specs) == 0

    def test_spec_with_no_h1_title(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={"01-nohead.md": "No heading\n## Summary\nstuff"},
        )
        ss = load_spec_set(spec_dir)
        assert ss.specs[1].title == ""

    def test_multiple_research_files(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            research={"a.md": "A content", "b.md": "B content", "c.md": "C content"},
        )
        ss = load_spec_set(spec_dir)
        assert len(ss.research_docs) == 3

    def test_spec_filename_with_hyphens_in_slug(self, tmp_path: Path) -> None:
        spec_dir = self._setup_spec_dir(
            tmp_path,
            specs={"01-multi-word-slug.md": "# Multi Word\n## Summary\ntext"},
        )
        ss = load_spec_set(spec_dir)
        assert ss.specs[1].slug == "multi-word-slug"


# ---------------------------------------------------------------------------
# _parse_sections — additional edge cases
# ---------------------------------------------------------------------------


class TestParseSectionsEdgeCases:
    def test_duplicate_heading_last_wins(self) -> None:
        text = "## A\nFirst\n## A\nSecond"
        result = _parse_sections(text)
        assert result["A"] == "Second"

    def test_section_with_empty_body(self) -> None:
        text = "## A\n## B\nContent B"
        result = _parse_sections(text)
        assert result["A"] == ""
        assert result["B"] == "Content B"

    def test_only_preamble_no_headings(self) -> None:
        text = "Line 1\nLine 2\n"
        result = _parse_sections(text)
        assert "_preamble" in result
        assert len(result) == 1

    def test_heading_immediately_after_preamble(self) -> None:
        text = "Preamble\n## Section\nBody"
        result = _parse_sections(text)
        assert "_preamble" in result
        assert "Section" in result


# ---------------------------------------------------------------------------
# _extract_title — additional edge cases
# ---------------------------------------------------------------------------


class TestExtractTitleEdgeCases:
    def test_multiple_h1_returns_first(self) -> None:
        text = "# First\n# Second"
        assert _extract_title(text) == "First"

    def test_h1_after_content(self) -> None:
        text = "Some text\n# Title"
        assert _extract_title(text) == "Title"


# ---------------------------------------------------------------------------
# _extract_dependencies — additional edge cases
# ---------------------------------------------------------------------------


class TestExtractDependenciesEdgeCases:
    def test_duplicate_spec_numbers_deduplicated(self) -> None:
        sections = {"Dependencies": "**Spec 1** and again **Spec 1** and **Spec 2**"}
        result = _extract_dependencies(sections)
        assert result == [1, 2]


# ---------------------------------------------------------------------------
# load_spec_set — file filtering edge cases
# ---------------------------------------------------------------------------


class TestLoadSpecSetFiltering:
    def test_ignores_single_digit_prefix_files(self, tmp_path: Path) -> None:
        """Files like 1-test.md (single digit) should not match NN-slug pattern."""
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        (tmp_path / "1-bad.md").write_text("# Bad\n## Summary\nstuff", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        assert len(ss.specs) == 0

    def test_ignores_non_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        (tmp_path / "01-test.txt").write_text("not markdown", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        assert len(ss.specs) == 0

    def test_ignores_three_digit_prefix_files(self, tmp_path: Path) -> None:
        """Files like 001-test.md (three digits) should not match NN-slug pattern."""
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        (tmp_path / "001-test.md").write_text("# Test\n## Summary\nstuff", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        assert len(ss.specs) == 0


# ---------------------------------------------------------------------------
# load_spec_set — dependencies point to existing specs
# ---------------------------------------------------------------------------


class TestLoadSpecSetDependencies:
    def test_dependencies_loaded_as_tuple(self, tmp_path: Path) -> None:
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        (tmp_path / "01-a.md").write_text("# A\n## Summary\na", encoding="utf-8")
        (tmp_path / "02-b.md").write_text(
            "# B\n## Summary\nb\n## Dependencies\n**Spec 1**",
            encoding="utf-8",
        )
        ss = load_spec_set(tmp_path)
        assert isinstance(ss.specs[2].dependencies, tuple)
        assert ss.specs[2].dependencies == (1,)

    def test_spec_without_dependencies_gets_empty_tuple(self, tmp_path: Path) -> None:
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        (tmp_path / "01-a.md").write_text("# A\n## Summary\na", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        assert ss.specs[1].dependencies == ()


# ---------------------------------------------------------------------------
# load_spec_set — glob matches but regex doesn't
# ---------------------------------------------------------------------------


class TestLoadSpecSetGlobRegexMismatch:
    def test_glob_match_but_regex_no_match_is_skipped(self, tmp_path: Path) -> None:
        """A file like '00-.md' matches glob [0-9][0-9]-*.md but not the regex
        ^(\\d{2})-(.+)\\.md$ because the slug group (.+) can't match empty."""
        (tmp_path / "CONSTITUTION.md").write_text("C", encoding="utf-8")
        # Valid spec
        (tmp_path / "01-valid.md").write_text("# Valid\n## Summary\nv", encoding="utf-8")
        # Matches glob [0-9][0-9]-*.md but not regex (empty slug after dash)
        (tmp_path / "00-.md").write_text("# Empty Slug\n## Summary\nx", encoding="utf-8")
        ss = load_spec_set(tmp_path)
        # Only the valid spec should be loaded
        assert len(ss.specs) == 1
        assert 1 in ss.specs
        assert 0 not in ss.specs
