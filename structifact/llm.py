"""
LLM client abstraction for AI-assisted discovery.

Structifact's deterministic core (adapters, validation, generators,
and the base `structifact discover` command) never imports this
module and never makes a network call. This module exists solely for
the optional, explicitly opt-in AI-assisted halves of
`structifact discover --ai` (raw-data field descriptions and
requirements-document extraction).

Design: LLMClient is a small interface, not tied to any one provider.
Only an Anthropic implementation ships today, since that's the only
one anyone has asked for — but nothing here is Anthropic-specific by
design. Someone using a different provider (OpenAI, etc.) could
implement this same interface with their own client rather than being
locked out of AI-assisted discovery entirely.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CostEstimate:
    estimated_input_tokens: int
    estimated_output_tokens: int
    note: str


class LLMClient(ABC):
    """
    Any provider implementing this interface can be used with
    `structifact discover --ai`. Implementations decide how to talk
    to their own provider; callers only depend on this interface.
    """

    @abstractmethod
    def estimate_cost(self, prompt: str) -> CostEstimate:
        """Called BEFORE any real request, so the user can see an
        estimate and decide whether to proceed. Must not make a
        network call itself."""
        raise NotImplementedError

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Makes the actual request with an arbitrary prompt. Only
        called after the user has explicitly confirmed (or passed
        -y). Provider implementations only need to implement this one
        generic method — everything Structifact asks an LLM to do
        (raw-data field descriptions, requirements-doc extraction,
        anything added later) is just a different prompt over the
        same call, not a new method per use case."""
        raise NotImplementedError

    def suggest_field_descriptions(self, prompt: str) -> str:
        """
        Kept as a named, self-documenting entry point for the
        raw-data discovery path (and for backward compatibility with
        existing call sites). Just delegates to complete() — provider
        implementations do not need to override this separately.
        """
        return self.complete(prompt)


class FakeLLMClient(LLMClient):
    """
    Test/development double. Makes no network calls, costs nothing,
    and records what it was asked so tests can assert on it.
    """

    def __init__(self, canned_response: str = ""):
        self.canned_response = canned_response
        self.prompts_received = []

    def estimate_cost(self, prompt: str) -> CostEstimate:
        return CostEstimate(
            estimated_input_tokens=len(prompt) // 4,
            estimated_output_tokens=0,
            note="fake client — no real cost",
        )

    def complete(self, prompt: str) -> str:
        self.prompts_received.append(prompt)
        return self.canned_response


class AnthropicLLMClient(LLMClient):
    """
    Real implementation using the Anthropic API. Requires the
    `anthropic` package (only imported lazily, when an actual request
    is made — constructing this class and calling estimate_cost()
    never requires the package to be installed) and an API key.

    The API key is never hardcoded: it comes from an explicit
    constructor argument or the ANTHROPIC_API_KEY environment
    variable. This is a deliberate "bring your own key" design — each
    user pays for their own usage. That's not just good practice for
    a personal project; it's also the correct architecture if this
    were ever used by more than one person, since no one's key should
    ever pay for someone else's usage.
    """

    MODEL = "claude-haiku-4-5"  # fastest/cheapest — appropriate for this task

    # Rough, approximate rates for cost ESTIMATION ONLY. These are not
    # guaranteed current — verify real pricing at
    # console.anthropic.com/pricing before relying on this number.
    _APPROX_INPUT_COST_PER_MTOK = 1.0
    _APPROX_OUTPUT_COST_PER_MTOK = 5.0
    # This caps BOTH the cost estimate shown before confirmation AND
    # the real API request's max_tokens — so it's not just a display
    # number, it's a hard ceiling on how long a real response can be.
    # 500 truncated a real response for a requirements-document
    # extraction with ~20 fields; 4000 ALSO truncated one on a
    # different run of the same document, purely from normal
    # run-to-run output-length variance — a fixed cap can't fully
    # eliminate this risk, only push the odds down. Raised again with
    # real headroom; the marginal cost of an unused higher ceiling
    # remains negligible (well under a cent at Haiku's output
    # pricing) next to the cost of another truncated, unusable
    # response. complete() also now surfaces stop_reason ==
    # "max_tokens" explicitly if this cap is ever hit again.
    _APPROX_OUTPUT_TOKEN_CAP = 8000

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise RuntimeError(
                "No Anthropic API key found. Set the ANTHROPIC_API_KEY "
                "environment variable, or pass one explicitly. Get a key "
                "at https://console.anthropic.com — this is separate from "
                "a claude.ai chat subscription."
            )

    def estimate_cost(self, prompt: str) -> CostEstimate:
        # Rough heuristic (~4 characters per token) — good enough for
        # a "should I proceed" decision, not a precise bill.
        est_input = max(1, len(prompt) // 4)
        est_output = self._APPROX_OUTPUT_TOKEN_CAP

        approx_dollars = (
            est_input / 1_000_000 * self._APPROX_INPUT_COST_PER_MTOK
            + est_output / 1_000_000 * self._APPROX_OUTPUT_COST_PER_MTOK
        )

        return CostEstimate(
            estimated_input_tokens=est_input,
            estimated_output_tokens=est_output,
            note=(
                f"~${approx_dollars:.4f} estimated (rough approximation — "
                f"verify current pricing at console.anthropic.com/pricing)"
            ),
        )

    def complete(self, prompt: str) -> str:
        import anthropic  # lazy import: only required if this path runs

        client = anthropic.Anthropic(api_key=self.api_key)

        response = client.messages.create(
            model=self.MODEL,
            max_tokens=self._APPROX_OUTPUT_TOKEN_CAP,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.stop_reason == "max_tokens":
            # Authoritative, not a guess: the API itself is telling us
            # the response was cut off before the model finished, not
            # inferred indirectly from e.g. a downstream YAML parse
            # failure on an unclosed code fence. Surfacing this
            # directly, at the source, is far more actionable than
            # letting the caller puzzle out a generic parse error.
            print(
                f"\nWarning: the AI response was cut off after hitting "
                f"the {self._APPROX_OUTPUT_TOKEN_CAP}-token output "
                f"limit before finishing — the output below is "
                f"incomplete, not just possibly malformed."
            )

        return response.content[0].text
