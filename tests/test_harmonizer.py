"""
Tests for samplify harmonizer.

Live LLM tests are marked with @pytest.mark.live and skipped by default.
Run them with: pytest -m live
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from samplify.harmonizer import harmonize, _build_user_message


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
