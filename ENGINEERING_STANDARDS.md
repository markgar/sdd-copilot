# Engineering Standards

Principles and patterns to follow on every build. These are not aspirational — they are the minimum bar.

---

## 1. Enums over magic strings

When a value has a fixed set of valid options (statuses, modes, types), define an enum. Never scatter string literals across modules.

```python
# Wrong
status: str = "pending"  # "pending" | "planned" | "building" | "done"

# Right
class SpecStatus(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    BUILDING = "building"
    DONE = "done"
```

**Why:** A typo in a string is a silent bug. A typo in an enum is an immediate `AttributeError`. The enum is also the single source of truth for what values exist — no hunting across files.

---

## 2. Validate at construction — every dataclass, no exceptions

Dataclasses and model objects must reject invalid state in `__post_init__`. If an object can be constructed in a broken state, every consumer has to defend against it. This applies to **every** dataclass — including container types like `TaskList` and `SpecSet`, not just leaf objects like `Task`.

```python
@dataclass(frozen=True)
class TaskList:
    spec_number: int
    tasks: tuple[Task, ...]
    path: Path

    def __post_init__(self) -> None:
        if self.spec_number < 0:
            raise ValueError(f"TaskList spec_number must be >= 0, got {self.spec_number}")
        if not isinstance(self.tasks, tuple):
            object.__setattr__(self, "tasks", tuple(self.tasks))
        if not self.tasks:
            raise ValueError("TaskList must contain at least one task")
```

**Why:** Fail fast, fail loud, fail at the source. Debugging a bad value three call-stacks away from where it was created is exponentially harder. Skipping validation on "obvious" containers is how empty collections propagate silently through the system.

---

## 3. Value objects should be immutable — including fields on mutable parents

If an object represents a value (not an entity you mutate over time), make it `frozen=True` and use tuples instead of lists for collections. Even on mutable dataclasses, fields that don't change after construction should use immutable types.

```python
@dataclass(frozen=True)
class BuildPlan:
    order: tuple[int, ...]  # not list[int]

@dataclass  # mutable — status changes during lifecycle
class Spec:
    dependencies: tuple[int, ...]  # but dependencies never change after load
    status: SpecStatus = SpecStatus.PENDING
```

**Why:** Immutable objects are safe to share, cache, and reason about. If something shouldn't change after creation, enforce it structurally — don't rely on discipline. Using `tuple` for a `list`-typed field on a non-frozen dataclass makes the immutability intent explicit.

---

## 4. Dependencies point inward

The dependency graph has three tiers:

```
Tier 0 (core):     exceptions.py
Tier 1 (domain):   models.py → depends on exceptions.py
Tier 2 (services): status.py, runner.py, prompt_builder.py → depend on models.py, exceptions.py
Tier 3 (orchestr): spec_loader.py, planner.py, builder.py → depend on tiers 0–2
Tier 4 (entry):    cli.py → depends on everything
```

The rule: **a module may only import from its own tier or below**. Low-level I/O modules (tier 2) never import orchestration modules (tier 3+). `models.py` is the centre — everything depends on it, not the reverse.

```
✗  status.py imports spec_loader (tier 2 → tier 3)
✗  runner.py imports models.SpecSet (tier 2 needs only simple types)
✓  status.py imports models.SpecStatus (tier 2 → tier 1)
✓  spec_loader.py imports status.load_all_statuses (tier 3 → tier 2)
```

**Why:** This is the Dependency Inversion Principle. When low-level code depends on high-level code, changes ripple in both directions and you can't test or reuse either layer independently.

---

## 5. Read once, pass the result

If a function reads from disk (or network, or any I/O), and you're calling it in a loop, you're doing N reads when you need one. Read once outside the loop, pass the data in.

```python
# Wrong — reads .sdd-status.json once per spec
for spec_number in spec_numbers:
    status = get_status(spec_dir, spec_number)  # disk read each time

# Right — single read, dict lookup in loop
all_statuses = load_all_statuses(spec_dir)
for spec_number in spec_numbers:
    status = all_statuses.get(spec_number, SpecStatus.PENDING)
```

**Why:** I/O is orders of magnitude slower than memory access. More importantly, repeated reads introduce race conditions — the file could change between reads.

---

## 6. Custom exceptions with context

Raw `OSError` and `JSONDecodeError` tell you what went wrong technically but not what the user was trying to do. Wrap them in domain exceptions that carry both.

```python
class StatusFileError(SddError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Status file error '{path}': {reason}")
```

**Why:** When something fails in production (or in a user's terminal), the error message is often the only diagnostic you get. `"Status file error '/foo/.sdd-status.json': Expecting property name"` beats `"Expecting property name: line 3 column 1"`.

Hierarchy tip: Give all your exceptions a common base class (`SddError`) so callers can catch broadly or narrowly.

---

## 7. Use `removeprefix` / `removesuffix`, not `lstrip` / `rstrip`

`lstrip("# ")` does **not** strip the string `"# "`. It strips any characters in the **set** `{'#', ' '}` from the left. This silently mangles input.

```python
# Wrong — strips the character set {'#', ' '}
"## Spaces matter".lstrip("# ")  # → "paces matter"

# Right — strips the exact prefix
"## Spaces matter".removeprefix("## ")  # → "Spaces matter"
```

**Why:** This is Python's most common string-handling trap. If you're removing a known prefix, `removeprefix` is always correct. `lstrip` is for removing a *class of characters* (like whitespace).

---

## 8. CLI shared options go on a parent parser

If multiple subcommands share the same flags (`--verbose`, `--config`, etc.), define them on a parent parser and pass it via `parents=[shared]`. Don't put them on the root parser.

```python
# Wrong — sdd plan --spec-dir ./foo fails; only sdd --spec-dir ./foo plan works
parser.add_argument("--spec-dir", ...)
subparsers = parser.add_subparsers(...)

# Right — args work after the subcommand name
shared = argparse.ArgumentParser(add_help=False)
shared.add_argument("--spec-dir", ...)
subparsers.add_parser("plan", parents=[shared])
```

**Why:** Users expect `command subcommand --flag`, not `command --flag subcommand`. The parent-parser pattern gives you both for free.

---

## 9. Repr should be useful, not exhaustive

The default `__repr__` dumps every field. For objects with large content (raw text, dicts of document bodies), this makes logs and debugger output unreadable.

```python
@dataclass
class Spec:
    sections: dict[str, str] = field(repr=False)  # suppress in repr

    def __repr__(self) -> str:
        return f"Spec(number={self.number}, slug={self.slug!r}, status={self.status.value!r})"
```

**Why:** You'll read `repr()` output 100x more often than you write it. Optimize for the reader.

---

## 10. Log at module level, configure at entry point

Every module gets its own logger. Configuration (level, format) happens once in `main()`.

```python
# In each module
import logging
logger = logging.getLogger(__name__)

logger.info("Loading spec set from %s", spec_dir)
logger.debug("  Loaded spec %02d: %s", number, slug)

# In CLI entry point only
logging.basicConfig(format="%(levelname)-8s %(name)s: %(message)s", level=level)
```

**Why:** Module-level loggers follow the package hierarchy, so you can silence or amplify specific subsystems. Configuring at the entry point means libraries never fight over log settings.

---

## 11. Type your function signatures honestly — no defensive coercion behind the caller's back

If a function accepts `SpecStatus`, demand `SpecStatus`. Don't accept `str` silently with an `isinstance` check and `# type: ignore`. If callers need to convert, they should do it explicitly before calling.

```python
# Wrong — lies about its type, accepts str silently
def set_status(spec_dir: Path, spec_number: int, status: SpecStatus) -> None:
    if not isinstance(status, SpecStatus):
        status = _validate_status(status)  # type: ignore[arg-type]

# Right — trusts the type system, fails if caller is wrong
def set_status(spec_dir: Path, spec_number: int, status: SpecStatus) -> None:
    data[str(spec_number)] = status.value  # AttributeError if not SpecStatus
```

**Why:** Types are a contract. If the signature says `SpecStatus`, callers should pass `SpecStatus`. Defensive coercion masks bugs at the call site — the caller thinks they can pass a `str` and never finds out they were wrong until the coercion changes.

---

## 12. Coerce types in `__post_init__`

When a frozen dataclass field is typed as `tuple[int, ...]` but callers might pass a `list`, coerce it in `__post_init__`. Python dataclasses do not enforce type annotations at runtime — a `list` will silently sit where a `tuple` was promised, breaking immutability guarantees.

```python
@dataclass(frozen=True)
class BuildPlan:
    order: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.order, tuple):
            object.__setattr__(self, "order", tuple(self.order))
```

**Why:** Type hints are documentation, not enforcement. If you promise `tuple` but accept `list`, downstream code that relies on immutability (hashing, caching, identity checks) will break silently. `object.__setattr__` is the sanctioned escape hatch for frozen dataclass `__post_init__`.

Note: Coerce in `__post_init__` for *container type mismatches* (list → tuple). Do **not** coerce in regular function bodies — that's a type lie (see §11).

---

## 13. Imports go at the top — no lazy imports without circular deps

If module A imports from module B, and module B does **not** import from module A, the import belongs at the top of the file. Lazy imports inside functions are only justified when there is a real circular dependency.

```python
# Wrong — lazy import without circular dependency
def get_spec(self, spec_number: int) -> Spec:
    try:
        return self.specs[spec_number]
    except KeyError:
        from mypackage.exceptions import SpecNotFoundError  # unnecessary
        raise SpecNotFoundError(spec_number) from None

# Right — top-level import
from mypackage.exceptions import SpecNotFoundError

def get_spec(self, spec_number: int) -> Spec:
    try:
        return self.specs[spec_number]
    except KeyError:
        raise SpecNotFoundError(spec_number) from None
```

**Why:** Lazy imports hide dependencies from readers and tools (linters, import sorters, IDE navigation). They also add per-call overhead. Save the technique for genuine circular-import situations — and when you do use it, add a comment explaining *why*.

---

## 14. Use `Callable` from `collections.abc`, not `callable`

The builtin `callable` is a function that checks whether an object is callable — it is **not** a type annotation. For type hints, use `collections.abc.Callable` (or `typing.Callable`).

```python
# Wrong — callable is the builtin function, not a type
_DISPATCH: dict[str, callable] = { ... }

# Right — proper type from collections.abc
from collections.abc import Callable
_DISPATCH: dict[str, Callable[[argparse.Namespace], None]] = { ... }
```

**Why:** `callable` as a type hint silently passes — it's a valid expression — but provides zero useful type information. `Callable[[args], return]` tells both the reader and the type checker exactly what signature is expected.

---

## 15. No f-strings without interpolation

If a string has no `{…}` expressions, drop the `f` prefix. Gratuitous f-strings signal to the reader that dynamic content is present when it isn't.

```python
# Wrong — misleading f-prefix
print(f"Command 'plan' is not yet implemented.")

# Right
print("Command 'plan' is not yet implemented.")
```

**Why:** Code is read far more often than it's written. Every `f"..."` triggers a micro-scan for `{expressions}`. When there are none, that scan was wasted attention.

---

## 16. Import ordering: stdlib → third-party → local

Follow PEP 8 import groups, separated by blank lines: standard library, third-party packages, then local/project imports. Within each group, sort alphabetically.

```python
# Standard library
import logging
import re
from pathlib import Path

# Third-party
import requests

# Local
from mypackage.models import Spec, SpecSet
from mypackage.status import load_all_statuses
```

**Why:** Consistent ordering makes imports scannable. Mixing groups forces the reader to mentally classify each import before they can find what they're looking for.

---

## 17. Silent fallbacks are hidden bugs — log or raise

When an expected resource is missing (e.g., a config file, a constitution document), don't silently return a default. At minimum log a warning. If the resource is required for correctness, raise.

```python
# Wrong — silent empty fallback
if not constitution_path.exists():
    constitution = Constitution(path=constitution_path, content="")

# Right — warn so the user knows prompts will be degraded
if not constitution_path.exists():
    logger.warning("CONSTITUTION.md not found in %s — prompts will lack project principles", spec_dir)
    constitution = Constitution(path=constitution_path, content="")
```

**Why:** Silent fallbacks mask misconfiguration. The user runs the tool, gets bad results, and has no clue that the constitution was never loaded. A warning in the log is the difference between debugging for 30 seconds and debugging for 30 minutes.

---

## 18. Define exceptions even before you need them — but wire them up

It's fine to define a `ConstitutionMissingError` before the code path that raises it exists. But when the code path *does* exist (loading a spec set), connect them. Dead exceptions are a signal that error handling was designed but not implemented.

**Why:** Exception hierarchies are API contracts. If you define `ConstitutionMissingError`, callers expect it. If you silently swallow the condition instead, the exception is misleading documentation.

---

## 19. DRY for configuration constants

When a default value (model name, timeout, file path pattern) is needed in multiple modules, define it as a **public constant** in the lowest-tier module that owns the concept, and import it elsewhere. Never duplicate the literal.

```python
# Wrong — same default in three files
# runner.py
_DEFAULT_MODEL = "claude-sonnet-4.6"
# planner.py
_DEFAULT_MODEL = "claude-sonnet-4.6"
# cli.py
default="claude-sonnet-4.6"

# Right — single source of truth in the owning module
# runner.py (tier 2 — owns copilot execution)
DEFAULT_MODEL = "claude-sonnet-4.6"

# planner.py (tier 3 — imports from tier 2)
from sdd_copilot.runner import DEFAULT_MODEL

# cli.py (tier 4 — imports from tier 2)
from sdd_copilot.runner import DEFAULT_MODEL
```

**Why:** If the value changes, you update one file. Duplicated literals drift silently — one file gets updated, the others don't, and you get inconsistent behaviour with no compiler error.

---

## 20. Chain exceptions explicitly with `from`

When catching an exception and re-raising as a domain exception, always capture the original with `as exc` and chain with `from exc`. Apply this consistently to **every** except clause — not just some.

```python
# Wrong — loses the causal chain on one branch
except subprocess.TimeoutExpired:
    raise RunnerError(working_dir, "timed out")
except OSError as exc:
    raise RunnerError(working_dir, str(exc)) from exc

# Right — both branches chain consistently
except subprocess.TimeoutExpired as exc:
    raise RunnerError(working_dir, "timed out") from exc
except OSError as exc:
    raise RunnerError(working_dir, str(exc)) from exc
```

**Why:** Python 3 sets `__context__` implicitly, but `__cause__` (set by `from`) signals *intentional* chaining and suppresses the "During handling of the above exception" noise. Inconsistent chaining means some error paths lose debugging context and some don't — that's the worst of both worlds.

---

## 21. Wrap construction errors in orchestration code

When orchestration code creates domain objects from external input (user input, API responses, file contents), catch `ValueError`/`TypeError` from construction and wrap in the orchestration-level exception. Otherwise raw validation errors escape to callers who can't tell whether the input was bad or the code has a bug.

```python
# Wrong — Task.__post_init__ ValueError escapes unwrapped
tasks = _parse_tasks(result.output)  # only catches _parse_tasks's own ValueError

# Right — catch all construction errors
try:
    tasks = _parse_tasks(result.output)
except ValueError as exc:
    raise PlannerError(spec.path, str(exc)) from exc
```

**Why:** Domain objects validate on construction (§2). Orchestration code feeds them external data. The `ValueError` from `Task(number=0, ...)` is meaningful to the planner but opaque to the CLI user. Wrapping it in `PlannerError` adds the context needed for diagnosis.

---

## Checklist

Before considering a module done:

- [ ] No magic strings — enums for fixed value sets
- [ ] Every dataclass validates on construction (including containers)
- [ ] Value objects are frozen / immutable; immutable fields on mutable objects use `tuple`
- [ ] Types are coerced in `__post_init__` where callers may pass the wrong container
- [ ] Dependencies point inward — check the tier diagram in §4
- [ ] I/O happens once, results are passed
- [ ] Errors carry domain context
- [ ] No silent fallbacks — missing resources are warned or raised
- [ ] No `lstrip`/`rstrip` where `removeprefix`/`removesuffix` is meant
- [ ] CLI args work after the subcommand
- [ ] Repr is readable, not exhaustive
- [ ] Logging is present and configured at the entry point
- [ ] Function signatures use real types — no `str` stand-ins, no `# type: ignore` coercion
- [ ] No lazy imports unless circular dependency exists
- [ ] `Callable` from `collections.abc`, not builtin `callable`
- [ ] No f-strings without interpolation
- [ ] Imports follow stdlib → third-party → local ordering
- [ ] Configuration constants defined once, imported elsewhere — no duplicated literals
- [ ] All `except` clauses that re-raise use `from exc` consistently
- [ ] Orchestration code wraps construction `ValueError`s in domain exceptions
