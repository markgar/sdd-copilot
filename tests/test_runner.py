"""Tests for sdd_copilot.runner — CopilotResult and run_copilot."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdd_copilot.exceptions import RunnerError
from sdd_copilot.runner import DEFAULT_MODEL, CopilotResult, run_copilot


# ---------------------------------------------------------------------------
# CopilotResult
# ---------------------------------------------------------------------------


class TestCopilotResult:
    def test_success_when_exit_code_zero(self) -> None:
        r = CopilotResult(exit_code=0, output="ok")
        assert r.success is True

    def test_failure_when_exit_code_nonzero(self) -> None:
        r = CopilotResult(exit_code=1, output="err")
        assert r.success is False

    def test_frozen(self) -> None:
        r = CopilotResult(exit_code=0)
        with pytest.raises(AttributeError):
            r.exit_code = 1  # type: ignore[misc]

    def test_default_output_is_empty(self) -> None:
        r = CopilotResult(exit_code=0)
        assert r.output == ""

    def test_success_derived_not_init(self) -> None:
        r = CopilotResult(exit_code=42)
        assert r.success is False
        r2 = CopilotResult(exit_code=0)
        assert r2.success is True


# ---------------------------------------------------------------------------
# run_copilot — copilot not found
# ---------------------------------------------------------------------------


class TestRunCopilotNotFound:
    @patch("sdd_copilot.runner.shutil.which", return_value=None)
    def test_raises_runner_error(self, _mock_which: MagicMock) -> None:
        with pytest.raises(RunnerError, match="not found"):
            run_copilot("prompt", Path("/wd"))


# ---------------------------------------------------------------------------
# run_copilot — happy path (no capture)
# ---------------------------------------------------------------------------


class TestRunCopilotNocapture:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_returns_result_no_capture(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        result = run_copilot("hello", Path("/wd"))
        assert result.success is True
        assert result.output == ""

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_passes_correct_command(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("my prompt", Path("/wd"), model="test-model")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/copilot"
        assert "-p" in cmd
        assert "my prompt" in cmd
        assert "--model" in cmd
        assert "test-model" in cmd
        assert "--yolo" in cmd
        assert mock_run.call_args[1]["cwd"] == Path("/wd")


# ---------------------------------------------------------------------------
# run_copilot — capture mode
# ---------------------------------------------------------------------------


class TestRunCopilotCapture:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_captures_stdout(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="captured text")
        result = run_copilot("prompt", Path("/wd"), capture=True)
        assert result.output == "captured text"
        assert mock_run.call_args[1].get("stdout") == subprocess.PIPE

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_nonzero_exit_code(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="error output")
        result = run_copilot("prompt", Path("/wd"), capture=True)
        assert result.success is False
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# run_copilot — extra dirs
# ---------------------------------------------------------------------------


class TestRunCopilotExtraDirs:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_extra_dirs_added(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot(
            "prompt",
            Path("/wd"),
            extra_dirs=(Path("/a"), Path("/b")),
        )
        cmd = mock_run.call_args[0][0]
        assert "--add-dir" in cmd
        idx = cmd.index("--add-dir")
        assert cmd[idx + 1] == "/a"


# ---------------------------------------------------------------------------
# run_copilot — error handling
# ---------------------------------------------------------------------------


class TestRunCopilotErrors:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_timeout_raises_runner_error(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="copilot", timeout=10)
        with pytest.raises(RunnerError, match="timed out"):
            run_copilot("prompt", Path("/wd"), timeout=10)

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_oserror_raises_runner_error(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.side_effect = OSError("Permission denied")
        with pytest.raises(RunnerError, match="Permission denied"):
            run_copilot("prompt", Path("/wd"))

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_timeout_chains_original(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        original = subprocess.TimeoutExpired(cmd="copilot", timeout=10)
        mock_run.side_effect = original
        with pytest.raises(RunnerError) as exc_info:
            run_copilot("prompt", Path("/wd"))
        assert exc_info.value.__cause__ is original

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_oserror_chains_original(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        original = OSError("fail")
        mock_run.side_effect = original
        with pytest.raises(RunnerError) as exc_info:
            run_copilot("prompt", Path("/wd"))
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# DEFAULT_MODEL constant
# ---------------------------------------------------------------------------


class TestDefaultModel:
    def test_is_string(self) -> None:
        assert isinstance(DEFAULT_MODEL, str)
        assert len(DEFAULT_MODEL) > 0

    def test_value(self) -> None:
        assert DEFAULT_MODEL == "claude-sonnet-4.6"


# ---------------------------------------------------------------------------
# CopilotResult — additional edge cases
# ---------------------------------------------------------------------------


class TestCopilotResultEdgeCases:
    def test_negative_exit_code_is_failure(self) -> None:
        r = CopilotResult(exit_code=-1)
        assert r.success is False

    def test_large_exit_code_is_failure(self) -> None:
        r = CopilotResult(exit_code=127)
        assert r.success is False

    def test_output_preserved(self) -> None:
        r = CopilotResult(exit_code=0, output="multi\nline\noutput")
        assert r.output == "multi\nline\noutput"


# ---------------------------------------------------------------------------
# run_copilot — command flags
# ---------------------------------------------------------------------------


class TestRunCopilotCommandFlags:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_session_flag_present(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"))
        cmd = mock_run.call_args[0][0]
        assert "-s" in cmd

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_autopilot_flag_present(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"))
        cmd = mock_run.call_args[0][0]
        assert "--autopilot" in cmd
        assert "--no-ask-user" in cmd

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_default_model_used(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"))
        cmd = mock_run.call_args[0][0]
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == DEFAULT_MODEL

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_timeout_forwarded_to_subprocess(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"), timeout=42)
        assert mock_run.call_args[1]["timeout"] == 42

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_no_extra_dirs_default(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"))
        cmd = mock_run.call_args[0][0]
        assert "--add-dir" not in cmd

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_multiple_extra_dirs(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"), extra_dirs=(Path("/a"), Path("/b")))
        cmd = mock_run.call_args[0][0]
        add_dir_indices = [i for i, v in enumerate(cmd) if v == "--add-dir"]
        assert len(add_dir_indices) == 2
        assert cmd[add_dir_indices[0] + 1] == "/a"
        assert cmd[add_dir_indices[1] + 1] == "/b"


# ---------------------------------------------------------------------------
# run_copilot — live output (no capture)
# ---------------------------------------------------------------------------


class TestRunCopilotLiveOutput:
    """Validates that non-capture mode streams to terminal (no stdout=PIPE)."""

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_no_capture_does_not_pipe_stdout(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"), capture=False)
        kwargs = mock_run.call_args[1]
        assert "stdout" not in kwargs

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_capture_pipes_stdout(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="text")
        run_copilot("prompt", Path("/wd"), capture=True)
        kwargs = mock_run.call_args[1]
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["text"] is True

    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_capture_false_returns_empty_output(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        result = run_copilot("prompt", Path("/wd"), capture=False)
        assert result.output == ""


# ---------------------------------------------------------------------------
# run_copilot — empty extra_dirs tuple
# ---------------------------------------------------------------------------


class TestRunCopilotEmptyExtraDirs:
    @patch("sdd_copilot.runner.subprocess.run")
    @patch("sdd_copilot.runner.shutil.which", return_value="/usr/bin/copilot")
    def test_empty_tuple_no_add_dir_flags(
        self, _mock_which: MagicMock, mock_run: MagicMock
    ) -> None:
        """An empty extra_dirs tuple should not add --add-dir flags."""
        mock_run.return_value = MagicMock(returncode=0, stdout=None)
        run_copilot("prompt", Path("/wd"), extra_dirs=())
        cmd = mock_run.call_args[0][0]
        assert "--add-dir" not in cmd
