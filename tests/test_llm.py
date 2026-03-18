"""Tests for LLM client."""

from unittest.mock import patch, MagicMock
import subprocess

import pytest

from diagram_update.llm import (
    generate_diagram,
    _build_prompt,
    _parse_response,
    _call_gh_copilot,
    _check_gh_available,
)
from diagram_update.models import LLMError, ToolError


class TestParseResponse:
    """Tests for response parsing and fence stripping."""

    def test_plain_d2(self):
        raw = "api: API\ndb: Database\napi -> db"
        assert _parse_response(raw) == raw

    def test_strip_d2_fence(self):
        raw = "```d2\napi: API\ndb: Database\napi -> db\n```"
        assert _parse_response(raw) == "api: API\ndb: Database\napi -> db"

    def test_strip_generic_fence(self):
        raw = "```\napi: API\napi -> db\n```"
        assert _parse_response(raw) == "api: API\napi -> db"

    def test_strip_diagram_fence(self):
        raw = "```diagram\napi: API\n```"
        assert _parse_response(raw) == "api: API"

    def test_empty_response(self):
        assert _parse_response("") == ""
        assert _parse_response("   ") == ""

    def test_whitespace_stripped(self):
        raw = "  \n  api: API\n  api -> db\n  \n"
        result = _parse_response(raw)
        assert result.startswith("api: API")
        assert result.endswith("api -> db")

    def test_fence_with_leading_content(self):
        # Fences that aren't the entire output - leading fence stripped
        raw = "```d2\napi: API\napi -> db\n```"
        result = _parse_response(raw)
        assert "```" not in result
        assert "api: API" in result


class TestBuildPrompt:
    """Tests for prompt construction."""

    def test_contains_skeleton(self):
        prompt = _build_prompt("FILE TREE:\napp.py", "architecture", None)
        assert "FILE TREE:" in prompt
        assert "app.py" in prompt

    def test_contains_diagram_type(self):
        prompt = _build_prompt("skeleton", "dependencies", None)
        assert "dependencies" in prompt

    def test_includes_existing_d2(self):
        existing = "api: API\napi -> db"
        prompt = _build_prompt("skeleton", "architecture", existing)
        assert "api: API" in prompt
        assert "Preserve the structure" in prompt

    def test_no_existing_d2(self):
        prompt = _build_prompt("skeleton", "architecture", None)
        assert "Preserve the structure" not in prompt

    def test_d2_syntax_rules_included(self):
        prompt = _build_prompt("skeleton", "architecture", None)
        assert "D2 syntax rules" in prompt
        assert "Nodes:" in prompt
        assert "Connections:" in prompt

    def test_ends_with_output_instruction(self):
        prompt = _build_prompt("skeleton", "architecture", None)
        assert "Output ONLY valid D2 code" in prompt


class TestCheckGhAvailable:
    """Tests for gh CLI availability check."""

    @patch("diagram_update.llm.shutil.which", return_value=None)
    def test_missing_gh_raises_tool_error(self, mock_which):
        with pytest.raises(ToolError, match="GitHub CLI is required"):
            _check_gh_available()

    @patch("diagram_update.llm.shutil.which", return_value="/usr/bin/gh")
    def test_gh_available_succeeds(self, mock_which):
        _check_gh_available()  # Should not raise


class TestCallGhCopilot:
    """Tests for subprocess invocation."""

    @patch("diagram_update.llm.subprocess.run")
    def test_constructs_correct_command(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="api: API", stderr=""
        )
        result = _call_gh_copilot("test prompt", "claude-opus-4-6")
        assert result == "api: API"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "gh"
        assert cmd[1] == "copilot"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "-s" in cmd
        assert "--model" in cmd
        assert "claude-opus-4-6" in cmd
        assert "--no-ask-user" in cmd

    @patch("diagram_update.llm.subprocess.run")
    def test_timeout_raises_llm_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=60)
        with pytest.raises(LLMError, match="timed out"):
            _call_gh_copilot("prompt", "model")

    @patch("diagram_update.llm.subprocess.run")
    def test_nonzero_exit_raises_llm_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="something failed"
        )
        with pytest.raises(LLMError, match="something failed"):
            _call_gh_copilot("prompt", "model")

    @patch("diagram_update.llm.subprocess.run")
    def test_auth_error_gives_helpful_message(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not authenticated"
        )
        with pytest.raises(LLMError, match="gh auth login"):
            _call_gh_copilot("prompt", "model")


class TestGenerateDiagram:
    """Tests for the full generate_diagram flow."""

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_returns_parsed_d2(self, mock_check, mock_call):
        mock_call.return_value = "```d2\napi: API\napi -> db\n```"
        result = generate_diagram("skeleton text")
        assert result == "api: API\napi -> db"

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_empty_response_raises(self, mock_check, mock_call):
        mock_call.return_value = ""
        with pytest.raises(LLMError, match="Empty response"):
            generate_diagram("skeleton text")

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_passes_model_parameter(self, mock_check, mock_call):
        mock_call.return_value = "api: API\napi -> db"
        generate_diagram("skeleton", model="gpt-4o")
        mock_call.assert_called_once_with(
            _build_prompt("skeleton", "architecture", None),
            "gpt-4o",
        )
