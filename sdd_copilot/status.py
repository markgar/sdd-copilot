"""Read/write spec status from ``.sdd-status.json``.

This module is the persistence layer for spec lifecycle state.  It knows
how to read/write a JSON file and validate values — nothing more.  Query
logic (e.g. "find the next actionable spec") lives on :class:`SpecSet`
where it belongs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sdd_copilot.exceptions import InvalidStatusError, StatusFileError
from sdd_copilot.models import SpecStatus

logger = logging.getLogger(__name__)

_STATUS_FILE = ".sdd-status.json"


def _status_path(spec_dir: Path) -> Path:
    """Return the path to the status JSON file."""
    return spec_dir / _STATUS_FILE


def _read_status_file(spec_dir: Path) -> dict[str, str]:
    """Load the raw status dict from disk (string keys).

    Returns an empty dict if the file does not exist.
    Raises :class:`StatusFileError` on I/O or parse failures.
    """
    path = _status_path(spec_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatusFileError(path, str(exc)) from exc

    if not isinstance(data, dict):
        raise StatusFileError(path, f"Expected a JSON object, got {type(data).__name__}")
    return data


def _write_status_file(spec_dir: Path, data: dict[str, str]) -> None:
    """Persist the status dict to disk."""
    path = _status_path(spec_dir)
    try:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise StatusFileError(path, str(exc)) from exc


def _validate_status(value: str) -> SpecStatus:
    """Coerce *value* to a :class:`SpecStatus` or raise."""
    try:
        return SpecStatus(value)
    except ValueError:
        raise InvalidStatusError(value, [s.value for s in SpecStatus]) from None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_status(spec_dir: Path, spec_number: int) -> SpecStatus:
    """Return the status of a single spec, defaulting to ``PENDING``."""
    data = _read_status_file(spec_dir)
    raw = data.get(str(spec_number), SpecStatus.PENDING.value)
    return _validate_status(raw)


def set_status(spec_dir: Path, spec_number: int, status: SpecStatus) -> None:
    """Update (or create) the status for a spec and write to disk.

    *status* must be a :class:`SpecStatus` member.
    """
    data = _read_status_file(spec_dir)
    data[str(spec_number)] = status.value
    _write_status_file(spec_dir, data)
    logger.debug("Spec %02d status → %s", spec_number, status.value)


def load_all_statuses(spec_dir: Path) -> dict[int, SpecStatus]:
    """Return the full status map with integer keys and validated values."""
    data = _read_status_file(spec_dir)
    return {int(k): _validate_status(v) for k, v in data.items()}
