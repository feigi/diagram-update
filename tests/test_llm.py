"""Tests for LLM client."""

from unittest.mock import patch, MagicMock, call
import subprocess

import pytest

from diagram_update.llm import (
    generate_diagram,
    _build_pass1_prompt,
    _build_pass2_prompt,
    _parse_response,
    _call_gh_copilot,
    _check_gh_available,
    _retry_generation,
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

    def test_strip_D2_uppercase_fence(self):
        raw = "```D2\napi: API\n```"
        assert _parse_response(raw) == "api: API"


class TestBuildPass1Prompt:
    """Tests for Pass 1 prompt construction (component identification)."""

    def test_contains_skeleton(self):
        prompt = _build_pass1_prompt("FILE TREE:\napp.py", "architecture")
        assert "FILE TREE:" in prompt
        assert "app.py" in prompt

    def test_contains_diagram_type(self):
        prompt = _build_pass1_prompt("skeleton", "dependencies")
        assert "dependencies" in prompt

    def test_architecture_focus(self):
        prompt = _build_pass1_prompt("skeleton", "architecture")
        assert "high-level services" in prompt

    def test_dependencies_focus(self):
        prompt = _build_pass1_prompt("skeleton", "dependencies")
        assert "package-level" in prompt

    def test_sequence_infers_entry_points(self):
        prompt = _build_pass1_prompt("skeleton", "sequence")
        assert "top 5" in prompt

    def test_sequence_uses_provided_entry_points(self):
        prompt = _build_pass1_prompt(
            "skeleton", "sequence",
            entry_points=["src/main.py:main", "src/api/app.py:create_app"],
        )
        assert "src/main.py:main" in prompt
        assert "src/api/app.py:create_app" in prompt
        assert "top 5" not in prompt

    def test_structured_output_format(self):
        prompt = _build_pass1_prompt("skeleton", "architecture")
        assert "COMPONENTS:" in prompt
        assert "RELATIONSHIPS:" in prompt
        assert "Output ONLY" in prompt


class TestBuildPass2Prompt:
    """Tests for Pass 2 prompt construction (D2 generation)."""

    def test_contains_components(self):
        components = "COMPONENTS:\n- id: api, label: API, type: service"
        prompt = _build_pass2_prompt(components, "architecture", None)
        assert "COMPONENTS:" in prompt
        assert "api" in prompt

    def test_d2_syntax_rules_included(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
        assert "D2 syntax rules" in prompt
        assert "Nodes:" in prompt
        assert "Connections:" in prompt

    def test_includes_existing_d2(self):
        existing = "api: API\napi -> db"
        prompt = _build_pass2_prompt("components", "architecture", existing)
        assert "api: API" in prompt
        assert "Preserve the structure" in prompt

    def test_no_existing_d2(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
        assert "Preserve the structure" not in prompt

    def test_sequence_diagram_instructions(self):
        prompt = _build_pass2_prompt("components", "sequence", None)
        assert "sequence_diagram" in prompt
        assert "actors" in prompt

    def test_non_sequence_no_sequence_instructions(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
        assert "sequence_diagram" not in prompt

    def test_ends_with_output_instruction(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
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


class TestRetryGeneration:
    """Tests for retry logic on empty/invalid D2 response."""

    @patch("diagram_update.llm._call_gh_copilot")
    def test_retry_returns_valid_d2(self, mock_call):
        mock_call.return_value = "api: API\napi -> db"
        result = _retry_generation("COMPONENTS:\n- id: api", "architecture", "model")
        assert "api: API" in result

    @patch("diagram_update.llm._call_gh_copilot")
    def test_retry_includes_error_context(self, mock_call):
        mock_call.return_value = "api: API"
        _retry_generation("components", "architecture", "model")
        prompt = mock_call.call_args[0][0]
        assert "previous attempt" in prompt.lower()
        assert "empty or invalid" in prompt.lower()

    @patch("diagram_update.llm._call_gh_copilot")
    def test_retry_sequence_mentions_shape(self, mock_call):
        mock_call.return_value = "flow: { shape: sequence_diagram }"
        _retry_generation("components", "sequence", "model")
        prompt = mock_call.call_args[0][0]
        assert "sequence_diagram" in prompt


class TestGenerateDiagram:
    """Tests for the full generate_diagram two-pass flow."""

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_two_pass_returns_d2(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 returns D2
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api, label: API, type: service\nRELATIONSHIPS:\n- api -> db: queries",
            "```d2\napi: API\ndb: Database\napi -> db: queries\n```",
        ]
        result = generate_diagram("skeleton text")
        assert result == "api: API\ndb: Database\napi -> db: queries"
        assert mock_call.call_count == 2

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_empty_pass1_raises(self, mock_check, mock_call):
        mock_call.return_value = ""
        with pytest.raises(LLMError, match="pass 1"):
            generate_diagram("skeleton text")

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_empty_pass2_triggers_retry(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 returns empty, retry returns D2
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "",
            "api: API\napi -> db",
        ]
        result = generate_diagram("skeleton text")
        assert "api: API" in result
        assert mock_call.call_count == 3  # pass1 + pass2 + retry

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_empty_pass2_and_retry_raises(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 empty, retry also empty
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "",
            "",
        ]
        with pytest.raises(LLMError, match="after retry"):
            generate_diagram("skeleton text")

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_passes_model_parameter(self, mock_check, mock_call):
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "api: API",
        ]
        generate_diagram("skeleton", model="gpt-4o")
        # Both pass 1 and pass 2 should use the specified model
        for c in mock_call.call_args_list:
            assert c[0][1] == "gpt-4o"

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_entry_points_passed_to_pass1(self, mock_check, mock_call):
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "api: API",
        ]
        generate_diagram(
            "skeleton",
            diagram_type="sequence",
            entry_points=["src/main.py:main"],
        )
        pass1_prompt = mock_call.call_args_list[0][0][0]
        assert "src/main.py:main" in pass1_prompt

    @patch("diagram_update.llm._call_gh_copilot")
    @patch("diagram_update.llm._check_gh_available")
    def test_sequence_diagram_type(self, mock_check, mock_call):
        mock_call.side_effect = [
            "COMPONENTS:\n- id: client",
            "flow: {\n  shape: sequence_diagram\n  client -> server\n}",
        ]
        result = generate_diagram("skeleton", diagram_type="sequence")
        assert "sequence_diagram" in result
