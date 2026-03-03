# SDD Copilot

CLI tool that orchestrates **Spec-Driven Development** by shelling out to the [GitHub Copilot CLI](https://docs.github.com/en/copilot). Give it a directory of numbered specs and a constitution document, and it will plan each spec into granular tasks, then build them one at a time — each in a fresh Copilot session with full context.

## How It Works

```
sdd plan   →  Decomposes the next pending spec into ordered tasks
sdd build  →  Executes each task via a separate Copilot CLI session
sdd status →  Shows progress across all specs
sdd run    →  Plan + build in sequence until all specs are done
```

Each Copilot session gets: the project constitution, the spec context, referenced research docs, and completed dependency summaries — assembled into a structured prompt automatically.

## Requirements

- Python 3.11+
- [GitHub Copilot CLI](https://docs.github.com/en/copilot) (`copilot` on `$PATH`)

## Install

```bash
pip install -e .
```

## Usage

```bash
# Point at your spec directory
sdd status --spec-dir ./specs

# Plan a specific spec into tasks
sdd plan --spec-dir ./specs --spec 1

# Build a planned spec (each task → one copilot session)
sdd build --spec-dir ./specs --spec 1 --project-dir ./my-project

# Run the full pipeline
sdd run --spec-dir ./specs --project-dir ./my-project

# Use a different model
sdd plan --spec-dir ./specs --model gpt-4o
```

### Spec Directory Structure

```
specs/
├── CONSTITUTION.md          # Project principles (included in every prompt)
├── README.md                # Build order (spec numbers extracted from here)
├── 01-foundation.md         # Numbered specs: NN-slug.md
├── 02-connections.md
├── research/                # Optional research docs referenced by specs
│   └── api-notes.md
└── .sdd-status.json         # Auto-managed progress file
```

## Project Structure

```
sdd_copilot/
├── cli.py              # argparse entrypoint
├── models.py           # Domain types: Spec, SpecSet, Task, BuildPlan, etc.
├── exceptions.py       # SddError hierarchy
├── spec_loader.py      # Parse spec directory into SpecSet
├── planner.py          # Planning loop: spec → tasks via copilot
├── builder.py          # Build loop: tasks → copilot sessions → validation
├── prompt_builder.py   # Assemble XML-structured prompts
├── runner.py           # Subprocess wrapper around copilot CLI
└── status.py           # Read/write .sdd-status.json
```

## Development

```bash
# Build the next backlog story
./build.sh

# Run code review + standards audit
./review.sh

# Run tests
./test.sh

# All three in sequence
./dev-loop.sh
```

See [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md) for coding conventions and [PLAN.md](PLAN.md) for full architecture details.
