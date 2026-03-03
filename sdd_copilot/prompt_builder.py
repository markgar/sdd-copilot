"""Assemble XML-structured prompts for the planning and build agents.

Each public function returns a complete prompt string ready to hand to
the runner.  All I/O (reading specs, research, etc.) has already happened
— this module is pure string assembly over in-memory domain objects.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sdd_copilot.models import Spec, SpecSet, SpecStatus, Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RESEARCH_REF_RE = re.compile(r"research/([^\s)]+\.md)")


def _collect_research(spec: Spec, spec_set: SpecSet) -> dict[str, str]:
    """Return research docs referenced in the spec's ``Reference`` section.

    Falls back to an empty dict when the section is absent or no research
    filenames are found.
    """
    ref_text = spec.sections.get("Reference", "")
    if not ref_text:
        return {}

    referenced: dict[str, str] = {}
    for match in _RESEARCH_REF_RE.finditer(ref_text):
        filename = match.group(1)
        content = spec_set.research_docs.get(filename)
        if content is not None:
            referenced[filename] = content
        else:
            logger.warning(
                "Spec %02d references research/%s but it was not found",
                spec.number,
                filename,
            )
    return referenced


def _build_dependency_context(spec: Spec, spec_set: SpecSet) -> str:
    """Build a summary block for each completed dependency spec.

    Only specs whose status is ``DONE`` are included — in-progress or
    pending dependencies are omitted so the agent doesn't build on
    unfinished work.
    """
    if not spec.dependencies:
        return ""

    parts: list[str] = []
    for dep_number in spec.dependencies:
        dep = spec_set.specs.get(dep_number)
        if dep is None:
            logger.warning(
                "Spec %02d depends on spec %02d which was not found",
                spec.number,
                dep_number,
            )
            continue
        if dep.status != SpecStatus.DONE:
            continue
        summary = dep.sections.get("Summary", "")
        acceptance = dep.sections.get("Acceptance Criteria", "")
        parts.append(
            f"# Spec {dep.number:02d}: {dep.title}\n"
            f"## Summary\n{summary}\n"
            f"## Acceptance Criteria\n{acceptance}"
        )

    return "\n\n".join(parts)


def _full_spec_text(spec: Spec) -> str:
    """Reconstruct the full spec markdown from its parsed sections."""
    parts: list[str] = []
    preamble = spec.sections.get("_preamble", "")
    if preamble:
        parts.append(preamble)

    for heading, body in spec.sections.items():
        if heading == "_preamble":
            continue
        parts.append(f"## {heading}\n{body}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_planning_prompt(spec: Spec, spec_set: SpecSet) -> str:
    """Assemble the planning prompt for a single spec.

    The prompt instructs the agent to decompose the spec's
    ``## What to Build`` section into ordered, granular implementation tasks.
    """
    logger.info("Building planning prompt for spec %02d: %s", spec.number, spec.title)

    research = _collect_research(spec, spec_set)
    dep_context = _build_dependency_context(spec, spec_set)

    # -- Assemble XML blocks ------------------------------------------------
    sections: list[str] = []

    sections.append(
        "<system>\n"
        "You are an SDD planning agent. Your job is to decompose a specification\n"
        "into ordered, granular implementation tasks.\n"
        "</system>"
    )

    sections.append(
        f"<constitution>\n"
        f"{spec_set.constitution.content}\n"
        f"</constitution>"
    )

    sections.append(
        f"<spec>\n"
        f"{_full_spec_text(spec)}\n"
        f"</spec>"
    )

    if research:
        research_parts = "\n\n".join(
            f"### {filename}\n{content}" for filename, content in research.items()
        )
        sections.append(f"<research>\n{research_parts}\n</research>")

    if dep_context:
        sections.append(
            f"<completed_dependencies>\n{dep_context}\n</completed_dependencies>"
        )

    sections.append(
        "<instructions>\n"
        'Decompose the "## What to Build" section into ordered, granular\n'
        "implementation tasks. Each task should be a single coherent unit of\n"
        "work that one coding session can complete.\n"
        "\n"
        "Output format — use EXACTLY this markdown structure:\n"
        "\n"
        "## Task 1: [short title]\n"
        "### Description\n"
        "[What to implement — specific functions, data structures, logic]\n"
        "### Acceptance Criteria\n"
        "[Relevant GIVEN/WHEN/THEN from the spec, or new micro-criteria]\n"
        "\n"
        "## Task 2: [short title]\n"
        "...\n"
        "</instructions>"
    )

    return "\n\n".join(sections)


def build_task_prompt(task: Task, spec: Spec, spec_set: SpecSet) -> str:
    """Assemble the build prompt for a single task within a spec.

    The prompt gives the agent constitution context, a summary of the
    parent spec, and the specific task to implement.
    """
    logger.info(
        "Building task prompt for spec %02d, task %d: %s",
        spec.number,
        task.number,
        task.title,
    )

    summary = spec.sections.get("Summary", "")
    dependencies = spec.sections.get("Dependencies", "")

    sections: list[str] = []

    sections.append(
        "<system>\n"
        "You are an SDD build agent. Implement exactly one task from\n"
        "a specification. Follow the constitution's principles strictly.\n"
        "</system>"
    )

    sections.append(
        f"<constitution>\n"
        f"{spec_set.constitution.content}\n"
        f"</constitution>"
    )

    sections.append(
        f"<spec_context>\n"
        f"# Spec {spec.number:02d}: {spec.title}\n"
        f"## Summary\n"
        f"{summary}\n"
        f"## Dependencies\n"
        f"{dependencies}\n"
        f"</spec_context>"
    )

    sections.append(
        f"<task>\n"
        f"## Task {task.number}: {task.title}\n"
        f"### Description\n"
        f"{task.description}\n"
        f"### Acceptance Criteria\n"
        f"{task.acceptance_criteria}\n"
        f"</task>"
    )

    sections.append(
        "<instructions>\n"
        "Implement this task. Follow the constitution's principles.\n"
        "When done, verify your work against the acceptance criteria.\n"
        "</instructions>"
    )

    return "\n\n".join(sections)
