"""Load a spec directory into a SpecSet.

Discovers numbered specs, parses sections by headings, extracts
dependencies, reads the constitution, research docs, README build
order, and merges in statuses from ``.sdd-status.json``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sdd_copilot.exceptions import ConstitutionMissingError
from sdd_copilot.models import BuildPlan, Constitution, Spec, SpecSet, SpecStatus
from sdd_copilot.status import load_all_statuses

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SPEC_FILENAME_RE = re.compile(r"^(\d{2})-(.+)\.md$")
_DEPENDENCY_RE = re.compile(r"\*\*Spec\s+(\d+)\*\*")
_README_SPEC_RE = re.compile(r"(\d{2})-")


def _parse_sections(text: str) -> dict[str, str]:
    """Split markdown *text* on ``## `` headings into a {heading: body} map.

    The content before the first ``## `` heading (if any) is stored under
    the key ``"_preamble"``.
    """
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            # Flush previous section
            if current_heading is not None:
                sections[current_heading] = "".join(current_lines).strip()
            else:
                preamble = "".join(current_lines).strip()
                if preamble:
                    sections["_preamble"] = preamble
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Flush the last section
    if current_heading is not None:
        sections[current_heading] = "".join(current_lines).strip()
    else:
        preamble = "".join(current_lines).strip()
        if preamble:
            sections["_preamble"] = preamble

    return sections


def _extract_title(text: str) -> str:
    """Return the text of the first ``# `` heading, or ``""``."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return ""


def _extract_dependencies(sections: dict[str, str]) -> list[int]:
    """Pull spec numbers from the ``Dependencies`` section."""
    dep_text = sections.get("Dependencies", "")
    return sorted(set(int(m) for m in _DEPENDENCY_RE.findall(dep_text)))


def _parse_readme_build_order(readme_path: Path) -> list[int]:
    """Extract an ordered list of spec numbers from a README.

    Looks for lines that contain a ``NN-`` pattern (e.g. ``01-foundation``)
    and returns the numbers in the order they appear.
    """
    if not readme_path.exists():
        return []

    order: list[int] = []
    seen: set[int] = set()
    for line in readme_path.read_text(encoding="utf-8").splitlines():
        for m in _README_SPEC_RE.finditer(line):
            num = int(m.group(1))
            if num not in seen:
                order.append(num)
                seen.add(num)
    return order


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_spec_set(spec_dir: Path) -> SpecSet:
    """Load everything from *spec_dir* into a :class:`SpecSet`.

    Steps:
    1. Discover numbered spec files (``NN-slug.md``).
    2. Parse each spec's markdown into sections, extract dependencies.
    3. Read ``CONSTITUTION.md``.
    4. Parse ``README.md`` for build order.
    5. Read ``research/*.md`` documents.
    6. Merge statuses from ``.sdd-status.json``.
    """
    spec_dir = spec_dir.resolve()
    logger.info("Loading spec set from %s", spec_dir)

    # -- 1. Discover numbered specs -----------------------------------------
    all_statuses = load_all_statuses(spec_dir)
    specs: dict[int, Spec] = {}
    for path in sorted(spec_dir.glob("[0-9][0-9]-*.md")):
        match = _SPEC_FILENAME_RE.match(path.name)
        if not match:
            continue
        number = int(match.group(1))
        slug = match.group(2)
        text = path.read_text(encoding="utf-8")

        # -- 2. Parse sections, title, dependencies -------------------------
        sections = _parse_sections(text)
        title = _extract_title(text)
        dependencies = _extract_dependencies(sections)
        status = all_statuses.get(number, SpecStatus.PENDING)

        logger.debug("  Loaded spec %02d: %s", number, slug)
        specs[number] = Spec(
            number=number,
            slug=slug,
            title=title,
            path=path,
            sections=sections,
            dependencies=dependencies,
            status=status,
        )

    # -- 3. Read constitution -----------------------------------------------
    constitution_path = spec_dir / "CONSTITUTION.md"
    if not constitution_path.exists():
        raise ConstitutionMissingError(spec_dir)
    constitution = Constitution(
        path=constitution_path,
        content=constitution_path.read_text(encoding="utf-8"),
    )

    # -- 4. Parse README build order ----------------------------------------
    readme_path = spec_dir / "README.md"
    order = _parse_readme_build_order(readme_path)
    # Fall back to numerical order of discovered specs if README has none.
    if not order:
        order = sorted(specs.keys())
    build_plan = BuildPlan(order=tuple(order))

    # -- 5. Read research docs ----------------------------------------------
    research_docs: dict[str, str] = {}
    research_dir = spec_dir / "research"
    if research_dir.is_dir():
        for rpath in sorted(research_dir.glob("*.md")):
            research_docs[rpath.name] = rpath.read_text(encoding="utf-8")

    # -- 6. Assemble SpecSet ------------------------------------------------
    return SpecSet(
        specs=specs,
        constitution=constitution,
        build_plan=build_plan,
        research_docs=research_docs,
        spec_dir=spec_dir,
    )
