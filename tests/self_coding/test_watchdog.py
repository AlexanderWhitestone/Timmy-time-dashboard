from unittest.mock import MagicMock, patch

from self_tdd.watchdog import _run_tests


def _mock_result(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_run_tests_returns_true_when_suite_passes():
    with patch("self_tdd.watchdog.subprocess.run", return_value=_mock_result(0, "5 passed")):
        passed, _ = _run_tests()
    assert passed is True


def test_run_tests_returns_false_when_suite_fails():
    with patch("self_tdd.watchdog.subprocess.run", return_value=_mock_result(1, "1 failed")):
        passed, _ = _run_tests()
    assert passed is False


def test_run_tests_output_includes_stdout():
    with patch("self_tdd.watchdog.subprocess.run", return_value=_mock_result(0, stdout="5 passed")):
        _, output = _run_tests()
    assert "5 passed" in output


def test_run_tests_output_combines_stdout_and_stderr():
    with patch(
        "self_tdd.watchdog.subprocess.run",
        return_value=_mock_result(1, stdout="FAILED test_foo", stderr="ImportError: no module named bar"),
    ):
        _, output = _run_tests()
    assert "FAILED test_foo" in output
    assert "ImportError" in output


def test_run_tests_invokes_pytest_with_correct_flags():
    with patch("self_tdd.watchdog.subprocess.run", return_value=_mock_result(0)) as mock_run:
        _run_tests()
    cmd = mock_run.call_args[0][0]
    assert "pytest" in cmd
    assert "tests/" in cmd
    assert "--tb=short" in cmd


def test_run_tests_uses_60s_timeout():
    with patch("self_tdd.watchdog.subprocess.run", return_value=_mock_result(0)) as mock_run:
        _run_tests()
    assert mock_run.call_args.kwargs["timeout"] == 60
