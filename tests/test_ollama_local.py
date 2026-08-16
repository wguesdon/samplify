"""End to end tests against a real ollama server on this machine.

These tests are deselected by default, because they need a running server.
Run them with:

    ollama serve
    ollama pull qwen3.5:9b
    uv run pytest -m local

They check what samplify guarantees, not what the model prefers. A local model
is free to propose a wrong merge, and the identity rule has to refuse it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from samplify.csv_processor import propose_csv
from samplify.harmonizer import DEFAULT_OLLAMA_MODEL

pytestmark = pytest.mark.local

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example"


def test_local_ollama_merges_the_delimiter_variants():
    """S1_B1, s1-b1 and s01_b01 are one sample, whatever the model calls it."""
    mapping = propose_csv(
        EXAMPLE_DIR / "delimiter_case.csv", "sample_id", method="auto", provider="ollama"
    )

    groups = [set(group.members) for group in mapping.groups]
    assert {"S1_B1", "s1-b1", "s01_b01"} in groups


def test_local_ollama_records_the_provider_and_the_model():
    mapping = propose_csv(
        EXAMPLE_DIR / "delimiter_case.csv", "sample_id", method="auto", provider="ollama"
    )

    assert mapping.provider == "ollama"
    assert mapping.model == DEFAULT_OLLAMA_MODEL


def test_local_ollama_never_mixes_two_samples():
    """The catalogue carries its own answer, so the merge can be checked.

    A group that holds two different true samples is a lost row at the apply
    step. The identity rule has to hold over whatever the local model returns.
    """
    truth = pd.read_csv(EXAMPLE_DIR / "mislabel_catalogue.csv")
    expected = dict(zip(truth["sample_id"], truth["true_sample"]))

    mapping = propose_csv(
        EXAMPLE_DIR / "mislabel_catalogue.csv",
        "sample_id",
        method="auto",
        provider="ollama",
    )

    for group in mapping.groups:
        truths = {expected[member] for member in group.members}
        assert len(truths) == 1, f"group {group.id} mixes {truths}"
