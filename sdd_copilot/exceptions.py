"""Custom exceptions for SDD Copilot.

All exceptions inherit from ``SddError`` so callers can catch broadly
or narrowly as needed.
"""

from __future__ import annotations

from pathlib import Path


class SddError(Exception):
    """Base exception for all SDD Copilot errors."""


class SpecLoadError(SddError):
    """Raised when a spec file cannot be read or parsed."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load spec '{path}': {reason}")


class StatusFileError(SddError):
    """Raised when the status JSON file is corrupt or unreadable."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Status file error '{path}': {reason}")


class InvalidStatusError(SddError):
    """Raised when an invalid status value is encountered."""

    def __init__(self, value: str, valid: list[str]) -> None:
        self.value = value
        self.valid = valid
        super().__init__(
            f"Invalid status '{value}'. Must be one of: {', '.join(valid)}"
        )


class SpecNotFoundError(SddError):
    """Raised when a requested spec number does not exist."""

    def __init__(self, spec_number: int) -> None:
        self.spec_number = spec_number
        super().__init__(f"Spec {spec_number:02d} not found")


class ConstitutionMissingError(SddError):
    """Raised when CONSTITUTION.md is missing from the spec directory."""

    def __init__(self, spec_dir: Path) -> None:
        self.spec_dir = spec_dir
        super().__init__(f"CONSTITUTION.md not found in '{spec_dir}'")


class RunnerError(SddError):
    """Raised when the copilot subprocess fails to launch or times out."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Runner error in '{path}': {reason}")


class PlannerError(SddError):
    """Raised when the planning phase fails."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Planner error in '{path}': {reason}")
