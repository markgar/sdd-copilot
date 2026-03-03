#!/bin/zsh
# build.sh — Pick up the next backlog story and build it

cd "$(dirname "$0")" || exit 1

copilot -p "Go to the backlog, get the next story, and build it. Reference ENGINEERING_STANDARDS.md (if it exists) for guidance. Aim for: fail-fast validation, no magic strings, immutability by default, inward-pointing dependencies, honest type signatures, and no silent fallbacks. Don't break existing functionality — run any existing tests before and after your changes. When you're done, mark the story as complete and git commit your work." --yolo
