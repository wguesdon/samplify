"""Tests for the shared normalisation rules.

None of these tests call an API. The rules module is the single source that the
prompt and the offline backends both read, so a change here is meant to show up
in both.
"""

from __future__ import annotations

from samplify import rules


def test_split_tokens_handles_every_delimiter():
    assert rules.split_tokens("Sample-1_batch.2 rep3") == ["sample", "1", "batch", "2", "rep3"]


def test_split_tokens_drops_empty_tokens():
    assert rules.split_tokens("__sample__1__") == ["sample", "1"]


def test_numbered_single_character_alias_needs_a_number():
    """A bare 'b' is too ambiguous to expand. 'b3' is not."""
    batch = next(a for a in rules.ABBREVIATIONS if a.canonical == "batch")
    assert batch.alias_regex("b") == r"b\d+"


def test_multi_character_alias_allows_no_number():
    replicate = next(a for a in rules.ABBREVIATIONS if a.canonical == "replicate")
    assert replicate.alias_regex("rep") == r"rep\d*"


def test_detect_abbreviations_finds_batch_and_control():
    found = rules.detect_abbreviations(["b1_ctrl_rep1", "b2_ctrl_rep2"])
    assert any("batch" in label for label in found)
    assert any("control" in label for label in found)
    assert any("replicate" in label for label in found)


def test_detect_abbreviations_finds_patient():
    """Version 0.1.0 could not expand p to patient, which a clinical cohort needs."""
    found = rules.detect_abbreviations(["p111_b1", "p112_b1"])
    assert any("patient" in label for label in found)


def test_detect_abbreviations_is_quiet_on_expanded_names():
    assert rules.detect_abbreviations(["patient1_batch1", "patient2_batch1"]) == []


def test_t_is_not_an_alias_for_treatment():
    """t1 reads as a timepoint at least as often as a treatment, so it is left alone."""
    aliases = {alias for abbrev in rules.ABBREVIATIONS for alias in abbrev.aliases}
    assert "t" not in aliases


def test_prompt_rules_names_every_expansion():
    text = rules.prompt_rules()
    for abbrev in rules.ABBREVIATIONS:
        assert abbrev.canonical in text


def test_prompt_rules_warns_against_a_wrong_expansion():
    assert "wrong expansion" in rules.prompt_rules()


def test_is_canonical():
    assert rules.is_canonical("patient1_batch2")
    assert not rules.is_canonical("Patient1_batch2")
    assert not rules.is_canonical("patient1-batch2")
    assert not rules.is_canonical("#111_a")
