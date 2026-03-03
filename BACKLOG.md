# SDD Copilot — Build Backlog

Stories are ordered for sequential implementation. Reference PLAN.md for full details.

---

- [x] **1. Project scaffold** — Set up `pyproject.toml` with `sdd` console entry point, create the `sdd_copilot/` package with `__init__.py`, and verify `sdd --help` runs.
- [x] **2. Models** — Implement all dataclasses in `models.py`: `Spec`, `Constitution`, `BuildPlan`, `Task`, `TaskList`, `SpecSet`.
- [x] **3. Status tracking** — Implement `status.py` — read/write `.sdd-status.json`: `get_status`, `set_status`, `load_all_statuses`, `next_actionable_spec`.
- [x] **4. Spec loader** — Implement `spec_loader.py` — `load_spec_set()`: discover numbered specs, parse sections by headings, extract dependencies, read constitution, read research docs, read README build order, load statuses.
- [x] **5. Prompt builder** — Implement `prompt_builder.py` — `build_planning_prompt()` and `build_task_prompt()` that assemble the XML-structured prompts with constitution, spec, research, and dependency context.
- [x] **6. Runner** — Implement `runner.py` — `run_copilot()`: define the `CopilotResult` dataclass, construct the `copilot` CLI command, execute via `subprocess.run()` with live terminal output (no capture), return `CopilotResult`.
- [x] **7. Planner** — Implement `planner.py` — `plan_next()`: pick next pending spec, build planning prompt, shell out to copilot, parse the markdown response into a `TaskList`, write `tasks/tasks-NN.md`, update status to `planned`.
- [x] **8. Builder** — Implement `builder.py` — `build_next()`: pick next planned spec, read task file, loop through tasks (one copilot session per task with live output), run validation command, update status to `done` or leave as `building`.
- [x] **9. CLI** — Implement `cli.py` with argparse — `sdd plan`, `sdd build`, `sdd status`, `sdd run` commands with `--spec-dir`, `--spec`, `--model`, `--project-dir` options.
- [ ] **10. End-to-end verification** — Test the full flow against a real spec set: `sdd status`, `sdd plan --spec 1`, `sdd build --spec 1`, `sdd run`.
