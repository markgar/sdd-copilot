#!/bin/zsh
# review.sh — Senior SWE code review, fix, and capture learnings

cd "$(dirname "$0")" || exit 1

copilot -p "Look at the codebase and act like a Senior SWE. You don't let anything go. You know SOLID, DIP, and all the best practices for architecture and software engineering. Focus primarily on recently changed code, but flag systemic issues if you spot them. Review the code and fix it to be the way it really should be. When you're done, generalize what you learned into ENGINEERING_STANDARDS.md so the builder can reference it on future builds. Only add generic findings, not one-off bug fixes. If the file already exists, update it. Merge duplicates. Also, if your review changes architecture, key conventions, or workflow, update .github/copilot-instructions.md to match — keep that file minimal (project identity, architecture rules, code conventions, workflow only). Finally, ensure the project has minimal but current documentation: a README.md (what it does, how to install, how to use), and if a CHANGELOG.md exists keep it up to date. Don't over-document — just enough for a new contributor to get oriented. Git commit your changes when done." --yolo
