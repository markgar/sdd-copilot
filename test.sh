#!/bin/zsh
# test.sh — Build and run tests across the codebase

cd "$(dirname "$0")" || exit 1

copilot -p "You are a senior test engineer. Look at the codebase, detect the language and test framework in use (or choose the standard one for the language), and write thorough tests for every module that has real implementation — skip stubs and empty files. Reference ENGINEERING_STANDARDS.md (if it exists) — tests should follow the same conventions as production code. For each module, test the happy path, edge cases, and error handling. If a test directory doesn't exist, create one. If tests already exist, review them for coverage gaps and add what's missing. Then run the full test suite and fix any failures until all tests pass. Keep tests focused, fast, and independent — no shared mutable state between tests. Mock external I/O (subprocess calls, disk reads, network) so tests are deterministic. Git commit your changes when done." --yolo
