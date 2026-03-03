"""Tests for sdd_copilot.status — status file I/O and validation."""

import json
from pathlib import Path

import pytest

from sdd_copilot.exceptions import InvalidStatusError, StatusFileError
from sdd_copilot.models import SpecStatus
from sdd_copilot.status import _validate_status as get_status_from_value, get_status, load_all_statuses, set_status


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_pending_when_no_file(self, tmp_path: Path) -> None:
        assert get_status(tmp_path, 1) == SpecStatus.PENDING

    def test_reads_existing_status(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "done"}), encoding="utf-8"
        )
        assert get_status(tmp_path, 1) == SpecStatus.DONE

    def test_returns_pending_for_missing_key(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"2": "done"}), encoding="utf-8"
        )
        assert get_status(tmp_path, 1) == SpecStatus.PENDING

    def test_invalid_status_value_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "bogus"}), encoding="utf-8"
        )
        with pytest.raises(InvalidStatusError):
            get_status(tmp_path, 1)


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------


class TestSetStatus:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        set_status(tmp_path, 1, SpecStatus.PLANNED)
        data = json.loads((tmp_path / ".sdd-status.json").read_text(encoding="utf-8"))
        assert data["1"] == "planned"

    def test_updates_existing_key(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "pending"}), encoding="utf-8"
        )
        set_status(tmp_path, 1, SpecStatus.DONE)
        data = json.loads((tmp_path / ".sdd-status.json").read_text(encoding="utf-8"))
        assert data["1"] == "done"

    def test_preserves_other_keys(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "done", "2": "pending"}), encoding="utf-8"
        )
        set_status(tmp_path, 2, SpecStatus.BUILDING)
        data = json.loads((tmp_path / ".sdd-status.json").read_text(encoding="utf-8"))
        assert data["1"] == "done"
        assert data["2"] == "building"

    def test_output_is_sorted_and_indented(self, tmp_path: Path) -> None:
        set_status(tmp_path, 2, SpecStatus.PENDING)
        set_status(tmp_path, 1, SpecStatus.DONE)
        text = (tmp_path / ".sdd-status.json").read_text(encoding="utf-8")
        assert text.endswith("\n")
        data = json.loads(text)
        keys = list(data.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# load_all_statuses
# ---------------------------------------------------------------------------


class TestLoadAllStatuses:
    def test_empty_when_no_file(self, tmp_path: Path) -> None:
        result = load_all_statuses(tmp_path)
        assert result == {}

    def test_returns_int_keys_and_enum_values(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "done", "2": "building"}), encoding="utf-8"
        )
        result = load_all_statuses(tmp_path)
        assert result == {1: SpecStatus.DONE, 2: SpecStatus.BUILDING}

    def test_invalid_value_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text(
            json.dumps({"1": "nope"}), encoding="utf-8"
        )
        with pytest.raises(InvalidStatusError):
            load_all_statuses(tmp_path)


# ---------------------------------------------------------------------------
# Error handling — corrupt files
# ---------------------------------------------------------------------------


class TestStatusFileErrors:
    def test_corrupt_json_raises_status_file_error(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text("not json", encoding="utf-8")
        with pytest.raises(StatusFileError):
            get_status(tmp_path, 1)

    def test_json_array_raises_status_file_error(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(StatusFileError, match="Expected a JSON object"):
            get_status(tmp_path, 1)

    def test_write_to_readonly_dir_raises(self, tmp_path: Path) -> None:
        status_file = tmp_path / ".sdd-status.json"
        status_file.write_text("{}", encoding="utf-8")
        status_file.chmod(0o444)
        try:
            with pytest.raises(StatusFileError):
                set_status(tmp_path, 1, SpecStatus.DONE)
        finally:
            status_file.chmod(0o644)

    def test_write_error_chains_cause(self, tmp_path: Path) -> None:
        status_file = tmp_path / ".sdd-status.json"
        status_file.write_text("{}", encoding="utf-8")
        status_file.chmod(0o444)
        try:
            with pytest.raises(StatusFileError) as exc_info:
                set_status(tmp_path, 1, SpecStatus.DONE)
            assert exc_info.value.__cause__ is not None
        finally:
            status_file.chmod(0o644)

    def test_read_error_chains_cause(self, tmp_path: Path) -> None:
        (tmp_path / ".sdd-status.json").write_text("not json", encoding="utf-8")
        with pytest.raises(StatusFileError) as exc_info:
            get_status(tmp_path, 1)
        assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# validate_status round-trip
# ---------------------------------------------------------------------------


class TestValidateStatus:
    def test_all_enum_values_round_trip(self) -> None:
        for s in SpecStatus:
            assert get_status_from_value(s.value) == s

    def test_from_none_suppresses_context(self) -> None:
        with pytest.raises(InvalidStatusError) as exc_info:
            get_status_from_value("bogus")
        assert exc_info.value.__cause__ is None


# ---------------------------------------------------------------------------
# _STATUS_FILE constant
# ---------------------------------------------------------------------------


class TestStatusFileConstant:
    def test_status_filename(self) -> None:
        from sdd_copilot.status import _STATUS_FILE
        assert _STATUS_FILE == ".sdd-status.json"


# ---------------------------------------------------------------------------
# Edge case: multiple set_status calls in sequence
# ---------------------------------------------------------------------------


class TestSetStatusMultipleCalls:
    def test_multiple_specs_persisted(self, tmp_path: Path) -> None:
        set_status(tmp_path, 1, SpecStatus.PLANNED)
        set_status(tmp_path, 2, SpecStatus.BUILDING)
        set_status(tmp_path, 3, SpecStatus.DONE)
        result = load_all_statuses(tmp_path)
        assert result == {
            1: SpecStatus.PLANNED,
            2: SpecStatus.BUILDING,
            3: SpecStatus.DONE,
        }

    def test_overwrite_same_spec(self, tmp_path: Path) -> None:
        set_status(tmp_path, 1, SpecStatus.PENDING)
        set_status(tmp_path, 1, SpecStatus.PLANNED)
        set_status(tmp_path, 1, SpecStatus.DONE)
        assert get_status(tmp_path, 1) == SpecStatus.DONE
