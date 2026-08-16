"""Tests for the offline matching backends.

None of these tests call an API. The behaviour they pin down is the part of
samplify that must be reproducible: same input, same groups, every time.
"""

from __future__ import annotations

import pytest

from samplify import matching


# ── Distances ──────────────────────────────────────────────────────────────


def test_hamming_counts_differing_positions():
    assert matching.hamming_distance("patient1", "patient2") == 1
    assert matching.hamming_distance("abc", "abc") == 0


def test_hamming_is_undefined_for_unequal_lengths():
    """None, not a number. A length-adjusted Hamming distance would mislead."""
    assert matching.hamming_distance("patient1", "patient11") is None


def test_levenshtein_counts_a_transposition_as_two():
    assert matching.levenshtein_distance("patient", "patietn") == 2


def test_damerau_counts_a_transposition_as_one():
    """One slip of the fingers is one edit, which is why damerau is the default."""
    assert matching.damerau_levenshtein_distance("patient", "patietn") == 1
    assert matching.damerau_levenshtein_distance("batch", "bacth") == 1


def test_damerau_still_counts_an_insertion():
    assert matching.damerau_levenshtein_distance("patient", "patients") == 1


def test_similarity_is_one_for_identical_strings():
    assert matching.similarity("abc", "abc") == 1.0


def test_similarity_scores_unequal_lengths_zero_under_hamming():
    assert matching.similarity("abc", "abcd", method="hamming") == 0.0


def test_similarity_rejects_an_unknown_method():
    with pytest.raises(ValueError, match="Unknown distance method"):
        matching.similarity("a", "b", method="jaro")


def test_default_distance_is_damerau():
    assert matching.DEFAULT_DISTANCE == "damerau"


# ── Identity ───────────────────────────────────────────────────────────────


def test_digit_signature_strips_zero_padding():
    assert matching.digit_signature("p111-batch03") == ("111", "3")


def test_digit_signature_is_empty_without_numbers():
    assert matching.digit_signature("control") == ()


def test_letter_skeleton_drops_digits_and_symbols():
    assert matching.letter_skeleton("Patient-111_BatchA") == "patientbatcha"


# ── Rule normalisation ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("S1_B1", "sample1_batch1"),
        ("s1-b1", "sample1_batch1"),
        ("s01_b01", "sample1_batch1"),
        ("P1_B1", "patient1_batch1"),
        ("#111_b2", "111_batch2"),
        ("CTRL_rep1_b1", "control_replicate1_batch1"),
        ("KO_rep2_B3", "knockout_replicate2_batch3"),
        ("sample007", "sample7"),
        ("patient1_batch1", "patient1_batch1"),
    ],
)
def test_rule_normalise(raw, expected):
    assert matching.rule_normalise(raw) == expected


def test_rule_normalise_is_idempotent():
    once = matching.rule_normalise("S01-B02")
    assert matching.rule_normalise(once) == once


# ── Grouping ───────────────────────────────────────────────────────────────


def test_rules_backend_merges_delimiter_and_case_variants():
    groups = matching.group_names(["S1_B1", "s1-b1", "s01_b01"], method="rules")
    assert groups == [["S1_B1", "s01_b01", "s1-b1"]]


def test_rules_backend_leaves_a_typo_alone():
    """A typo is not a delimiter problem, so the rules backend cannot see it."""
    groups = matching.group_names(
        ["patient1_batch1", "patietn1_batch1"], method="rules"
    )
    assert len(groups) == 2


def test_damerau_backend_merges_a_typo():
    groups = matching.group_names(
        ["patient1_batch1", "patietn1_batch1", "pateint1_batch1"], method="damerau"
    )
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_different_numbers_never_merge():
    """The guard that matters. p111 and p112 are one edit apart and two patients."""
    groups = matching.group_names(["p111_b1", "p112_b1"], method="damerau", threshold=0.5)
    assert len(groups) == 2


def test_different_numbers_never_merge_even_at_threshold_zero():
    groups = matching.group_names(["patient11_b1", "patient12_b1"], method="damerau", threshold=0.0)
    assert len(groups) == 2


def test_grouping_does_not_depend_on_input_order():
    names = ["s01_b01", "S1_B1", "s1-b1", "S2_B1"]
    forward = matching.group_names(names, method="damerau")
    backward = matching.group_names(list(reversed(names)), method="damerau")
    assert forward == backward


def test_group_names_rejects_the_llm_method():
    with pytest.raises(ValueError, match="Unknown offline method"):
        matching.group_names(["a"], method="llm")


# ── Near misses ────────────────────────────────────────────────────────────


def test_near_miss_reports_an_inserted_digit():
    pairs = matching.find_near_misses(["patient11_batch1", "patient111_batch1"])
    assert pairs == [("patient111_batch1", "patient11_batch1")]


def test_near_miss_ignores_a_substituted_digit():
    """Two consecutive sample numbers are not a typo, and reporting them buries the real ones."""
    assert matching.find_near_misses(["patient111_batch1", "patient112_batch1"]) == []


def test_near_miss_compares_components_separately():
    """patient11/batch2 against patient1/batch1 differs in both numbers, so it is not a slip."""
    assert matching.find_near_misses(["patient11_batch2", "patient1_batch1"]) == []


def test_near_miss_is_empty_on_a_clean_cohort():
    assert matching.find_near_misses(["S1_B1", "S2_B1", "S3_B1"]) == []


# ── Canonical name choice ──────────────────────────────────────────────────


def test_canonical_is_the_correct_spelling_when_every_form_appears_once():
    """The medoid. Each typo is one edit from the correct form and two from the others."""
    group = ["patient1_batch1", "patietn1_batch1", "pateint1_batch1", "patient1_bacth1"]
    assert matching.canonical_for_group(group) == "patient1_batch1"


def test_canonical_follows_the_row_count():
    group = ["patient1_batch1", "patietn1_batch1"]
    occurrences = {"patient1_batch1": 1, "patietn1_batch1": 50}
    assert matching.canonical_for_group(group, occurrences) == "patietn1_batch1"


def test_corpus_settles_a_two_name_group():
    """Two spellings give the medoid nothing, so the rest of the dataset decides."""
    dataset = [f"sample_{n}" for n in range(1, 12)] + ["sampel_5"]
    corpus = matching.skeleton_corpus(dataset)
    assert matching.canonical_for_group(["sample_5", "sampel_5"], None, corpus) == "sample5"


def test_without_a_corpus_a_two_name_group_has_no_signal():
    """Stated plainly: the tie-break needs the dataset, not the pair alone."""
    assert matching.canonical_for_group(["sample_5", "sampel_5"]) == "sampel5"


def test_canonical_of_one_name_is_its_normalised_form():
    assert matching.canonical_for_group(["S1_B1"]) == "sample1_batch1"


# ── The mislabelling catalogue ─────────────────────────────────────────────

#: One row per naming fault, as the reference spelling and the faulty one.
#: These are the same cases as example/mislabel_catalogue.csv.
CAUGHT = [
    ("delimiter dropped", "sample_1", "sample1"),
    ("delimiter changed", "sample_1", "sample-1"),
    ("capital letter", "sample_1", "Sample_1"),
    ("all capitals", "sample_4", "SAMPLE_4"),
    ("zero padded number", "sample_3", "sample_03"),
    ("doubled delimiter", "sample_6", "sample__6"),
    ("surrounding space", "sample_7", " sample_7 "),
    ("abbreviated word", "sample_8", "s_8"),
    ("one letter dropped", "sample_2", "smple_2"),
    ("two letters swapped", "sample_5", "sampel_5"),
]

#: Pairs that look alike and are two different samples.
KEPT_APART = [
    ("replicate letter", "sample_9a", "sample_9b"),
    ("a different number", "sample_11", "sample_12"),
    ("an added digit", "sample_10", "sample_100"),
]


@pytest.mark.parametrize("fault,reference,faulty", CAUGHT, ids=[c[0] for c in CAUGHT])
def test_catalogue_faults_are_caught(fault, reference, faulty):
    groups = matching.group_names([reference, faulty], method="damerau")
    assert groups == [sorted([reference, faulty])], fault


@pytest.mark.parametrize("case,left,right", KEPT_APART, ids=[c[0] for c in KEPT_APART])
def test_catalogue_pairs_stay_apart(case, left, right):
    groups = matching.group_names([left, right], method="damerau")
    assert len(groups) == 2, case


def test_a_replicate_letter_is_part_of_the_identity():
    """sample_9a and sample_9b differ by one substituted letter and are two samples."""
    assert matching.digit_signature("sample_9a") == ("9a",)
    assert matching.digit_signature("sample_9b") == ("9b",)


def test_a_replicate_letter_reads_as_a_different_identifier():
    """The letter after the number identifies the sample, so it is never a typo to fix."""
    assert matching.describe_difference("sample_9a", "sample_9b") == "different identifiers"


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("sample_1", "sample1", "formatting only"),
        ("sample_2", "smple_2", "insertion or deletion"),
        ("sample_5", "sampel_5", "transposition"),
        ("sample_9a", "sample_9b", "different identifiers"),
        ("sample_10", "sample_100", "different identifiers"),
        ("batch_a1", "batch_b1", "substitution"),
        ("sample_1", "sample_1", "identical"),
    ],
)
def test_describe_difference(left, right, expected):
    assert matching.describe_difference(left, right) == expected


def test_near_miss_is_quiet_inside_a_numbering_series():
    """In a cohort numbered 1 to 12, sample_1 and sample_10 are both ordinary members."""
    names = [f"sample_{n}" for n in range(1, 13)]
    assert matching.find_near_misses(names) == []


def test_near_miss_fires_outside_the_series():
    names = [f"sample_{n}" for n in range(1, 13)] + ["sample_100"]
    assert matching.find_near_misses(names) == [("sample_10", "sample_100")]


def test_canonical_does_not_depend_on_input_order():
    group = ["patient1_batch1", "patietn1_batch1", "pateint1_batch1"]
    assert matching.canonical_for_group(group) == matching.canonical_for_group(
        list(reversed(group))
    )
