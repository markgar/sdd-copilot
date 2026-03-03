# Copilot Instructions — SDD Copilot

## Project

Python 3.11+ CLI tool (`sdd`) that orchestrates Spec-Driven Development by shelling out to `copilot` CLI. Two main loops: **plan** (decompose a spec into tasks) and **build** (execute each task in a fresh copilot session). Entry point: `sdd_copilot/cli.py` via `sdd` console script.

## Key Files

- **BACKLOG.md** — ordered stories; build the next unchecked one.
- **PLAN.md** — full architecture, module contracts, and prompt formats.
- **ENGINEERING_STANDARDS.md** — mandatory code standards; read before every build.

## Architecture Rules

- **Tiered dependency graph.** Core types (`exceptions.py`, `models.py`) sit at the bottom. Service modules (`status.py`, `runner.py`, `prompt_builder.py`) depend on core. Orchestration (`spec_loader.py`, `planner.py`, `builder.py`) depends on services + core. Entry point (`cli.py`) depends on everything. **A module may only import from its own tier or below.**
- **`models.py` is the centre.** All domain types live here. Other modules depend on it, not the reverse.
- **Custom exceptions** inherit from `SddError` in `exceptions.py`. Always include the `Path` and a human-readable `reason`.

## Code Conventions

- **Enums over magic strings.** Use `SpecStatus` (a `StrEnum`), never bare `"pending"` / `"done"` literals.
- **Frozen dataclasses for value objects.** Use `frozen=True` and `tuple` (not `list`) for immutable collections (`BuildPlan`, `TaskList`, `Task`). On mutable dataclasses, fields that don't change after construction still use `tuple`.
- **Validate at construction — every dataclass.** `__post_init__` rejects invalid state — fail fast. This includes container types, not just leaf objects.
- **Coerce container types in `__post_init__`** (list → tuple). Do **not** coerce types in regular function bodies — that's a type lie.
- **Type signatures honestly.** Use `Path` not `str` for paths, `SpecStatus` not `str` for statuses, `Spec | None` when nullable. No `# type: ignore` coercion in function bodies.
- **Repr should be concise.** Suppress large fields with `repr=False`; override `__repr__` to show only key identifiers.
- **`removeprefix` / `removesuffix`**, never `lstrip` / `rstrip` for known prefix/suffix removal.
- **Read I/O once, pass the result.** No repeated disk reads in loops.
- **No silent fallbacks.** When expected resources are missing, log a warning or raise. Never return an empty default without telling the user.
- **DRY for constants.** Define default values (model, timeout, etc.) once in the owning module; import elsewhere. No duplicated literals.
- **Chain exceptions with `from`.** Every `except` that re-raises must use `as exc` / `from exc` — consistently across all branches.
- **Module-level loggers** (`logging.getLogger(__name__)`). Configure format/level only in the CLI entry point.
- **Underscore means module-private.** Never import `_functions` from another module; make them public if cross-module use is needed.
- **No unused imports.** Every `import` statement must be used.
- **Exception test coverage must be exhaustive.** New exception classes must be added to the parametrized hierarchy test and get a dedicated test class.

## CLI Pattern

Shared options (`--spec-dir`, `--model`, `--verbose`) go on a parent `ArgumentParser(add_help=False)` passed via `parents=` to each subparser, so flags work after the subcommand name.

## Workflow

Stories are built sequentially from BACKLOG.md. After building, run a review pass (see `review.sh`) that audits against ENGINEERING_STANDARDS.md and fixes issues in place.
