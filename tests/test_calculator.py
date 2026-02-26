"""Tests for the calculator tool."""

from timmy.tools import calculator


def test_basic_multiplication():
    assert calculator("347 * 829") == "287663"


def test_basic_addition():
    assert calculator("100 + 200") == "300"


def test_basic_division():
    assert calculator("100 / 4") == "25.0"


def test_integer_division():
    assert calculator("100 // 3") == "33"


def test_exponentiation():
    assert calculator("2 ** 10") == "1024"


def test_sqrt():
    assert calculator("math.sqrt(17161)") == "131.0"


def test_sqrt_non_perfect():
    result = float(calculator("math.sqrt(2)"))
    assert abs(result - 1.4142135623730951) < 1e-10


def test_log_base_10():
    result = float(calculator("math.log10(1000)"))
    assert abs(result - 3.0) < 1e-10


def test_log_natural():
    result = float(calculator("math.log(math.e)"))
    assert abs(result - 1.0) < 1e-10


def test_trig_sin():
    result = float(calculator("math.sin(math.pi / 2)"))
    assert abs(result - 1.0) < 1e-10


def test_abs_builtin():
    assert calculator("abs(-42)") == "42"


def test_round_builtin():
    assert calculator("round(3.14159, 2)") == "3.14"


def test_min_max_builtins():
    assert calculator("min(3, 7, 1)") == "1"
    assert calculator("max(3, 7, 1)") == "7"


def test_complex_expression():
    assert calculator("(347 * 829) + (100 / 4)") == "287688.0"


def test_invalid_expression_returns_error():
    result = calculator("not a valid expression")
    assert result.startswith("Error evaluating")


def test_no_builtins_access():
    """Ensure dangerous builtins like __import__ are blocked."""
    result = calculator("__import__('os').system('echo pwned')")
    assert result.startswith("Error evaluating")


def test_no_open_access():
    result = calculator("open('/etc/passwd').read()")
    assert result.startswith("Error evaluating")


def test_division_by_zero():
    result = calculator("1 / 0")
    assert result.startswith("Error evaluating")
