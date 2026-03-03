# SDD Copilot CLI — Build Plan

A Python CLI tool that orchestrates Spec-Driven Development by running two loops — **Plan** and **Build** — each shelling out to `copilot -p "..." --yolo` with carefully constructed prompts and context.

The tool reads a spec set (constitution, numbered specs, research, README), tracks progress via a local `.sdd-status.json` file, generates ephemeral task files in `tasks/`, and drives implementation one spec at a time — plan it into tasks, build each task sequentially, then advance to the next spec.

---

## Architecture

```
sdd plan              sdd build
    │                     │
    ▼                     ▼
┌──────────┐        ┌──────────┐
│ Planner  │        │ Builder  │
│ Loop     │        │ Loop     │
└────┬─────┘        └────┬─────┘
     │                    │
     ▼                    ▼
┌──────────────────────────────┐
│       Prompt Builder         │
│  (constitution + spec +      │
│   research + dep summaries)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          Runner              │
│  copilot -p "..." --yolo     │
│  --autopilot --no-ask-user   │
│  -s --model <model>          │
└──────────────────────────────┘
```

---

## Two Loops

### Planning Phase (`sdd plan`)

Runs once per spec — one Copilot session — then exits.

1. Take the next `pending` spec in numerical order (or user-specified spec number)
2. Load: constitution + spec content + referenced research docs + completed dependency specs' summaries
3. Construct a planning prompt: "Decompose the '## What to Build' section into ordered, granular implementation tasks"
4. Shell out: `copilot -p "{prompt}" --yolo --autopilot --no-ask-user -s`
5. Parse response → write `tasks/tasks-NN.md`
6. Mark spec status as `planned`
7. **Done. Planner exits.**

### Build Phase (`sdd build`)

Loops through the tasks that the planner produced. Each task gets its own Copilot CLI execution, giving it a completely fresh context window every time.

1. Take the next `planned` spec in numerical order (or user-specified spec number)
2. Read `tasks/tasks-NN.md`, parse into task list
3. Mark spec status as `building`
4. For each task in order:
   a. Construct a build prompt with: constitution + spec context + task description + acceptance criteria
   b. Shell out: `copilot -p "{prompt}" --yolo --autopilot --no-ask-user -s` — **fresh session, fresh context**
   c. Mark task as completed in progress tracking
   d. Log result
5. After all tasks: run the spec's `## Validation Command`
6. If validation passes → mark spec status as `done`
7. If validation fails → leave status as `building`, log failure

### Full Cycle

Specs are numbered to reflect their natural dependency order. Processing is strictly sequential: finish spec 01 completely (plan → build all tasks → validate) before moving to spec 02, and so on.

---

## Project Structure

```
/Users/markgarner/dev/sdd-copilot/
├── pyproject.toml
└── sdd_copilot/
    ├── __init__.py
    ├── cli.py              # argparse entrypoint: plan, build, status, run
    ├── models.py           # dataclasses: SpecSet, Spec, Constitution, BuildPlan, Task, TaskList
    ├── spec_loader.py      # parse spec directory: constitution, README, numbered specs, research
    ├── planner.py          # planning loop: pick spec → prompt → copilot → tasks.md
    ├── builder.py          # build loop: read tasks → prompt per task → copilot → validate
    ├── prompt_builder.py   # assemble context bundles into structured prompts
    ├── runner.py           # subprocess wrapper around copilot CLI
    ├── status.py           # read/write spec status from .sdd-status.json
```

---

## Module Details

### 1. Models (`models.py`)

All data flows through typed dataclasses:

```python
@dataclass
class Spec:
    number: int                    # 01, 02, ...
    slug: str                      # "foundation", "connection-managers"
    title: str                     # "Foundation & Data Model"
    path: Path                     # absolute path to the spec .md file
    sections: dict[str, str]       # heading → content: "Summary", "What to Build", etc.
    dependencies: list[int]        # [1, 2] = depends on Spec 01 and 02
    status: str                    # "pending" | "planned" | "building" | "done"

@dataclass
class Constitution:
    path: Path
    content: str                   # full raw text

@dataclass
class BuildPlan:
    order: list[int]                        # specs in numerical order

@dataclass
class Task:
    number: int                    # 1, 2, 3, ...
    title: str
    description: str
    acceptance_criteria: str       # relevant GIVEN/WHEN/THEN

@dataclass
class TaskList:
    spec_number: int
    tasks: list[Task]
    path: Path                     # tasks/tasks-NN.md

@dataclass
class SpecSet:
    specs: dict[int, Spec]         # number → Spec
    constitution: Constitution
    build_plan: BuildPlan          # ordered list of spec numbers
    research_docs: dict[str, str]  # filename → content
    spec_dir: Path
```

### 2. Spec Loader (`spec_loader.py`)

`load_spec_set(spec_dir: Path) -> SpecSet`

- **Discovers numbered specs**: glob `[0-9][0-9]-*.md`, parse number and slug from filename
- **Parses each spec by headings**: splits on `## ` to extract sections map
- **Extracts dependencies**: regex `\*\*Spec (\d+)\*\*` from the `## Dependencies` section
- **Reads constitution**: `CONSTITUTION.md` as raw text
- **Parses README build plan**: extracts the spec list in numerical order
- **Reads research docs**: glob `research/*.md`, store as `{filename: content}`
- **Reads statuses**: from `.sdd-status.json` in the spec directory

### 3. Status Tracking (`status.py`)

Uses a single JSON file (`.sdd-status.json`) in the spec directory to track progress. Spec files are **never modified** by this tool.

```json
{
  "1": "done",
  "2": "planned",
  "3": "pending"
}
```

Functions:
- `get_status(spec_dir: Path, spec_number: int) -> str` — reads status from `.sdd-status.json`, defaults to `"pending"` if absent
- `set_status(spec_dir: Path, spec_number: int, status: str) -> None` — updates `.sdd-status.json` (creates if missing)
- `load_all_statuses(spec_dir: Path) -> dict[int, str]` — returns the full status map
- `next_actionable_spec(spec_set: SpecSet, target_status: str) -> Spec | None` — walks specs in numerical order, returns the first one whose status matches `target_status`

Status flow per spec:
```
pending → planned → building → done
```

### 4. Prompt Builder (`prompt_builder.py`)

#### Planning Prompt

`build_planning_prompt(spec: Spec, spec_set: SpecSet) -> str`

Assembles:
```
<system>
You are an SDD planning agent. Your job is to decompose a specification
into ordered, granular implementation tasks.
</system>

<constitution>
{full constitution text}
</constitution>

<spec>
{full spec text}
</spec>

<research>
{content of each research doc referenced in ## Reference}
</research>

<completed_dependencies>
{for each dependency spec: ## Summary + ## Acceptance Criteria}
</completed_dependencies>

<instructions>
Decompose the "## What to Build" section into ordered, granular
implementation tasks. Each task should be a single coherent unit of
work that one coding session can complete.

Output format — use EXACTLY this markdown structure:

## Task 1: [short title]
### Description
[What to implement — specific functions, data structures, logic]
### Acceptance Criteria
[Relevant GIVEN/WHEN/THEN from the spec, or new micro-criteria]

## Task 2: [short title]
...
</instructions>
```

#### Build Prompt

`build_task_prompt(task: Task, spec: Spec, spec_set: SpecSet) -> str`

Assembles:
```
<system>
You are an SDD build agent. Implement exactly one task from
a specification. Follow the constitution's principles strictly.
</system>

<constitution>
{full constitution text}
</constitution>

<spec_context>
# Spec {NN}: {title}
## Summary
{summary section}
## Dependencies
{dependencies section}
</spec_context>

<task>
## Task {N}: {title}
### Description
{description}
### Acceptance Criteria
{acceptance criteria}
</task>

<instructions>
Implement this task. Follow the constitution's principles.
When done, verify your work against the acceptance criteria.
</instructions>
```

### 5. Runner (`runner.py`)

`run_copilot(prompt: str, working_dir: Path, model: str, extra_dirs: list[Path]) -> CopilotResult`

```python
@dataclass
class CopilotResult:
    exit_code: int
    success: bool

def run_copilot(
    prompt: str,
    working_dir: Path,
    model: str = "claude-sonnet-4.6",
    extra_dirs: list[Path] | None = None,
    timeout: int = 600,
) -> CopilotResult:
    """Shell out to copilot CLI in non-interactive yolo mode.
    
    Output streams directly to the terminal in real-time
    so the user can watch what copilot is doing.
    """
```

Constructs command:
```bash
copilot \
  -p "{prompt}" \
  --yolo \
  --autopilot \
  --no-ask-user \
  --model {model} \
  --add-dir {spec_dir} \
  --add-dir {project_dir} \
  -s
```

Uses `subprocess.run()` with **no `capture_output`** — stdout and stderr pass through directly to the terminal. The user sees copilot's output live as it works. Only the exit code is captured to determine success/failure.

### 6. Planner (`planner.py`)

```python
def plan_next(
    spec_set: SpecSet,
    spec_number: int | None = None,
    model: str = "claude-sonnet-4.6",
) -> TaskList:
    """Plan the next (or specified) spec into tasks."""
```

Flow:
1. If no `spec_number`, call `next_actionable_spec(spec_set, "pending")`
2. Build planning prompt via `prompt_builder.build_planning_prompt()`
3. Shell out via `runner.run_copilot()`
4. Parse copilot's markdown response into `list[Task]`
5. Write `tasks/tasks-{NN:02d}.md` in the spec directory
6. Call `set_status(spec_set.spec_dir, spec.number, "planned")`
7. Return the `TaskList`

### 7. Builder (`builder.py`)

```python
def build_next(
    spec_set: SpecSet,
    spec_number: int | None = None,
    model: str = "claude-sonnet-4.6",
    project_dir: Path | None = None,
) -> bool:
    """Build the next (or specified) planned spec, task by task."""
```

Flow:
1. If no `spec_number`, call `next_actionable_spec(spec_set, "planned")`
2. Read `tasks/tasks-{NN:02d}.md`, parse into `TaskList`
3. Call `set_status(spec_set.spec_dir, spec.number, "building")`
4. For each task:
   a. Print progress: `[Task {i}/{total}] {title}`
   b. Build task prompt via `prompt_builder.build_task_prompt()`
   c. Shell out via `runner.run_copilot(working_dir=project_dir)`
   d. Log success/failure
5. Run the spec's `## Validation Command` via `subprocess.run()`
6. If validation passes → `set_status(spec_set.spec_dir, spec.number, "done")`, return `True`
7. If validation fails → leave status as `"building"`, return `False`

### 8. CLI (`cli.py`)

```
Usage: sdd <command> [options]

Commands:
  plan     Plan the next spec into tasks
  build    Build the next planned spec, task by task
  status   Show status of all specs
  run      Plan + build in sequence, advancing through specs

Options:
  --spec-dir PATH    Path to the specs directory (default: cwd)
  --spec N           Target a specific spec number
  --model MODEL      Copilot model (default: claude-sonnet-4.6)
  --project-dir PATH Working directory for copilot build sessions
```

#### `sdd status`

Prints a table:
```
Spec  Title                              Status    Deps
────  ─────                              ──────    ────
  01  Foundation & Data Model            done      —
  02  Connection Managers                planned   01
  03  Data Flow Core                     pending   01, 02
  ...
```

#### `sdd run`

Processes specs sequentially in numerical order: plan spec 01 → build all its tasks → validate → move to spec 02 → repeat until all specs are done (or one fails validation).

---

## Task File Format

Written to `{spec_dir}/tasks/tasks-NN.md`, overwritten on re-plan:

```markdown
# Tasks: Spec 01 — Foundation & Data Model

## Task 1: Imports, constants, and format detection
### Description
Create the file `ssis_doc.py` with all imports, the `NS` namespace dict,
and `_detect_format_version()` function that reads PackageFormatVersion
from attribute (fmt8) or child element (fmt2/6), defaulting to 2.
### Acceptance Criteria
- **GIVEN** a format 8 .dtsx root element
  **WHEN** `_detect_format_version()` is called
  **THEN** it returns `8`

## Task 2: Property accessor and decode helpers
### Description
Implement `_get_prop()` for format-agnostic property access and
`_decode_escapes()` for `_xHHHH_` patterns.
### Acceptance Criteria
- **GIVEN** the string `_x000D__x000A_`
  **WHEN** `_decode_escapes()` executes
  **THEN** the return value is `\r\n`

...
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Generic, not SSIS-specific | Yes | Works with any spec set following the spec kit structure |
| Agent CLI | `copilot -p "..." --yolo` | User's installed tool, autonomous non-interactive sessions |
| Status persistence | `.sdd-status.json` in spec dir | Single file, easy to reset; spec files are never modified; travels with specs in git |
| Task files | `tasks/` dir, overwritten on re-run | Ephemeral — spec-diffing for incremental re-planning deferred |
| Prompt assembly | Full context per session | Sessions are stateless; each gets constitution + spec + research + deps |
| Live terminal output | Yes | Copilot stdout/stderr stream directly to the terminal — user watches it work in real-time |
| Model default | `claude-sonnet-4.6` | Fast + capable; user can override with `--model` |

---

## Verification

```bash
# Check it loads the SSIS spec set
sdd status --spec-dir /Users/markgarner/dev/ssis/specs

# Plan spec 01 into tasks
sdd plan --spec-dir /Users/markgarner/dev/ssis/specs --spec 1

# Build spec 01 (each task → one copilot session)
sdd build --spec-dir /Users/markgarner/dev/ssis/specs --spec 1 \
    --project-dir /Users/markgarner/dev/ssis

# Run full pipeline through dependency graph
sdd run --spec-dir /Users/markgarner/dev/ssis/specs \
    --project-dir /Users/markgarner/dev/ssis
```
