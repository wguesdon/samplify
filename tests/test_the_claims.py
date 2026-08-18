"""The claims the README makes, tested against the code.

A document is where a person learns what a tool guarantees, so a claim in it is
a promise. These tests read as the promises do, and each one fails if the code
stops honouring the sentence it quotes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from samplify import csv_processor, matching
from samplify.csv_processor import apply_mapping, propose_csv

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()


def test_the_readme_still_makes_these_claims():
    """If a sentence below is reworded, the test that quotes it must move too."""
    for sentence in (
        "samplify never merges two names with different numbers",
        "The command makes no model call",
        "the same output on any machine and on any day",
        "samplify does not change the\noriginal column",
    ):
        assert sentence in README, sentence


@pytest.mark.parametrize(
    "left,right",
    [
        ("patient11_batch1", "patient111_batch1"),
        ("p111", "p112"),
        ("sample_9a", "sample_9b"),
        ("sample_9α", "sample_9β"),
        ("OVTOKO_DOX+_br1", "OVTOKO_DOX-_br1"),
    ],
)
def test_samplify_never_merges_two_names_with_different_numbers(left, right):
    assert len(matching.group_names([left, right], method="damerau")) == 2


def test_apply_does_not_change_the_original_column(tmp_path):
    """Including the values that a CSV reader likes to reinterpret."""
    source = tmp_path / "in.csv"
    source.write_text('sample_id,other\n007,x\nNA,y\n"a,b",z\n')

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    output = tmp_path / "out.csv"
    apply_mapping(mapping, output_path=output)

    before = pd.read_csv(source, dtype=str, keep_default_na=False)
    after = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert list(after["sample_id"]) == list(before["sample_id"])
    assert list(after["other"]) == list(before["other"])


def test_apply_makes_no_model_call(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(csv_processor, "harmonize", lambda *a, **k: calls.append(1))

    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    apply_mapping(mapping, output_path=tmp_path / "out.csv")

    assert calls == []


def test_the_same_mapping_and_input_give_the_same_output(tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\nP3_B2\np3-b2\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    apply_mapping(mapping, output_path=first)
    apply_mapping(mapping, output_path=second)

    assert first.read_bytes() == second.read_bytes()
