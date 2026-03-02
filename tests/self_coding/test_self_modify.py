"""Tests for the self-modification loop (self_modify/loop.py).

All tests are fully mocked — no Ollama, no real file I/O, no git.
"""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from self_coding.self_modify.loop import SelfModifyLoop, ModifyRequest, ModifyResult


# ── Dataclass tests ───────────────────────────────────────────────────────────


class TestModifyRequest:
    def test_defaults(self):
        req = ModifyRequest(instruction="Fix the bug")
        assert req.instruction == "Fix the bug"
        assert req.target_files == []
        assert req.dry_run is False

    def test_with_target_files(self):
        req = ModifyRequest(
            instruction="Add docstring",
            target_files=["src/foo.py"],
            dry_run=True,
        )
        assert req.target_files == ["src/foo.py"]
        assert req.dry_run is True


class TestModifyResult:
    def test_success_result(self):
        result = ModifyResult(
            success=True,
            files_changed=["src/foo.py"],
            test_passed=True,
            commit_sha="abc12345",
            branch_name="timmy/self-modify-123",
            llm_response="...",
            attempts=1,
        )
        assert result.success
        assert result.commit_sha == "abc12345"
        assert result.error is None
        assert result.autonomous_cycles == 0

    def test_failure_result(self):
        result = ModifyResult(success=False, error="something broke")
        assert not result.success
        assert result.error == "something broke"
        assert result.files_changed == []


# ── SelfModifyLoop unit tests ────────────────────────────────────────────────


class TestSelfModifyLoop:
    def test_init_defaults(self):
        loop = SelfModifyLoop()
        assert loop._max_retries == 2

    def test_init_custom_retries(self):
        loop = SelfModifyLoop(max_retries=5)
        assert loop._max_retries == 5

    def test_init_backend(self):
        loop = SelfModifyLoop(backend="anthropic")
        assert loop._backend == "anthropic"

    def test_init_autonomous(self):
        loop = SelfModifyLoop(autonomous=True, max_autonomous_cycles=5)
        assert loop._autonomous is True
        assert loop._max_autonomous_cycles == 5

    @patch("self_coding.self_modify.loop.settings")
    def test_run_disabled(self, mock_settings):
        mock_settings.self_modify_enabled = False
        loop = SelfModifyLoop()
        result = loop.run(ModifyRequest(instruction="test"))
        assert not result.success
        assert "disabled" in result.error.lower()

    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_run_no_target_files(self, mock_settings):
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 0
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"
        loop = SelfModifyLoop()
        loop._infer_target_files = MagicMock(return_value=[])
        result = loop.run(ModifyRequest(instruction="do something vague"))
        assert not result.success
        assert "no target files" in result.error.lower()

    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_run_success_path(self, mock_settings):
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 2
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"

        loop = SelfModifyLoop()
        loop._read_files = MagicMock(return_value={"src/foo.py": "old content"})
        loop._generate_edits = MagicMock(
            return_value=({"src/foo.py": "x = 1\n"}, "llm raw")
        )
        loop._write_files = MagicMock(return_value=["src/foo.py"])
        loop._run_tests = MagicMock(return_value=(True, "5 passed"))
        loop._git_commit = MagicMock(return_value="abc12345")
        loop._validate_paths = MagicMock()

        result = loop.run(
            ModifyRequest(instruction="Add docstring", target_files=["src/foo.py"])
        )

        assert result.success
        assert result.test_passed
        assert result.commit_sha == "abc12345"
        assert result.files_changed == ["src/foo.py"]
        loop._run_tests.assert_called_once()
        loop._git_commit.assert_called_once()

    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_run_test_failure_reverts(self, mock_settings):
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 0
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"

        loop = SelfModifyLoop(max_retries=0)
        loop._read_files = MagicMock(return_value={"src/foo.py": "old content"})
        loop._generate_edits = MagicMock(
            return_value=({"src/foo.py": "x = 1\n"}, "llm raw")
        )
        loop._write_files = MagicMock(return_value=["src/foo.py"])
        loop._run_tests = MagicMock(return_value=(False, "1 failed"))
        loop._revert_files = MagicMock()
        loop._validate_paths = MagicMock()

        result = loop.run(
            ModifyRequest(instruction="Break it", target_files=["src/foo.py"])
        )

        assert not result.success
        assert not result.test_passed
        loop._revert_files.assert_called()

    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_dry_run(self, mock_settings):
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 2
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"

        loop = SelfModifyLoop()
        loop._read_files = MagicMock(return_value={"src/foo.py": "old content"})
        loop._generate_edits = MagicMock(
            return_value=({"src/foo.py": "x = 1\n"}, "llm raw")
        )
        loop._validate_paths = MagicMock()

        result = loop.run(
            ModifyRequest(
                instruction="Add docstring",
                target_files=["src/foo.py"],
                dry_run=True,
            )
        )

        assert result.success
        assert result.files_changed == ["src/foo.py"]


# ── Syntax validation tests ─────────────────────────────────────────────────


class TestSyntaxValidation:
    def test_valid_python_passes(self):
        loop = SelfModifyLoop()
        errors = loop._validate_syntax({"src/foo.py": "x = 1\nprint(x)\n"})
        assert errors == {}

    def test_invalid_python_caught(self):
        loop = SelfModifyLoop()
        errors = loop._validate_syntax({"src/foo.py": "def foo(\n"})
        assert "src/foo.py" in errors
        assert "line" in errors["src/foo.py"]

    def test_unterminated_string_caught(self):
        loop = SelfModifyLoop()
        bad_code = '"""\nTIMMY = """\nstuff\n"""\n'
        errors = loop._validate_syntax({"src/foo.py": bad_code})
        # This specific code is actually valid, but let's test truly broken code
        broken = '"""\nunclosed string\n'
        errors = loop._validate_syntax({"src/foo.py": broken})
        assert "src/foo.py" in errors

    def test_non_python_files_skipped(self):
        loop = SelfModifyLoop()
        errors = loop._validate_syntax({"README.md": "this is not python {{{}"})
        assert errors == {}

    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_syntax_error_skips_write(self, mock_settings):
        """When LLM produces invalid syntax, we skip writing and retry."""
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 1
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"

        loop = SelfModifyLoop(max_retries=1)
        loop._read_files = MagicMock(return_value={"src/foo.py": "x = 1\n"})
        # First call returns broken syntax, second returns valid
        loop._generate_edits = MagicMock(side_effect=[
            ({"src/foo.py": "def foo(\n"}, "bad llm"),
            ({"src/foo.py": "def foo():\n    pass\n"}, "good llm"),
        ])
        loop._write_files = MagicMock(return_value=["src/foo.py"])
        loop._run_tests = MagicMock(return_value=(True, "passed"))
        loop._git_commit = MagicMock(return_value="abc123")
        loop._validate_paths = MagicMock()

        result = loop.run(
            ModifyRequest(instruction="Fix foo", target_files=["src/foo.py"])
        )

        assert result.success
        # _write_files should only be called once (for the valid attempt)
        loop._write_files.assert_called_once()


# ── Multi-backend tests ──────────────────────────────────────────────────────


class TestBackendResolution:
    def test_resolve_ollama(self):
        loop = SelfModifyLoop(backend="ollama")
        assert loop._resolve_backend() == "ollama"

    def test_resolve_anthropic(self):
        loop = SelfModifyLoop(backend="anthropic")
        assert loop._resolve_backend() == "anthropic"

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"})
    def test_resolve_auto_with_key(self):
        loop = SelfModifyLoop(backend="auto")
        assert loop._resolve_backend() == "anthropic"

    @patch.dict("os.environ", {}, clear=True)
    def test_resolve_auto_without_key(self):
        loop = SelfModifyLoop(backend="auto")
        assert loop._resolve_backend() == "ollama"


# ── Autonomous loop tests ────────────────────────────────────────────────────


class TestAutonomousLoop:
    @patch("self_coding.self_modify.loop.os.environ", {"SELF_MODIFY_SKIP_BRANCH": "1"})
    @patch("self_coding.self_modify.loop.settings")
    def test_autonomous_retries_after_failure(self, mock_settings):
        mock_settings.self_modify_enabled = True
        mock_settings.self_modify_max_retries = 0
        mock_settings.self_modify_allowed_dirs = "src,tests"
        mock_settings.self_modify_backend = "ollama"

        loop = SelfModifyLoop(max_retries=0, autonomous=True, max_autonomous_cycles=2)
        loop._validate_paths = MagicMock()
        loop._read_files = MagicMock(return_value={"src/foo.py": "x = 1\n"})

        # First run fails, autonomous cycle 1 succeeds
        call_count = [0]

        def fake_generate(instruction, contents, prev_test_output=None, prev_syntax_errors=None):
            call_count[0] += 1
            return ({"src/foo.py": "x = 2\n"}, "llm raw")

        loop._generate_edits = MagicMock(side_effect=fake_generate)
        loop._write_files = MagicMock(return_value=["src/foo.py"])
        loop._revert_files = MagicMock()

        # First call fails tests, second succeeds
        test_results = [(False, "FAILED"), (True, "PASSED")]
        loop._run_tests = MagicMock(side_effect=test_results)
        loop._git_commit = MagicMock(return_value="abc123")
        loop._diagnose_failure = MagicMock(return_value="Fix: do X instead of Y")

        result = loop.run(
            ModifyRequest(instruction="Fix foo", target_files=["src/foo.py"])
        )

        assert result.success
        assert result.autonomous_cycles == 1
        loop._diagnose_failure.assert_called_once()

    def test_diagnose_failure_reads_report(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report\n**Error:** SyntaxError line 5\n")

        loop = SelfModifyLoop(backend="ollama")
        loop._call_llm = MagicMock(return_value="ROOT CAUSE: Missing closing paren")

        diagnosis = loop._diagnose_failure(report)
        assert "Missing closing paren" in diagnosis
        loop._call_llm.assert_called_once()

    def test_diagnose_failure_handles_missing_report(self, tmp_path):
        loop = SelfModifyLoop(backend="ollama")
        result = loop._diagnose_failure(tmp_path / "nonexistent.md")
        assert result is None


# ── Path validation tests ─────────────────────────────────────────────────────


class TestPathValidation:
    def test_rejects_path_outside_repo(self):
        loop = SelfModifyLoop(repo_path=Path("/tmp/test-repo"))
        with pytest.raises(ValueError, match="escapes repository"):
            loop._validate_paths(["../../etc/passwd"])

    def test_rejects_path_outside_allowed_dirs(self):
        loop = SelfModifyLoop(repo_path=Path("/tmp/test-repo"))
        with pytest.raises(ValueError, match="not in allowed directories"):
            loop._validate_paths(["docs/secret.py"])

    def test_accepts_src_path(self):
        loop = SelfModifyLoop(repo_path=Path("/tmp/test-repo"))
        loop._validate_paths(["src/some_module.py"])

    def test_accepts_tests_path(self):
        loop = SelfModifyLoop(repo_path=Path("/tmp/test-repo"))
        loop._validate_paths(["tests/test_something.py"])


# ── File inference tests ──────────────────────────────────────────────────────


class TestFileInference:
    def test_infer_explicit_py_path(self):
        loop = SelfModifyLoop()
        files = loop._infer_target_files("fix bug in src/dashboard/app.py")
        assert "src/dashboard/app.py" in files

    def test_infer_from_keyword_config(self):
        loop = SelfModifyLoop()
        files = loop._infer_target_files("update the config to add a new setting")
        assert "src/config.py" in files

    def test_infer_from_keyword_agent(self):
        loop = SelfModifyLoop()
        files = loop._infer_target_files("modify the agent prompt")
        assert "src/timmy/agent.py" in files

    def test_infer_returns_empty_for_vague(self):
        loop = SelfModifyLoop()
        files = loop._infer_target_files("do something cool")
        assert files == []


# ── NLU intent tests ──────────────────────────────────────────────────────────


class TestCodeIntent:
    def test_detects_modify_code(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("modify the code in config.py")
        assert intent.name == "code"

    def test_detects_self_modify(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("self-modify to add a new endpoint")
        assert intent.name == "code"

    def test_detects_edit_source(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("edit the source to fix the bug")
        assert intent.name == "code"

    def test_detects_update_your_code(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("update your code to handle errors")
        assert intent.name == "code"

    def test_detects_fix_function(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("fix the function that calculates totals")
        assert intent.name == "code"

    def test_does_not_match_general_chat(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("tell me about the weather today")
        assert intent.name == "chat"

    def test_extracts_target_file_entity(self):
        from integrations.voice.nlu import detect_intent

        intent = detect_intent("modify file src/config.py to add debug flag")
        assert intent.entities.get("target_file") == "src/config.py"


# ── Route tests ───────────────────────────────────────────────────────────────


class TestSelfModifyRoutes:
    def test_status_endpoint(self, client):
        resp = client.get("/self-modify/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert data["enabled"] is False  # Default

    def test_run_when_disabled(self, client):
        resp = client.post("/self-modify/run", data={"instruction": "test"})
        assert resp.status_code == 403

