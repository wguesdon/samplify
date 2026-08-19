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


@pytest.mark.parametrize(
    "names,label",
    [
        (["Th1", "Th17"], "two T helper subsets"),
        (["MSI-1", "MSI-13"], "two samples of one series"),
        (["human cTEC5", "human mTEC5"], "cortical against medullary"),
        (["Primary B cells", "Primary T cells"], "two lymphocyte lineages"),
        (["exp1-d4", "exp1-d14"], "day 4 against day 14"),
    ],
)
def test_a_pair_that_needs_a_person_is_kept_apart_and_reported(names, label):
    """Keeping two samples apart is half of the promise. Saying so is the other
    half, because a pair nobody sees is a pair nobody decides.

    Every one of these comes from the ENA archive.
    """
    assert len(matching.group_names(names, method="damerau")) == 2, label
    reported = matching.find_near_misses(names) + matching.find_letter_variants(names)
    assert reported, label


def test_a_blank_line_is_a_row_and_survives(tmp_path):
    """pandas drops an empty line by default, and that line is a row.

    The output then held fewer rows than the input, which is the one thing this
    tool must never do.
    """
    source = tmp_path / "in.csv"
    source.write_text("sample_id,n\nsample_1,1\n\nsample_2,3\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    output = tmp_path / "out.csv"
    frame, log = apply_mapping(mapping, output_path=output)

    assert len(frame) == 3
    assert log["summary"]["total_rows"] == 3

    written = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert list(written["sample_id"]) == ["sample_1", "", "sample_2"]
    assert list(written["n"]) == ["1", "", "3"]


@pytest.mark.parametrize(
    "content,rows",
    [
        ("sample_id\nsample_1\n\nsample_2\n", 3),
        ("sample_id\n\n\n", 2),
        ("sample_id\nsample_1\n   \nsample_2\n", 3),
        ("sample_id\nsample_1\n", 1),
    ],
)
def test_the_output_holds_one_row_for_each_input_row(tmp_path, content, rows):
    source = tmp_path / "in.csv"
    source.write_text(content)

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    frame, _ = apply_mapping(mapping)
    assert len(frame) == rows
