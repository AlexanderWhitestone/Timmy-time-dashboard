"""Functional tests for self_tdd.watchdog — continuous test runner.

All subprocess calls are mocked to avoid running real pytest.
"""

from unittest.mock import patch, MagicMock, call

import pytest

from self_tdd.watchdog import _run_tests, watch


class TestRunTests:
    @patch("self_tdd.watchdog.subprocess.run")
    def test_run_tests_passing(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="5 passed\n",
            stderr="",
        )
        passed, output = _run_tests()
        assert passed is True
        assert "5 passed" in output

    @patch("self_tdd.watchdog.subprocess.run")
    def test_run_tests_failing(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="2 failed, 3 passed\n",
            stderr="ERRORS",
        )
        passed, output = _run_tests()
        assert passed is False
        assert "2 failed" in output
        assert "ERRORS" in output

    @patch("self_tdd.watchdog.subprocess.run")
    def test_run_tests_command_format(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_tests()
        cmd = mock_run.call_args[0][0]
        assert "pytest" in " ".join(cmd)
        assert "tests/" in cmd
        assert "-q" in cmd
        assert "--tb=short" in cmd
        assert mock_run.call_args[1]["capture_output"] is True
        assert mock_run.call_args[1]["text"] is True


class TestWatch:
    @patch("self_tdd.watchdog.time.sleep")
    @patch("self_tdd.watchdog._run_tests")
    @patch("self_tdd.watchdog.typer")
    def test_watch_first_pass(self, mock_typer, mock_tests, mock_sleep):
        """First iteration: None→passing → should print green message."""
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt
            return (True, "all good")

        mock_tests.side_effect = side_effect
        watch(interval=10)
        # Should have printed green "All tests passing" message
        mock_typer.secho.assert_called()

    @patch("self_tdd.watchdog.time.sleep")
    @patch("self_tdd.watchdog._run_tests")
    @patch("self_tdd.watchdog.typer")
    def test_watch_regression(self, mock_typer, mock_tests, mock_sleep):
        """Regression: passing→failing → should print red message + output."""
        results = [(True, "ok"), (False, "FAILED: test_foo"), KeyboardInterrupt]
        idx = 0

        def side_effect():
            nonlocal idx
            if idx >= len(results):
                raise KeyboardInterrupt
            r = results[idx]
            idx += 1
            if isinstance(r, type) and issubclass(r, BaseException):
                raise r()
            return r

        mock_tests.side_effect = side_effect
        watch(interval=5)
        # Should have printed red "Regression detected" at some point
        secho_calls = [str(c) for c in mock_typer.secho.call_args_list]
        assert any("Regression" in c for c in secho_calls) or any("RED" in c for c in secho_calls)

    @patch("self_tdd.watchdog.time.sleep")
    @patch("self_tdd.watchdog._run_tests")
    @patch("self_tdd.watchdog.typer")
    def test_watch_keyboard_interrupt(self, mock_typer, mock_tests, mock_sleep):
        mock_tests.side_effect = KeyboardInterrupt
        watch(interval=60)
        mock_typer.echo.assert_called()  # "Watchdog stopped"
