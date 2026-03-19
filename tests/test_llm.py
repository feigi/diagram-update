"""Tests for LLM client."""

from unittest.mock import patch, MagicMock, call
import subprocess

import pytest

from diagram_update.llm import (
    generate_diagram,
    _build_pass1_prompt,
    _build_pass2_prompt,
    _parse_response,
    _call_copilot,
    _check_copilot_available,
    _retry_generation,
    _validate_d2,
    _extract_skeleton_edges,
    _extract_pass1_ids,
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

    def test_determinism_instructions(self):
        prompt = _build_pass1_prompt("skeleton", "architecture")
        assert "sorted alphabetically" in prompt
        assert "Determinism" in prompt


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
        assert "MUST reproduce it as closely" in prompt

    def test_no_existing_d2(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
        assert "MUST reproduce it as closely" not in prompt

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

    def test_determinism_rules(self):
        prompt = _build_pass2_prompt("components", "architecture", None)
        assert "DETERMINISM" in prompt
        assert "alphabetical order" in prompt
        assert "matching '}'" in prompt


class TestCheckCopilotAvailable:
    """Tests for Copilot CLI availability check."""

    @patch("diagram_update.llm.shutil.which", return_value=None)
    def test_missing_copilot_raises_tool_error(self, mock_which):
        with pytest.raises(ToolError, match="Copilot CLI is required"):
            _check_copilot_available()

    @patch("diagram_update.llm.shutil.which", return_value="/usr/local/bin/copilot")
    def test_copilot_available_succeeds(self, mock_which):
        _check_copilot_available()  # Should not raise


class TestCallCopilot:
    """Tests for subprocess invocation."""

    @patch("diagram_update.llm.subprocess.run")
    def test_constructs_correct_command(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="api: API", stderr=""
        )
        result = _call_copilot("test prompt", "claude-sonnet-4.6")
        assert result == "api: API"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "copilot"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "-s" in cmd
        assert "--model" in cmd
        assert "claude-sonnet-4.6" in cmd
        assert "--no-ask-user" in cmd
        assert "--no-custom-instructions" in cmd

    @patch("diagram_update.llm.subprocess.run")
    def test_timeout_raises_llm_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="copilot", timeout=300)
        with pytest.raises(LLMError, match="timed out"):
            _call_copilot("prompt", "model")

    @patch("diagram_update.llm.subprocess.run")
    def test_custom_timeout_is_passed_to_subprocess(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="a: A", stderr="")
        _call_copilot("prompt", "model", timeout=60)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 60

    @patch("diagram_update.llm.subprocess.run")
    def test_nonzero_exit_raises_llm_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="something failed"
        )
        with pytest.raises(LLMError, match="something failed"):
            _call_copilot("prompt", "model")

    @patch("diagram_update.llm.subprocess.run")
    def test_auth_error_gives_helpful_message(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not authenticated"
        )
        with pytest.raises(LLMError, match="copilot login"):
            _call_copilot("prompt", "model")


class TestRetryGeneration:
    """Tests for retry logic on empty/invalid D2 response."""

    @patch("diagram_update.llm._call_copilot")
    def test_retry_returns_valid_d2(self, mock_call):
        mock_call.return_value = "api: API\napi -> db"
        result = _retry_generation("COMPONENTS:\n- id: api", "architecture", "model")
        assert "api: API" in result

    @patch("diagram_update.llm._call_copilot")
    def test_retry_includes_error_context(self, mock_call):
        mock_call.return_value = "api: API"
        _retry_generation("components", "architecture", "model")
        prompt = mock_call.call_args[0][0]
        assert "previous attempt" in prompt.lower()
        assert "empty or invalid" in prompt.lower()

    @patch("diagram_update.llm._call_copilot")
    def test_retry_sequence_mentions_shape(self, mock_call):
        mock_call.return_value = "flow: { shape: sequence_diagram }"
        _retry_generation("components", "sequence", "model")
        prompt = mock_call.call_args[0][0]
        assert "sequence_diagram" in prompt


class TestGenerateDiagram:
    """Tests for the full generate_diagram two-pass flow."""

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_two_pass_returns_d2(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 returns D2
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api, label: API, type: service\nRELATIONSHIPS:\n- api -> db: queries",
            "```d2\napi: API\ndb: Database\napi -> db: queries\n```",
        ]
        result = generate_diagram("skeleton text")
        assert result == "api: API\ndb: Database\napi -> db: queries"
        assert mock_call.call_count == 2

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_empty_pass1_raises(self, mock_check, mock_call):
        mock_call.return_value = ""
        with pytest.raises(LLMError, match="pass 1"):
            generate_diagram("skeleton text")

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
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

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_empty_pass2_and_retry_raises(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 empty, retry also empty
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "",
            "",
        ]
        with pytest.raises(LLMError, match="after retry"):
            generate_diagram("skeleton text")

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_passes_model_parameter(self, mock_check, mock_call):
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "api: API",
        ]
        generate_diagram("skeleton", model="gpt-4o")
        # Both pass 1 and pass 2 should use the specified model
        for c in mock_call.call_args_list:
            assert c[0][1] == "gpt-4o"

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
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

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_sequence_diagram_type(self, mock_check, mock_call):
        mock_call.side_effect = [
            "COMPONENTS:\n- id: client",
            "flow: {\n  shape: sequence_diagram\n  client -> server\n}",
        ]
        result = generate_diagram("skeleton", diagram_type="sequence")
        assert "sequence_diagram" in result

    @patch("diagram_update.llm._call_copilot")
    @patch("diagram_update.llm._check_copilot_available")
    def test_d2_with_no_nodes_raises(self, mock_check, mock_call):
        # Pass 1 returns components, pass 2 returns only comments/empty lines
        mock_call.side_effect = [
            "COMPONENTS:\n- id: api",
            "# just a comment\n",
        ]
        with pytest.raises(LLMError, match="no nodes"):
            generate_diagram("skeleton text")


class TestValidateD2:
    """Tests for D2 output validation."""

    def test_valid_d2_passes(self):
        _validate_d2("api: API\ndb: Database\napi -> db: queries")

    def test_empty_nodes_raises(self):
        with pytest.raises(LLMError, match="no nodes"):
            _validate_d2("# just a comment")

    def test_nodes_only_warns_no_raise(self):
        # Nodes without edges is valid but should warn
        _validate_d2("api: API\ndb: Database")  # Should not raise

    def test_full_diagram_passes(self):
        d2 = "api: API {\n  handler: Handler\n}\ndb: Database\napi -> db: queries"
        _validate_d2(d2)  # Should not raise

    def test_skeleton_coverage_high(self):
        """Good D2 output that covers skeleton relationships should pass cleanly."""
        skeleton = "DEPENDENCIES:\napi -> db (x3)\nauth -> db"
        d2 = "api: API\ndb: Database\nauth: Auth\napi -> db: queries\nauth -> db: validates"
        _validate_d2(d2, skeleton=skeleton)  # Should not raise

    def test_skeleton_coverage_low_warns(self, caplog):
        """D2 output missing most skeleton relationships should log a warning."""
        import logging
        skeleton = "DEPENDENCIES:\napi -> db\nauth -> cache\nworker -> queue\nscheduler -> worker"
        d2 = "foo: Foo\nbar: Bar\nfoo -> bar: something"
        with caplog.at_level(logging.WARNING):
            _validate_d2(d2, skeleton=skeleton)
        assert "Low skeleton coverage" in caplog.text

    def test_unbalanced_braces_raises(self):
        """D2 with unbalanced braces should raise LLMError."""
        with pytest.raises(LLMError, match="unbalanced braces"):
            _validate_d2("api: API {\n  handler: Handler\n")

    def test_balanced_braces_passes(self):
        """D2 with balanced braces should pass."""
        _validate_d2("api: API {\n  handler: Handler\n}\ndb: DB\napi -> db")

    def test_skeleton_coverage_none_skipped(self):
        """No skeleton means no coverage check."""
        _validate_d2("api: API\napi -> db")  # Should not raise


class TestExtractPass1Ids:
    """Tests for pass 1 component ID extraction."""

    def test_extracts_standard_ids(self):
        text = (
            "COMPONENTS:\n"
            "- id: api, label: API, type: service\n"
            "- id: db, label: Database, type: database\n"
        )
        assert _extract_pass1_ids(text) == ["api", "db"]

    def test_empty_text_returns_empty(self):
        assert _extract_pass1_ids("some random text") == []

    def test_strips_trailing_commas(self):
        text = "- id: api, label: API\n- id: db, label: DB\n"
        assert _extract_pass1_ids(text) == ["api", "db"]

    def test_dotted_ids(self):
        text = "- id: src.auth.handler, label: Auth Handler, type: module\n"
        assert _extract_pass1_ids(text) == ["src.auth.handler"]


class TestExtractSkeletonEdges:
    """Tests for skeleton DEPENDENCIES parsing."""

    def test_extracts_basic_edges(self):
        skeleton = "FILE TREE:\napp.py\n\nDEPENDENCIES:\napi -> db\nauth -> cache"
        edges = _extract_skeleton_edges(skeleton)
        assert ("api", "db") in edges
        assert ("auth", "cache") in edges

    def test_handles_weight_annotations(self):
        skeleton = "DEPENDENCIES:\nsrc/api -> src/db (x3)"
        edges = _extract_skeleton_edges(skeleton)
        assert ("src.api", "src.db") in edges

    def test_empty_skeleton_returns_empty(self):
        assert _extract_skeleton_edges("FILE TREE:\napp.py") == []

    def test_extracts_full_dotted_paths(self):
        skeleton = "DEPENDENCIES:\nsrc/auth/handler -> src/db/models"
        edges = _extract_skeleton_edges(skeleton)
        assert ("src.auth.handler", "src.db.models") in edges
