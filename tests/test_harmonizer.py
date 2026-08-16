"""
Tests for samplify harmonizer.

Live LLM tests are marked with @pytest.mark.live and skipped by default.
Run them with: pytest -m live
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from samplify import rules
from samplify.harmonizer import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _build_user_message,
    build_system_prompt,
    harmonize,
    resolve_model,
)


# ── Unit tests (no API calls) ──────────────────────────────────────────────

def test_empty_input():
    result = harmonize([])
    assert result == {"canonical_pattern": "", "mapping": {}}


def test_user_message_format():
    msg = _build_user_message(["sample1-b1", "sample1_batch2"])
    assert "sample1-b1" in msg
    assert "sample1_batch2" in msg


def test_missing_name_fallback():
    """LLM response missing a name → original name preserved."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "canonical_pattern": "sample{n}_batch{m}",
        "mapping": {
            "sample1-b1": "sample1_batch1",
            # sample1_batch2 deliberately omitted to test fallback
        },
    })

    with patch("samplify.harmonizer.OpenAI") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = harmonize(
            ["sample1-b1", "sample1_batch2"],
            api_key="fake-key",
        )

    assert result["mapping"]["sample1-b1"] == "sample1_batch1"
    assert result["mapping"]["sample1_batch2"] == "sample1_batch2"  # fallback


def test_no_api_key_raises():
    import os
    env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="No API key"):
            harmonize(["sample1"], api_key=None)
    finally:
        if env_backup:
            os.environ["OPENROUTER_API_KEY"] = env_backup


# ── The request and the answer (no API calls) ──────────────────────────────

def _answer(payload, names=None, **kwargs):
    """Run harmonize against a mocked client that returns `payload`.

    Args:
        payload: The message content the fake model returns.
        names: The input names. Defaults to one name.
        **kwargs: Passed through to harmonize.

    Returns:
        A tuple of the harmonize result and the patched OpenAI class, so a
        test can inspect what was sent.
    """
    response = MagicMock()
    response.choices[0].message.content = payload

    with patch("samplify.harmonizer.OpenAI") as client_cls:
        client_cls.return_value.chat.completions.create.return_value = response
        result = harmonize(
            names if names is not None else ["sample1"], api_key="fake-key", **kwargs
        )
    return result, client_cls


def test_resolve_model_prefers_the_explicit_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "from/env")
    assert resolve_model("explicit/model") == "explicit/model"


def test_resolve_model_reads_the_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "from/env")
    assert resolve_model(None) == "from/env"


def test_resolve_model_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert resolve_model(None) == DEFAULT_MODEL


def test_the_request_goes_to_openrouter_with_the_chosen_model():
    _result, client_cls = _answer(
        json.dumps({"mapping": {"sample1": "sample1"}}), model="acme/model-1"
    )

    assert client_cls.call_args.kwargs["base_url"] == DEFAULT_BASE_URL
    assert client_cls.call_args.kwargs["api_key"] == "fake-key"

    request = client_cls.return_value.chat.completions.create.call_args.kwargs
    assert request["model"] == "acme/model-1"
    assert request["messages"][0]["role"] == "system"
    assert "sample1" in request["messages"][1]["content"]


def test_the_request_pins_temperature_zero_and_json():
    """docs/how_it_works.md claims both, and reproducibility depends on them."""
    _result, client_cls = _answer(json.dumps({"mapping": {"sample1": "sample1"}}))

    request = client_cls.return_value.chat.completions.create.call_args.kwargs
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}


def test_a_non_json_answer_raises():
    with pytest.raises(ValueError, match="did not return valid JSON"):
        _answer("Sorry, I cannot do that.")


def test_a_missing_answer_raises():
    """A refusal arrives as no content at all."""
    with pytest.raises(ValueError, match="did not return valid JSON"):
        _answer(None)


def test_json_without_a_mapping_key_raises():
    with pytest.raises(ValueError, match="without a 'mapping' key"):
        _answer(json.dumps({"canonical_pattern": "sampleN_batchN"}))


def test_json_that_is_not_an_object_raises():
    with pytest.raises(ValueError, match="not an object"):
        _answer(json.dumps(["sample1", "sample2"]))


def test_the_system_prompt_carries_the_number_rule_and_the_shared_table():
    prompt = build_system_prompt()
    assert "p111" in prompt
    assert "p112" in prompt
    assert rules.prompt_rules() in prompt


# ── Live tests (require real API key) ──────────────────────────────────────

@pytest.mark.live
def test_delimiter_variation():
    """Core use case: same sample, three delimiter styles."""
    names = ["sample_1_batch_1", "sample1_batch2", "sample-1-b3"]
    result = harmonize(names)

    mapping = result["mapping"]
    assert len(mapping) == 3

    # All canonical names should use underscores only
    for canonical in mapping.values():
        assert "-" not in canonical, f"Dash found in canonical name: {canonical}"

    # batch abbreviation should be expanded
    for canonical in mapping.values():
        assert "batch" in canonical, f"'batch' not expanded in: {canonical}"

    print("\nLive test result:")
    for orig, canon in mapping.items():
        print(f"  {orig!r:30s} → {canon!r}")


@pytest.mark.live
def test_mixed_abbreviations():
    """Replicate, control, knockout abbreviations."""
    names = [
        "ctrl_rep1_b1",
        "control_replicate2_batch1",
        "ctrl-r3-batch1",
        "ko_rep1_batch2",
        "knockout_replicate2_b2",
    ]
    result = harmonize(names)
    mapping = result["mapping"]
    assert len(mapping) == len(names)

    print("\nLive abbreviation test:")
    for orig, canon in mapping.items():
        print(f"  {orig!r:35s} → {canon!r}")


@pytest.mark.live
def test_zero_padding():
    """Zero-padded numbers should be normalised."""
    names = ["sample01_batch001", "sample1_batch1", "sample001_b1"]
    result = harmonize(names)
    mapping = result["mapping"]

    # All three should map to the same canonical form
    canonical_values = list(mapping.values())
    assert len(set(canonical_values)) == 1, (
        f"Expected all to map to same name, got: {canonical_values}"
    )
