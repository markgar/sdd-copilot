"""Subprocess wrapper around the ``copilot`` CLI.

This is the lowest-level execution layer — it knows how to construct
the ``copilot`` command line and call it via :func:`subprocess.run`.
Output streams directly to the terminal so the user can watch
Copilot work in real-time.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sdd_copilot.exceptions import RunnerError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CopilotResult:
    """Outcome of a single ``copilot`` CLI invocation."""

    exit_code: int
    output: str = ""  # captured stdout (empty when not capturing)
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "success", self.exit_code == 0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4.6"
_DEFAULT_TIMEOUT = 600  # seconds


def run_copilot(
    prompt: str,
    working_dir: Path,
    model: str = DEFAULT_MODEL,
    extra_dirs: tuple[Path, ...] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    capture: bool = False,
) -> CopilotResult:
    """Shell out to ``copilot`` CLI in non-interactive yolo mode.

    By default, output streams directly to the terminal in real-time
    so the user can watch what Copilot is doing.  When *capture* is
    ``True``, stdout is captured and returned in
    :attr:`CopilotResult.output` (stderr still passes through).

    Parameters
    ----------
    prompt:
        The full prompt string to pass via ``-p``.
    working_dir:
        The directory in which the ``copilot`` process runs (``cwd``).
    model:
        The LLM model name (passed via ``--model``).
    extra_dirs:
        Additional directories to expose to Copilot via ``--add-dir``.
    timeout:
        Maximum wall-clock seconds before the process is killed.
    capture:
        When ``True``, capture stdout so the response text is available
        in :attr:`CopilotResult.output`.  Defaults to ``False``.

    Raises
    ------
    RunnerError
        If the ``copilot`` binary is not found on ``$PATH`` or the
        process times out.
    """
    copilot_bin = shutil.which("copilot")
    if copilot_bin is None:
        raise RunnerError(
            working_dir,
            "'copilot' executable not found on $PATH",
        )

    cmd: list[str] = [
        copilot_bin,
        "-p", prompt,
        "--yolo",
        "--autopilot",
        "--no-ask-user",
        "--model", model,
        "-s",
    ]

    if extra_dirs:
        for d in extra_dirs:
            cmd.extend(["--add-dir", str(d)])

    logger.info(
        "Running copilot (model=%s, cwd=%s, timeout=%ds)",
        model,
        working_dir,
        timeout,
    )
    logger.debug("Command: %s", cmd)

    try:
        if capture:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                timeout=timeout,
                stdout=subprocess.PIPE,
                text=True,
            )
        else:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(
            working_dir,
            f"copilot process timed out after {timeout}s",
        ) from exc
    except OSError as exc:
        raise RunnerError(working_dir, str(exc)) from exc

    output = result.stdout if capture else ""
    outcome = CopilotResult(exit_code=result.returncode, output=output)
    logger.info(
        "Copilot exited with code %d (%s)",
        outcome.exit_code,
        "success" if outcome.success else "failure",
    )
    return outcome
