import argparse
import io
import contextlib
from unittest.mock import patch, Mock

import pytest

from structifact.discover import (
    discover_csv, render_draft_yaml, build_ai_prompt, parse_ai_suggestions,
)
from structifact.llm import FakeLLMClient, AnthropicLLMClient, CostEstimate
from structifact.cli import discover as discover_cmd


# --- build_ai_prompt ---

def test_build_ai_prompt_includes_dataset_name_and_fields():
    discovered = discover_csv("tests/fixtures/raw_customers.csv")
    prompt = build_ai_prompt(discovered)

    assert "raw_customers" in prompt
    assert "customer_id" in prompt
    assert "email" in prompt
    assert "inferred type" in prompt


# --- parse_ai_suggestions ---

def test_parse_ai_suggestions_well_formed():
    raw = "customer_id: Unique identifier for the customer\nemail: Customer's email address"
    result = parse_ai_suggestions(raw)

    assert result == {
        "customer_id": "Unique identifier for the customer",
        "email": "Customer's email address",
    }


def test_parse_ai_suggestions_skips_malformed_lines():
    raw = "customer_id: A real description\nthis line has no colon\n\nemail:"
    result = parse_ai_suggestions(raw)

    # "email:" has no description after the colon, should be skipped
    assert result == {"customer_id": "A real description"}


def test_parse_ai_suggestions_strips_leading_dash():
    raw = "- customer_id: Some description"
    result = parse_ai_suggestions(raw)

    assert result == {"customer_id": "Some description"}


# --- render_draft_yaml with AI suggestions ---

def test_render_draft_yaml_without_ai_suggestions_unchanged():
    # regression: must behave exactly as before when ai_suggestions
    # is None — this is the default, most common path
    discovered = discover_csv("tests/fixtures/raw_customers.csv")

    without_arg = render_draft_yaml(discovered)
    with_none = render_draft_yaml(discovered, ai_suggestions=None)

    assert without_arg == with_none
    assert "AI-suggested" not in without_arg


def test_render_draft_yaml_with_ai_suggestions_marks_them_clearly():
    discovered = discover_csv("tests/fixtures/raw_customers.csv")
    suggestions = {"customer_id": "Unique customer identifier"}

    rendered = render_draft_yaml(discovered, ai_suggestions=suggestions)

    assert 'description: "Unique customer identifier"  # AI-suggested, review before trusting' in rendered

    # strip comment markers before joining lines, so this reads the
    # disclaimer as prose rather than tripping over the leading "#"
    # on each line
    header_prose = " ".join(
        line.lstrip("#").strip() for line in rendered.splitlines()
    )
    assert "has not seen your actual data values" in header_prose


def test_render_draft_yaml_fields_without_suggestion_stay_todo():
    discovered = discover_csv("tests/fixtures/raw_customers.csv")
    # only suggest for one field
    suggestions = {"customer_id": "Unique customer identifier"}

    rendered = render_draft_yaml(discovered, ai_suggestions=suggestions)

    # email got no suggestion, should still show TODO
    email_section = rendered.split("name: email")[1].split("name:")[0]
    assert "TODO" in email_section


# --- FakeLLMClient ---

def test_fake_llm_client_returns_canned_response_and_records_prompt():
    client = FakeLLMClient(canned_response="customer_id: A fake description")

    result = client.suggest_field_descriptions("some prompt")

    assert result == "customer_id: A fake description"
    assert client.prompts_received == ["some prompt"]


def test_fake_llm_client_estimate_cost_no_network():
    client = FakeLLMClient()
    estimate = client.estimate_cost("a" * 400)

    assert isinstance(estimate, CostEstimate)
    assert estimate.estimated_input_tokens == 100
    assert "no real cost" in estimate.note


# --- AnthropicLLMClient: error path only, never a real call ---

def test_anthropic_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="No Anthropic API key found"):
        AnthropicLLMClient()


def test_anthropic_client_accepts_explicit_key_no_network():
    # constructing the client and estimating cost never makes a
    # network call or requires the anthropic package to be installed
    client = AnthropicLLMClient(api_key="fake-key-for-testing")
    estimate = client.estimate_cost("some prompt text")

    assert isinstance(estimate, CostEstimate)
    assert "console.anthropic.com/pricing" in estimate.note


def test_anthropic_client_reads_key_from_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-for-testing")

    client = AnthropicLLMClient()

    assert client.api_key == "env-key-for-testing"


# --- AnthropicLLMClient.complete(): mocked network, real response-parsing ---
#
# Regression coverage for a real bug: claude-sonnet-5 can return a leading
# ThinkingBlock (no .text attribute) ahead of the actual answer, and
# complete() used to unconditionally return response.content[0].text --
# crashing with AttributeError whenever that happened (see
# DECISION_HISTORY.md's override-merge characterization entry). These mock
# the Anthropic SDK boundary so the fix is verified without a real call.

class _FakeBlock:
    def __init__(self, block_type, **attrs):
        self.type = block_type
        for k, v in attrs.items():
            setattr(self, k, v)


class _FakeFinalMessage:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessageStream:
    """Mimics the `with client.messages.stream(...) as stream:` context
    manager -- just enough of it for complete() to drive."""

    def __init__(self, text_chunks, final_message):
        self._text_chunks = text_chunks
        self._final_message = final_message

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    @property
    def text_stream(self):
        return iter(self._text_chunks)

    def get_final_message(self):
        return self._final_message


def _client_with_fake_stream(final_message, text_chunks=("",)):
    client = AnthropicLLMClient(api_key="fake-key-for-testing")
    fake_anthropic_client = Mock()
    fake_anthropic_client.messages.stream.return_value = _FakeMessageStream(
        text_chunks, final_message
    )
    return client, fake_anthropic_client


def test_complete_extracts_text_block_after_leading_thinking_block():
    # The exact real-world shape: a ThinkingBlock ahead of the TextBlock.
    # Must not raise AttributeError, and must return the real text block's
    # content, not the thinking block's.
    final_message = _FakeFinalMessage(content=[
        _FakeBlock("thinking", thinking="internal reasoning, not the answer"),
        _FakeBlock("text", text='dataset: "orders"\nfields: []\nunresolved_notes: []\n'),
    ])
    client, fake_anthropic_client = _client_with_fake_stream(final_message)

    with patch("anthropic.Anthropic", return_value=fake_anthropic_client):
        result = client.complete("some prompt")

    assert result == 'dataset: "orders"\nfields: []\nunresolved_notes: []\n'


def test_complete_returns_empty_string_when_only_thinking_returned():
    # Regression for the historical symptom this bug produced: a response
    # that never got past thinking (budget exhausted first) must come back
    # as "" -- not crash, and not fabricate text from the thinking block.
    final_message = _FakeFinalMessage(
        content=[_FakeBlock("thinking", thinking="ran out of budget here")],
        stop_reason="max_tokens",
    )
    client, fake_anthropic_client = _client_with_fake_stream(final_message)

    with patch("anthropic.Anthropic", return_value=fake_anthropic_client):
        result = client.complete("some prompt")

    assert result == ""


def test_complete_handles_plain_single_text_block_unchanged():
    # The common case (no thinking block at all) must keep working exactly
    # as before -- this isn't a thinking-specific rewrite, just no longer
    # assuming position 0.
    final_message = _FakeFinalMessage(content=[
        _FakeBlock("text", text="plain response, no thinking block"),
    ])
    client, fake_anthropic_client = _client_with_fake_stream(final_message)

    with patch("anthropic.Anthropic", return_value=fake_anthropic_client):
        result = client.complete("some prompt")

    assert result == "plain response, no thinking block"


# --- CLI: --ai off by default ---

def test_discover_cli_default_never_touches_ai(tmp_path, capsys):
    args = argparse.Namespace(
        spec="tests/fixtures/raw_customers.csv",
        output=str(tmp_path / "out.yml"),
        sample_size=100,
        ai=False,
        yes=False,
    )

    discover_cmd(args)  # no ai_client passed — must never be needed

    out = capsys.readouterr().out
    assert "AI-assisted" not in out
    assert "AI-suggested" not in (tmp_path / "out.yml").read_text()


# --- CLI: --ai with -y (skip confirmation) ---

def test_discover_cli_ai_with_yes_flag_uses_fake_client(tmp_path, capsys):
    fake = FakeLLMClient(canned_response="customer_id: A suggested description")

    args = argparse.Namespace(
        spec="tests/fixtures/raw_customers.csv",
        output=str(tmp_path / "out.yml"),
        sample_size=100,
        ai=True,
        yes=True,
    )

    discover_cmd(args, ai_client=fake)

    out = capsys.readouterr().out
    assert "Estimate:" in out
    assert len(fake.prompts_received) == 1  # the request was actually made

    written = (tmp_path / "out.yml").read_text()
    assert '"A suggested description"  # AI-suggested' in written


# --- CLI: --ai without -y, interactive confirmation ---

def test_discover_cli_ai_confirmed_interactively(tmp_path, capsys):
    fake = FakeLLMClient(canned_response="customer_id: A confirmed description")

    args = argparse.Namespace(
        spec="tests/fixtures/raw_customers.csv",
        output=str(tmp_path / "out.yml"),
        sample_size=100,
        ai=True,
        yes=False,
    )

    with patch("builtins.input", return_value="y"):
        discover_cmd(args, ai_client=fake)

    assert len(fake.prompts_received) == 1
    written = (tmp_path / "out.yml").read_text()
    assert "A confirmed description" in written


def test_discover_cli_ai_declined_interactively_makes_no_request(tmp_path, capsys):
    fake = FakeLLMClient(canned_response="customer_id: Should never appear")

    args = argparse.Namespace(
        spec="tests/fixtures/raw_customers.csv",
        output=str(tmp_path / "out.yml"),
        sample_size=100,
        ai=True,
        yes=False,
    )

    with patch("builtins.input", return_value="n"):
        discover_cmd(args, ai_client=fake)

    out = capsys.readouterr().out
    assert "Skipped" in out
    assert len(fake.prompts_received) == 0  # the critical assertion: no request made

    written = (tmp_path / "out.yml").read_text()
    assert "Should never appear" not in written
    assert "TODO" in written  # fell back to the deterministic draft
