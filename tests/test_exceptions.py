"""Tests for sdd_copilot.exceptions — custom exception hierarchy."""

from pathlib import Path

import pytest

from sdd_copilot.exceptions import (
    BuilderError,
    ConstitutionMissingError,
    InvalidStatusError,
    PlannerError,
    RunnerError,
    SddError,
    SpecLoadError,
    SpecNotFoundError,
    StatusFileError,
)


# ---------------------------------------------------------------------------
# Hierarchy — every exception is an SddError
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """All domain exceptions must inherit from SddError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            SpecLoadError,
            StatusFileError,
            InvalidStatusError,
            SpecNotFoundError,
            ConstitutionMissingError,
            RunnerError,
            PlannerError,
            BuilderError,
        ],
    )
    def test_inherits_from_sdd_error(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, SddError)

    def test_sdd_error_inherits_from_exception(self) -> None:
        assert issubclass(SddError, Exception)


# ---------------------------------------------------------------------------
# Individual exception construction and fields
# ---------------------------------------------------------------------------


class TestSpecLoadError:
    def test_message_includes_path_and_reason(self) -> None:
        exc = SpecLoadError(Path("/specs/01-foo.md"), "File not found")
        assert "/specs/01-foo.md" in str(exc)
        assert "File not found" in str(exc)

    def test_fields_stored(self) -> None:
        p = Path("/specs/01-foo.md")
        exc = SpecLoadError(p, "bad utf-8")
        assert exc.path == p
        assert exc.reason == "bad utf-8"


class TestStatusFileError:
    def test_message_format(self) -> None:
        exc = StatusFileError(Path("/d/.sdd-status.json"), "corrupt")
        assert "Status file error" in str(exc)
        assert "corrupt" in str(exc)

    def test_fields_stored(self) -> None:
        p = Path("/d/.sdd-status.json")
        exc = StatusFileError(p, "corrupt")
        assert exc.path == p
        assert exc.reason == "corrupt"


class TestInvalidStatusError:
    def test_message_lists_valid_values(self) -> None:
        exc = InvalidStatusError("bogus", ["pending", "done"])
        assert "bogus" in str(exc)
        assert "pending" in str(exc)
        assert "done" in str(exc)

    def test_fields_stored(self) -> None:
        exc = InvalidStatusError("x", ["a", "b"])
        assert exc.value == "x"
        assert exc.valid == ["a", "b"]


class TestSpecNotFoundError:
    def test_message_includes_spec_number(self) -> None:
        exc = SpecNotFoundError(5)
        assert "05" in str(exc)

    def test_field_stored(self) -> None:
        exc = SpecNotFoundError(42)
        assert exc.spec_number == 42


class TestConstitutionMissingError:
    def test_message_includes_spec_dir(self) -> None:
        exc = ConstitutionMissingError(Path("/my/specs"))
        assert "/my/specs" in str(exc)

    def test_field_stored(self) -> None:
        p = Path("/my/specs")
        exc = ConstitutionMissingError(p)
        assert exc.spec_dir == p


class TestRunnerError:
    def test_message_format(self) -> None:
        exc = RunnerError(Path("/wd"), "timed out")
        assert "Runner error" in str(exc)
        assert "timed out" in str(exc)

    def test_fields_stored(self) -> None:
        p = Path("/wd")
        exc = RunnerError(p, "reason")
        assert exc.path == p
        assert exc.reason == "reason"


class TestPlannerError:
    def test_message_format(self) -> None:
        exc = PlannerError(Path("/spec.md"), "parse failed")
        assert "Planner error" in str(exc)
        assert "parse failed" in str(exc)

    def test_fields_stored(self) -> None:
        p = Path("/spec.md")
        exc = PlannerError(p, "r")
        assert exc.path == p
        assert exc.reason == "r"


class TestBuilderError:
    def test_message_format(self) -> None:
        exc = BuilderError(Path("/tasks/tasks-01.md"), "task file empty")
        assert "Builder error" in str(exc)
        assert "task file empty" in str(exc)

    def test_fields_stored(self) -> None:
        p = Path("/tasks/tasks-01.md")
        exc = BuilderError(p, "missing")
        assert exc.path == p
        assert exc.reason == "missing"


# ---------------------------------------------------------------------------
# Catchability
# ---------------------------------------------------------------------------


class TestCatchBroadly:
    def test_catch_sdd_error_catches_specific(self) -> None:
        with pytest.raises(SddError):
            raise SpecLoadError(Path("."), "boom")

    def test_catch_sdd_error_catches_runner_error(self) -> None:
        with pytest.raises(SddError):
            raise RunnerError(Path("."), "boom")
