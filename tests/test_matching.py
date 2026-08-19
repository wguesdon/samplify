"""Tests for the offline matching backends.

None of these tests call an API. The behaviour they pin down is the part of
samplify that must be reproducible: same input, same groups, every time.
"""

from __future__ import annotations

import pytest

from samplify import matching, rules


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


# ── The review findings of 2026-08-18 ──────────────────────────────────────


def test_a_letter_before_a_digit_is_not_an_identity_suffix():
    """p1b1 and p1_b1 are one sample written two ways.

    The b of p1b1 introduces the next number. Reading it as a replicate letter
    gave the compact form the signature ('1b', '1') and the delimited form the
    signature ('1', '1'), so the two never reached the same block.
    """
    assert matching.digit_signature("p1b1") == ("1", "1")
    assert matching.digit_signature("p1_b1") == ("1", "1")
    assert matching.group_names(["p1b1", "p1_b1"], method="damerau") == [
        ["p1_b1", "p1b1"]
    ]


def test_a_replicate_letter_at_the_end_stays_in_the_signature():
    assert matching.digit_signature("sample_9a") == ("9a",)
    assert matching.digit_signature("sample_9b") == ("9b",)
    assert matching.group_names(["sample_9a", "sample_9b"], method="damerau") == [
        ["sample_9a"],
        ["sample_9b"],
    ]


def test_a_replicate_letter_in_another_script_keeps_two_samples_apart():
    """The identity rule works on a letter, not on an ASCII letter."""
    assert matching.digit_signature("sample_9α") == ("9α",)
    assert matching.digit_signature("sample_9β") == ("9β",)
    assert matching.group_names(["sample_9α", "sample_9β"], method="damerau") == [
        ["sample_9α"],
        ["sample_9β"],
    ]


def test_two_names_in_another_script_do_not_normalise_to_the_same_string():
    """Dropping every non-ASCII letter left only the number behind."""
    assert matching.rule_normalise("Пациент_1") == "пациент1"
    assert matching.rule_normalise("Δείγμα_1") == "δείγμα1"
    assert matching.group_names(["Пациент_1", "Δείγμα_1"], method="damerau") == [
        ["Δείγμα_1"],
        ["Пациент_1"],
    ]


def test_a_short_name_needs_the_ratio_for_one_inserted_letter():
    """wt is wildtype and wnt is a gene family, and one letter separates them."""
    assert matching.group_names(["wt_1", "wnt_1"], method="damerau") == [
        ["wnt_1"],
        ["wt_1"],
    ]
    assert matching.group_names(["t_1", "tp_1"], method="damerau") == [
        ["t_1"],
        ["tp_1"],
    ]
    assert matching.group_names(["k_1", "ko_1"], method="damerau") == [
        ["k_1"],
        ["ko_1"],
    ]


def test_a_long_name_still_matches_on_one_dropped_letter():
    """The rule that finds a real typing error is unchanged above the limit."""
    assert matching.group_names(["smple_1", "sample_1"], method="damerau") == [
        ["sample_1", "smple_1"]
    ]
    assert matching.group_names(["sampel_5", "sample_5"], method="damerau") == [
        ["sampel_5", "sample_5"]
    ]


def test_two_names_without_a_letter_do_not_match():
    """Two empty letter skeletons score 1.0 against each other."""
    assert matching.group_names(["###", "$$$"], method="damerau") == [["###"], ["$$$"]]
    assert matching.group_names(["###", "$$$"], method="rules") == [["###"], ["$$$"]]


def test_group_names_refuses_a_threshold_outside_the_ratio():
    for value in (-0.1, 1.5):
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            matching.group_names(["a_1"], method="damerau", threshold=value)


def test_the_canonical_name_of_an_unnormalisable_group_is_the_raw_name():
    """An empty canonical name would rename the sample to nothing."""
    assert matching.canonical_for_group(["###"]) == "###"


# ── The indexed near-miss search ───────────────────────────────────────────


def test_near_miss_reads_the_middle_component_of_a_signature():
    """The index keys on every other component, so any position must work.

    The pair is sorted, and the underscore sorts after every digit, so the
    longer number comes first.
    """
    names = ["donor2_plate11_well3", "donor2_plate111_well3"]
    assert matching.find_near_misses(names) == [
        ("donor2_plate111_well3", "donor2_plate11_well3")
    ]


def test_near_miss_needs_every_other_component_to_agree():
    names = ["donor2_plate11_well3", "donor9_plate111_well3"]
    assert matching.find_near_misses(names) == []


def test_near_miss_pairs_every_spelling_of_the_two_names():
    """Several spellings of one sample all reach the report."""
    names = ["patient11_batch1", "PATIENT11-BATCH1", "patient111_batch1"]
    assert matching.find_near_misses(names) == [
        ("PATIENT11-BATCH1", "patient111_batch1"),
        ("patient111_batch1", "patient11_batch1"),
    ]


def test_a_dropped_replicate_letter_is_not_a_near_miss():
    """The letter belongs to the skeleton, so the two names never meet.

    `sample_9` and `sample_9a` have the skeletons `sample` and `samplea`. The
    identity rule keeps them apart, which is correct, and the near-miss search
    groups by skeleton, so it never sees the pair. A dropped replicate letter
    therefore reaches no report. This test records the behaviour and not an
    approval of it.
    """
    assert matching.find_near_misses(["sample_9", "sample_9a"]) == []


def test_near_miss_stays_fast_on_a_cohort_of_one_convention():
    """A cohort written to one convention holds every name in one skeleton.

    The pairwise search read 19 million pairs there and took 34 seconds. The
    bound below is far above the indexed cost and far below the pairwise one,
    so it fails only if the search becomes quadratic again.
    """
    import time

    names = [f"patient{i}_batch{(i % 12) + 1}" for i in range(1, 6001)]
    start = time.perf_counter()
    pairs = matching.find_near_misses(names)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"the near-miss search took {elapsed:.1f} s"
    # Every number from 1 to 6000 has a neighbour in the series, so each one is
    # an ordinary member of it and the report stays empty.
    assert pairs == []


def test_near_miss_fires_at_scale_where_the_series_has_a_gap():
    """The same cohort with one number far outside the series reports it."""
    names = [f"patient{i}_batch1" for i in range(1, 3001)]
    names.append("patient29999_batch1")
    names.append("patient2999_batch1")

    assert ("patient29999_batch1", "patient2999_batch1") in matching.find_near_misses(names)


# ── The edit cap, from the validation on real ENA data ─────────────────────


def test_two_edits_do_not_merge_however_long_the_name():
    """EVT and ST are two cell types, and the ratio let them merge.

    The pair scores 0.857 because the two names share sixteen characters. The
    three that differ carry the whole identity. This pair comes from PRJDB12972
    of the ENA archive.
    """
    names = ["EVT-TS-1_paired-RNA", "ST-TS-1_paired-RNA"]
    assert matching.similarity(
        matching.letter_skeleton(names[0]), matching.letter_skeleton(names[1])
    ) > 0.85
    assert matching.group_names(names, method="damerau") == [
        ["EVT-TS-1_paired-RNA"],
        ["ST-TS-1_paired-RNA"],
    ]


def test_a_long_shared_context_does_not_carry_a_merge():
    """SK-N-SH and TGW are two cell lines, and the sentence around them agreed.

    This pair comes from PRJDB14234 and scores 0.889 over five edits.
    """
    names = [
        "Mock_SKNSH transcriptome after vector transfection",
        "Mock_TGW transcriptome after vector transfection",
    ]
    assert matching.group_names(names, method="damerau") == [
        ["Mock_SKNSH transcriptome after vector transfection"],
        ["Mock_TGW transcriptome after vector transfection"],
    ]


def test_one_edit_still_merges_at_every_length():
    """The cap keeps every real typing error that the corpus held."""
    for pair in (
        ["smple_1", "sample_1"],
        ["sampel_5", "sample_5"],
        ["patietn1_batch1", "patient1_batch1"],
    ):
        assert len(matching.group_names(pair, method="damerau")) == 1, pair


# ── The banded distance ────────────────────────────────────────────────────


def test_the_banded_distance_is_exact_at_or_below_the_cap():
    for a, b, distance in (
        ("patient", "patient", 0),
        ("patient", "patietn", 1),
        ("sample", "smple", 1),
        ("batcha", "batchb", 1),
    ):
        assert matching.damerau_levenshtein_distance(a, b, max_distance=2) == distance


def test_the_banded_distance_reports_one_above_the_cap():
    """A caller that asked about one edit learns only that there are more."""
    assert matching.damerau_levenshtein_distance("abcdef", "uvwxyz", max_distance=1) == 2
    assert matching.damerau_levenshtein_distance("abcdef", "uvwxyz", max_distance=3) == 4
    assert matching.damerau_levenshtein_distance("abcdef", "uvwxyz") == 6


def test_the_banded_distance_agrees_with_the_full_grid():
    """Random strings, every cap from zero to four, against the whole grid."""
    import random

    random.seed(11)
    for _ in range(400):
        a = "".join(random.choice("abcdef") for _ in range(random.randint(0, 10)))
        b = "".join(random.choice("abcdef") for _ in range(random.randint(0, 10)))
        true = matching.damerau_levenshtein_distance(a, b)
        for cap in range(5):
            expected = true if true <= cap else cap + 1
            assert matching.damerau_levenshtein_distance(a, b, max_distance=cap) == expected


def test_describe_difference_still_separates_a_swap_from_a_substitution():
    """The swap is now read from the positions and not from a second distance."""
    assert matching.describe_difference("patietn_1", "patient_1") == "transposition"
    assert matching.describe_difference("batcha_1", "batchb_1") == "substitution"
    assert matching.describe_difference("smple_1", "sample_1") == "insertion or deletion"
    assert matching.describe_difference("alpha_1", "omega_1") == "unrelated"


# ── The signs that identify a sample ───────────────────────────────────────


def test_a_hyphen_between_two_characters_separates_two_tokens():
    assert rules.prepare("S1-B1") == "s1_b1"
    assert matching.group_names(["S1_B1", "s1-b1"], method="damerau") == [
        ["S1_B1", "s1-b1"]
    ]


def test_a_hyphen_in_any_other_position_is_a_sign():
    """dox- is the uninduced arm and dox+ is the induced one."""
    assert rules.prepare("OVTOKO_DOX-_br1") == "ovtoko_dox-_br1"
    # A sign carries the count of numbers that stand before it and the word it
    # touches, so that `control+_batch1`, `control_batch1+` and
    # `control_batch+1` all differ.
    assert matching.digit_signature("OVTOKO_DOX-_br1") == ("1", "0dox-")
    assert matching.digit_signature("OVTOKO_DOX+_br1") == ("1", "0dox+")
    assert matching.group_names(
        ["OVTOKO_DOX+_br1", "OVTOKO_DOX-_br1"], method="damerau"
    ) == [["OVTOKO_DOX+_br1"], ["OVTOKO_DOX-_br1"]]


def test_a_sign_separates_two_populations():
    """CD4+ and CD4- are two populations, and CXCR5+ and CXCR5- are two more."""
    for pair in (
        ["CD4+_donor1", "CD4-_donor1"],
        ["PD-1lo CXCR5+ population 2", "PD-1lo CXCR5- population 2"],
    ):
        assert len(matching.group_names(pair, method="damerau")) == 2, pair


def test_a_sign_survives_the_brackets_around_it():
    """ICESeq(+), ICESeq(++) and ICESeq(-) are three conditions of PRJDA74549."""
    names = [
        "Human ICESeq(+), template 1",
        "Human ICESeq(++), template 1",
        "Human ICESeq(-), template 1",
    ]
    assert len(matching.group_names(names, method="damerau")) == 3


def test_a_prime_marks_a_variant_of_a_name():
    names = ["HAP1 WT#2-1'_RNA", "HAP1 WT#2-1_RNA"]
    assert len(matching.group_names(names, method="damerau")) == 2


def test_the_number_sign_is_not_a_sign():
    """In #111_b2 it reads as the word number and identifies nothing."""
    assert matching.rule_normalise("#111_b2") == "111_batch2"
    assert matching.digit_signature("#111_b2") == ("111", "2")


def test_the_abbreviations_still_expand_across_a_hyphen():
    assert matching.group_names(
        ["ctrl-r1-batch1", "CTRL_rep1_b1"], method="damerau"
    ) == [["CTRL_rep1_b1", "ctrl-r1-batch1"]]


# ── A substituted letter is reported and never merged ──────────────────────


def test_a_substituted_letter_never_merges():
    """It is the one edit that also carries meaning, and on real data it did.

    Every one of the 42 pairs that a substitution merged on the ENA corpus was
    two different samples. These four are from PRJDB14694, PRJDB12299,
    PRJDB12972 and PRJDB15361.
    """
    for pair in (
        ["Primary B cells", "Primary T cells"],
        ["human cTEC5", "human mTEC5"],
        ["TSmatKO-1_paired-RNA", "TSpatKO-1_paired-RNA"],
        ["Decell A549 #1", "Recell A549 #1"],
    ):
        assert len(matching.group_names(pair, method="damerau")) == 2, pair


def test_a_substituted_letter_is_reported_instead():
    """A refused pair still reaches a person."""
    assert matching.find_letter_variants(["Primary B cells", "Primary T cells"]) == [
        ("Primary B cells", "Primary T cells")
    ]
    assert matching.find_letter_variants(["human cTEC5", "human mTEC5"]) == [
        ("human cTEC5", "human mTEC5")
    ]


def test_a_letter_variant_needs_the_same_numbers():
    """Two names with different numbers are a different report."""
    assert matching.find_letter_variants(["human cTEC5", "human mTEC7"]) == []


def test_a_plate_row_is_not_reported():
    """Eight row letters stand at one position, so the position is a field.

    PRJEB20147 holds 1351 plate wells and produced 1754 pairs without this
    rule, which buries the two or three that matter.
    """
    plate = [f"SCGC-1231_{row}07" for row in "ABCDEFGH"]
    assert matching.find_letter_variants(plate) == []

    # Two letters at the position is a contrast, and it is still reported.
    assert matching.find_letter_variants(plate[:2]) == [
        ("SCGC-1231_A07", "SCGC-1231_B07")
    ]


def test_one_keystroke_still_merges_and_is_not_reported():
    for pair in (
        ["smple_1", "sample_1"],
        ["sampel_5", "sample_5"],
        ["patietn1_batch1", "patient1_batch1"],
    ):
        assert len(matching.group_names(pair, method="damerau")) == 1, pair
        assert matching.find_letter_variants(pair) == [], pair


def test_padding_behind_a_symbol_reads_as_formatting():
    """malaria5#02 and malaria5#2 are one sample of PRJDB2573.

    The number sign stops the token from reaching the zero-padding rule, so the
    two normalise differently. Their letters and their numbers both agree, so
    the difference is formatting and the figure must say so.
    """
    assert matching.describe_difference("malaria5#02", "malaria5#2") == "formatting only"
    assert len(matching.group_names(["malaria5#02", "malaria5#2"], method="damerau")) == 1


# ── The backend list holds no dead alias ───────────────────────────────────


def test_only_the_backends_that_change_the_answer_are_offered():
    """A choice that does not change the answer is worse than no choice.

    hamming found a substituted character and nothing else, and a substitution
    no longer merges, so it answered as rules did. levenshtein and damerau
    differ only over a transposition, and the slip rule decides that for both.
    """
    assert matching.OFFLINE_METHODS == ("rules", "damerau")
    assert matching.METHODS == ("rules", "damerau", "llm", "auto")

    with pytest.raises(ValueError, match="Unknown offline method"):
        matching.group_names(["a_1"], method="hamming")
    with pytest.raises(ValueError, match="Unknown offline method"):
        matching.group_names(["a_1"], method="levenshtein")


def test_the_two_backends_do_not_answer_alike():
    """Each remaining backend has to earn its place in the list."""
    typo = ["patietn1_batch1", "patient1_batch1"]
    assert len(matching.group_names(typo, method="rules")) == 2
    assert len(matching.group_names(typo, method="damerau")) == 1


def test_the_three_measures_are_still_public():
    """Only the backend list shrank. The measures are correct and stay."""
    assert matching.hamming_distance("patient1", "patient2") == 1
    assert matching.levenshtein_distance("patient", "patietn") == 2
    assert matching.damerau_levenshtein_distance("patient", "patietn") == 1
    assert matching.similarity("abc", "abd", method="hamming") > 0.6
    assert matching.similarity("abc", "abd", method="levenshtein") > 0.6


# ── A chain of allowed edits may not carry a forbidden pair ────────────────


def test_a_bridge_cannot_carry_a_substitution_into_a_group():
    """Grouping is transitive and the match rule is not.

    abcde1 is one deletion from abcdef1 and one deletion from abcdeg1, so the
    union-find joined all three, and the two ends are one substitution apart.
    """
    names = ["abcdef1", "abcde1", "abcdeg1"]
    assert matching.describe_difference("abcdef1", "abcdeg1") == "substitution"
    assert matching.group_names(names, method="damerau") == [
        ["abcde1"],
        ["abcdef1"],
        ["abcdeg1"],
    ]


def test_the_bridge_check_leaves_a_clean_group_alone():
    """The five spellings of one sample hold no forbidden pair."""
    names = ["P1_B1", "p01_b01", "p1-b1", "patient1_batch1", "patietn1_batch1"]
    assert matching.group_names(names, method="damerau") == [sorted(names)]


def test_clear_name_caches_forgets_a_normalisation():
    """A rule changed at run time must not read an entry made under the old one."""
    from samplify import rules

    assert matching.rule_normalise("s1") == "sample1"
    original = rules.COMPILED_ALIASES
    try:
        rules.COMPILED_ALIASES = ()
        assert matching.rule_normalise("s1") == "sample1"  # the cached answer
        matching.clear_name_caches()
        assert matching.rule_normalise("s1") == "s1"
    finally:
        rules.COMPILED_ALIASES = original
        matching.clear_name_caches()

    assert matching.rule_normalise("s1") == "sample1"


def test_a_chain_of_one_edit_steps_may_span_two_edits():
    """This is a decision and not an accident.

    The cap governs one pair, and a group is built from many pairs. A chain
    carries evidence, because the middle name is one edit from both ends and
    that is the reason to believe the three are one sample. A substitution
    carries the opposite, and split_on_a_substitution removes those.

    The reference corpus holds no group in which a pair joined by a distance
    sits above the cap, so nothing real depends on this either way.
    """
    # Each step is one letter inserted inside the name. A letter added at the
    # end is a label and not a slip, and the rule above refuses that shape.
    chain = ["axbcdef1", "abcdef1", "abcdyef1"]
    assert matching.group_names(chain, method="damerau") == [sorted(chain)]

    # The two ends alone are two edits apart, and alone they do not merge.
    ends = [chain[0], chain[-1]]
    assert matching.damerau_levenshtein_distance(
        matching.letter_skeleton(ends[0]), matching.letter_skeleton(ends[1])
    ) == 2
    assert matching.group_names(ends, method="damerau") == [sorted(ends)[:1], sorted(ends)[1:]]


# ── A character that int cannot read ───────────────────────────────────────


def test_a_superscript_does_not_crash_the_near_miss_search():
    """`'²'.isdigit()` is True and `int('²')` raises.

    Every test for a number in the module now uses `str.isdecimal`, which is
    exactly the set that `int` reads.
    """
    assert "²".isdigit() and not "²".isdecimal()
    assert matching.find_near_misses(["sample²_1", "sample_1"]) == []
    assert matching.digit_signature("sample²_1") == ("1", "0sample²")


def test_a_character_that_is_neither_a_letter_nor_a_digit_identifies_a_sample():
    """It survives normalisation, so it may not be read as formatting.

    No name of the 36073 in the reference corpus holds one, so this costs
    nothing there and it keeps two names apart rather than guessing.
    """
    assert matching.group_names(["sample²_1", "sample_1"], method="damerau") == [
        ["sample_1"],
        ["sample²_1"],
    ]


def test_a_combining_mark_identifies_a_sample():
    """`İ` lower-cases to `i` and a combining dot, and dropping the dot made
    `sampleİ1` the same name as `sampleI1`. Two names that differ by a Greek
    letter already stay apart, so these have to as well."""
    assert "İ".lower() == "i̇"
    assert matching.digit_signature("sampleİ1") == ("1", "0samplei̇")
    assert matching.group_names(["sampleI1", "sampleİ1"], method="damerau") == [
        ["sampleI1"],
        ["sampleİ1"],
    ]


def test_the_three_name_readers_are_the_cached_ones():
    """A helper was once inserted between letter_skeleton and its decorator,
    which moved the cache onto the helper and left the reader uncached."""
    for reader in (matching.digit_signature, matching.letter_skeleton,
                   matching.rule_normalise):
        assert hasattr(reader, "cache_clear"), reader.__name__
    assert not hasattr(matching._identifies_but_cannot_be_read, "cache_clear")


def test_zero_padding_falls_away_in_any_script():
    """`str.lstrip("0")` removes the ASCII zero and nothing else.

    The Arabic-Indic `٠١` kept its padding while `01` lost it, so the two
    spellings of one number had different identities and never grouped. The
    digits keep their own script, so `sample١` and `sample1` stay apart for the
    same reason that `sample_9α` and `sample_9a` do.
    """
    assert matching.digit_signature("sample٠١") == matching.digit_signature("sample١")
    assert matching.digit_signature("sample01") == matching.digit_signature("sample1")
    assert matching.digit_signature("sample000") == ("0",)
    assert len(matching.group_names(["sample٠١", "sample١"], method="damerau")) == 1
    assert len(matching.group_names(["sample1", "sample١"], method="damerau")) == 2


def test_the_rules_backend_removes_padding_in_any_script_too():
    """The signature and the normalisation call the same padding function.

    `digit_signature` was fixed first and `_expand_token` was not, so the rules
    backend still kept `s٠١` and `s١` apart while the identity rule had already
    joined them.
    """
    assert matching.rule_normalise("s٠١") == matching.rule_normalise("s١")
    assert matching.rule_normalise("s01") == matching.rule_normalise("s1") == "sample1"
    assert matching.rule_normalise("sample000") == "sample0"
    assert matching.group_names(["s٠١", "s١"], method="rules") == [["s٠١", "s١"]]


def test_the_rules_backend_splits_a_word_from_its_number_in_any_script():
    """An ASCII-only letter class left `Пациент٠١` with its padding.

    The identity rule had already joined the two names, and the rules backend
    still kept them apart, so the two disagreed about one sample.
    """
    assert matching.rule_normalise("Пациент٠١") == matching.rule_normalise("Пациент١")
    assert matching.rule_normalise("patient01") == matching.rule_normalise("patient1")
    assert matching.group_names(["Пациент٠١", "Пациент١"], method="rules") == [
        ["Пациент٠١", "Пациент١"]
    ]


def test_padding_falls_away_when_a_letter_follows_the_number():
    """A pattern that ended at the digits left `sample001a` with its padding.

    `digit_signature` had already read the two as one identity, and the rules
    backend still kept them apart.
    """
    assert matching.rule_normalise("sample001a") == matching.rule_normalise("sample1a")
    assert matching.group_names(["sample001a", "sample1a"], method="rules") == [
        ["sample001a", "sample1a"]
    ]
    # The replicate letter still identifies the sample.
    assert matching.group_names(["sample_9a", "sample_9b"], method="damerau") == [
        ["sample_9a"],
        ["sample_9b"],
    ]


# ── The value of MIN_SLIP_LENGTH, measured against the reference corpus ────


@pytest.mark.parametrize(
    "left,right",
    [
        ("3C1", "3SC1"),            # PRJDB10263
        ("NT2", "NT2-H"),           # PRJDB13884
        ("KMM-1", "MM1"),           # PRJDB3120, two myeloma cell lines
        ("CPT2", "CPT2-H"),         # PRJDB13884
        ("SMB", "USMB"),            # PRJDB15836
        ("GEV-006_1", "GEV-006_F1"),  # PRJEB55162
        ("HD-006_FH", "HD-006_H"),  # PRJEB55162
        ("CPT2-H", "CPT2-HA"),      # PRJDB13884
    ],
)
def test_the_pairs_that_set_the_slip_length_stay_apart(left, right):
    """Every pair in the corpus that turns on the slip rule alone.

    The ratio refuses each of these, so only the rule could join them, and each
    one is two different samples. Their shortest skeletons run from one letter
    to four, which is why the limit is five.
    """
    assert min(
        len(matching.letter_skeleton(left)), len(matching.letter_skeleton(right))
    ) < matching.MIN_SLIP_LENGTH
    assert len(matching.group_names([left, right], method="damerau")) == 2


def test_a_shorter_limit_would_merge_them():
    """The limit is the smallest value that refuses all of them.

    This test fails if someone lowers MIN_SLIP_LENGTH, and it says why.
    """
    assert matching.MIN_SLIP_LENGTH == 5
    assert matching.describe_difference("SMB", "USMB") in matching.SLIP_KINDS
    assert matching.similarity(
        matching.letter_skeleton("SMB"), matching.letter_skeleton("USMB")
    ) < 0.85


# ── The value of MAX_VARIANT_LETTERS, measured against the corpus ──────────


def test_a_position_of_two_letters_carries_a_real_contrast():
    """1002 positions in the corpus hold two letters, and they are contrasts."""
    assert matching.find_letter_variants(["3C1", "3N1"]) == [("3C1", "3N1")]


def test_a_position_of_more_letters_is_a_field_of_the_scheme():
    """349 positions hold three or more, and every one read is a plate well.

    These are the rows of one plate at one timepoint, from PRJDB6952.
    """
    plate = [f"RNA-seq_A549_24h_{row}01_DMSO_0.1" for row in "ABCD"]
    assert matching.find_letter_variants(plate) == []

    # Two of the same rows is a contrast again, and it is reported.
    assert len(matching.find_letter_variants(plate[:2])) == 1


def test_the_variant_limit_is_the_measured_one():
    """This test fails if someone raises the limit, and it says why."""
    assert matching.MAX_VARIANT_LETTERS == 2


# ── A sign is a sign in every typeface ─────────────────────────────────────


@pytest.mark.parametrize(
    "left,right,label",
    [
        ("WT2-1′", "WT2-1", "a typographic prime"),
        ("WT2-1’", "WT2-1", "a right single quotation mark"),
        ("CD4−_donor1", "CD4_donor1", "a Unicode minus"),
        ("CD4–_donor1", "CD4_donor1", "an en dash"),
        ("CD4—_donor1", "CD4_donor1", "an em dash"),
        ("CD4＋_donor1", "CD4_donor1", "a fullwidth plus"),
        ("CD4±_donor1", "CD4_donor1", "a plus-minus sign"),
    ],
)
def test_a_sign_identifies_a_sample_in_every_typeface(left, right, label):
    """A name that arrives from a word processor carries the typographic sign.

    Only the ASCII prime and hyphen were kept, so `WT2-1′` merged with `WT2-1`
    and `CD4−_donor1` merged with `CD4_donor1`.
    """
    assert len(matching.group_names([left, right], method="damerau")) == 2, label


@pytest.mark.parametrize(
    "dash", ["-", "‐", "‑", "‒", "–", "—", "―",
             "−", "－"]
)
def test_every_dash_separates_two_tokens_where_a_hyphen_would(dash):
    """The position decides, and it decides the same for each of them.

    The members are compared as a set, because the ASCII hyphen sorts before
    the underscore and every other dash sorts after it.
    """
    groups = matching.group_names([f"S1{dash}B1", "S1_B1"], method="damerau")
    assert len(groups) == 1
    assert set(groups[0]) == {f"S1{dash}B1", "S1_B1"}


def test_a_sign_carries_its_position():
    """`control+_batch1` and `control_batch1+` are two names, and the signature
    said they were one. Each sign records how many numbers stand before it, and
    the numbers keep the first places so their positions never move."""
    assert matching.digit_signature("control+_batch1") == ("1", "0control+")
    assert matching.digit_signature("control_batch1+") == ("1", "1+")
    assert len(matching.group_names(
        ["control+_batch1", "control_batch1+"], method="damerau"
    )) == 2


# ── The difference is judged against the token that holds it ───────────────


@pytest.mark.parametrize(
    "left,right,label",
    [
        ("sample_A", "sample_AA", "two identifiers"),
        ("plate_A", "plate_AA", "two plates"),
        ("SM B from healthy control", "USM B from healthy control", "PRJDB15836"),
    ],
)
def test_shared_context_does_not_license_a_short_difference(left, right, label):
    """`sample_A` and `sample_AA` differ by one letter in a name of seven.

    The tool split `SMB` from `USMB` and merged the same two samples written
    out in full, because the words they share made the difference look small.
    """
    assert len(matching.group_names([left, right], method="damerau")) == 2, label


@pytest.mark.parametrize(
    "left,right,label",
    [
        ("smple_1", "sample_1", "a dropped letter"),
        ("sampel_5", "sample_5", "a swap"),
        ("patietn1_batch1", "patient1_batch1", "a swap beside another token"),
        ("S1_B1", "s1-b1", "formatting"),
        ("ctrl-r1-batch1", "CTRL_rep1_b1", "abbreviations"),
    ],
)
def test_a_real_typing_error_still_merges(left, right, label):
    assert len(matching.group_names([left, right], method="damerau")) == 1, label


def test_the_whole_name_decides_when_no_single_token_holds_the_difference():
    """Two names with different token counts have no one differing token."""
    assert matching.comparable_letters("sample_1", "sample_batch_1") == (
        "sample", "samplebatch"
    )
    assert matching.comparable_letters("sample_A", "sample_AA") == ("a", "aa")


@pytest.mark.parametrize(
    "left,right,label",
    [
        ("MSTO-211H PBS 6h", "MSTO-211H_R PBS 6h", "a parental line and its resistant line"),
        ("MSTO-211H Pemetrexed 6h", "MSTO-211H_R Pemetrexed 6h", "the same under treatment"),
        ("TCC-MESO-2 PBS 6h", "TCC-MESO-2_R PBS 6h", "another pair of the same study"),
        ("RNA_OvK_S005_Primary_0", "RNA_OvK_S005_Primary_A0", "PRJDB12395"),
    ],
)
def test_a_whole_token_added_is_not_a_typing_error(left, right, label):
    """No keystroke adds a token.

    `MSTO-211H` and `MSTO-211H_R` are a parental cell line and the resistant
    line derived from it in a study of pemetrexed resistance, and the words
    around the added token made it look like one inserted letter.
    """
    assert len(matching.group_names([left, right], method="damerau")) == 2, label


def test_a_name_without_delimiters_is_not_that_shape():
    """`p1b1` holds the one token `pb` and `p1_b1` holds `p` and `b`, and
    neither list is inside the other, so the two are compared as whole names."""
    assert matching._one_name_gained_a_token("MSTO_R_x", "MSTO_x")
    assert not matching._one_name_gained_a_token("p1b1", "p1_b1")
    assert matching.group_names(["p1b1", "p1_b1"], method="damerau") == [
        ["p1_b1", "p1b1"]
    ]


@pytest.mark.parametrize(
    "left,right",
    [
        ("CD4-", "CD4−"),   # ASCII hyphen against the Unicode minus
        ("CD4-", "CD4–"),   # against the en dash
        ("CD4-", "CD4－"),   # against the fullwidth hyphen-minus
        ("CD4+", "CD4＋"),   # ASCII plus against the fullwidth plus
        ("WT2-1'", "WT2-1′"),   # apostrophe against the prime
        ("WT2-1'", "WT2-1’"),   # against the right single quotation mark
    ],
)
def test_one_sign_written_two_ways_is_one_sign(left, right):
    """A sign is a sign in every typeface, and the identity says so.

    The sign tables made each typographic form count as a sign, and the
    signature then kept the raw character. `CD4-` and `CD4−` therefore held two
    identities and never merged, which the documentation said they would.
    """
    assert matching.digit_signature(left) == matching.digit_signature(right)
    assert matching.group_names([left, right], method="damerau") == [
        sorted([left, right])
    ]


@pytest.mark.parametrize("sign", ["±", "″"])
def test_a_sign_that_stands_for_itself_does_not_fold(sign):
    """The plus-minus and the double prime are not spellings of another sign."""
    assert matching.digit_signature(f"CD4{sign}") != matching.digit_signature("CD4-")
    assert matching.digit_signature(f"CD4{sign}") != matching.digit_signature("CD4+")


def test_a_sign_belongs_to_the_word_it_touches():
    """`control+` and `batch+` are two statements, and the signature says so.

    The entry held only the count of numbers before the sign, so
    `control+_batch1` and `control_batch+1` both read `0+` and the two names
    merged into one sample.
    """
    assert matching.digit_signature("control+_batch1") != matching.digit_signature(
        "control_batch+1"
    )
    assert len(
        matching.group_names(["control+_batch1", "control_batch+1"], method="damerau")
    ) == 2


def test_the_word_in_front_of_a_sign_is_read_through_the_abbreviation_table():
    """`ctrl+` and `control+` make one statement, so the identity is one.

    The word joins the signature expanded, because the raw word would make the
    identity rule refuse a pair of names that the abbreviation table exists to
    join.
    """
    assert matching.digit_signature("ctrl+_1") == matching.digit_signature("control+_1")
    assert matching.digit_signature("ctrl_batch1") == matching.digit_signature(
        "control_batch1"
    )


@pytest.mark.parametrize("name", ["", "   ", "_", "__"])
def test_a_name_that_identifies_nothing_is_not_canonical(name):
    """The check answered yes about a name that holds no identity.

    The search for a forbidden character finds nothing in an empty string, so
    the answer was True and the guard read as permission.
    """
    assert rules.is_canonical(name) is False


@pytest.mark.parametrize("name", ["sample_1", "s1", "1", "a_b_c_9"])
def test_a_name_that_follows_the_rules_is_canonical(name):
    assert rules.is_canonical(name) is True


@pytest.mark.parametrize(
    "positive,negative",
    [
        ("CD4⁺_donor1", "CD4⁻_donor1"),   # the superscript forms a journal writes
        ("CD4₊_donor1", "CD4₋_donor1"),   # the subscript forms
    ],
)
def test_a_superscript_sign_separates_two_populations(positive, negative):
    """`CD4⁺` and `CD4⁻` are two populations, and a journal writes them that way.

    The superscript plus is a mathematical symbol and not a word character, so
    normalisation deleted it and the identity signature never saw it. The two
    names became one string and the rules path merged them with no distance
    computed at all.
    """
    assert matching.digit_signature(positive) != matching.digit_signature(negative)
    assert len(matching.group_names([positive, negative], method="rules")) == 2


@pytest.mark.parametrize(
    "left,right",
    [("CD4⁺_donor1", "CD4+_donor1"), ("CD4⁻_donor1", "CD4-_donor1")],
)
def test_a_superscript_sign_is_the_sign_it_writes(left, right):
    """One statement written in two typefaces is one statement."""
    assert matching.digit_signature(left) == matching.digit_signature(right)
    assert matching.group_names([left, right], method="rules") == [sorted([left, right])]


def test_the_set_of_signs_covers_every_identity_character_of_the_corpus():
    """The signs were measured against real data and not chosen.

    The 36073 names of the reference corpus hold 18 characters that are neither
    a letter nor a digit nor a space. Three of them carry identity, and all
    three are kept. The other fifteen separate or decorate, and each one is
    dropped.
    """
    carries_identity = "-+'"
    separates_or_decorates = '_,.()#/:"[]%=?>'

    for character in carries_identity:
        assert matching.digit_signature(f"cd4{character}_donor1") != matching.digit_signature(
            "cd4_donor1"
        ), character

    for character in separates_or_decorates:
        assert matching.rule_normalise(f"cd4{character}_donor1") == matching.rule_normalise(
            "cd4_donor1"
        ), character


def test_every_unicode_spelling_of_a_kept_sign_reads_as_that_sign():
    """The list of spellings is closed, and this test is how it stays closed.

    A character whose compatibility form is a sign samplify keeps is a spelling
    of that sign. `CD4⁺` merged with `CD4⁻` because one such spelling was
    missing, and that pair is a positive and a negative population.
    """
    import unicodedata

    known = set(rules.IDENTITY_SIGNS) | set(rules.HYPHENS)
    missing = []
    for code in range(0x20, 0x1F000):
        character = chr(code)
        forms = {
            unicodedata.normalize("NFKC", character),
            unicodedata.normalize("NFKD", character),
        }
        if forms & {"+", "-", "'", "±"} and character not in known:
            missing.append(f"U+{code:04X} {unicodedata.name(character, '?')}")

    assert missing == [], missing


@pytest.mark.parametrize(
    "wide,plain",
    [("sample１", "sample1"), ("sampleＡ_1", "sampleA_1"), ("ｓ１＿ｂ１", "s1_b1")],
)
def test_a_fullwidth_character_is_the_same_character(wide, plain):
    """`sample１` is `sample1` typed on a Japanese keyboard.

    The fullwidth signs were folded and the letters and the digits were not, so
    one name typed on two keyboards read as two samples.
    """
    assert matching.digit_signature(wide) == matching.digit_signature(plain)
    assert matching.group_names([wide, plain], method="rules") == [sorted([wide, plain])]


@pytest.mark.parametrize("pair", [("sample١", "sample1"), ("sample_9α", "sample_9a")])
def test_another_script_is_another_sample(pair):
    """A digit of another script is not a width of the ASCII one.

    A cohort that labels its replicates `sample_9α` and `sample_9β` names two
    samples exactly as `9a` and `9b` do, and the same holds for the digits.
    """
    assert matching.digit_signature(pair[0]) != matching.digit_signature(pair[1])
    assert len(matching.group_names(list(pair), method="rules")) == 2


@pytest.mark.parametrize(
    "left,right",
    [
        ("SampleA", "SampleAA"),     # the compact form of the pair below
        ("sample_A", "sample_AA"),   # two identifiers, and the corpus holds this
        ("sample", "samplee"),       # a label added, or a letter typed twice
        ("ctrl", "ctrls"),
        ("Usamplebatchone1", "samplebatchone1"),   # the same shape at the front
        ("USMB1", "SMB1"),                         # the corpus pair, written short
    ],
)
def test_a_label_added_at_either_end_is_not_a_slipped_keystroke(left, right):
    """The delimiter was doing the work, and the compact form escaped.

    `sample_A` and `sample_AA` differ in a token of one letter against two, and
    the ratio refuses that. `SampleA` and `SampleAA` hold the same difference
    inside one token of eight letters, where the ratio reads 0.933 and merged
    two samples.

    The front of the name reads the same way. `SM B from healthy control` and
    `USM B from healthy control` are two samples of the reference corpus. No
    pair of that corpus merges on either shape.
    """
    assert len(matching.group_names([left, right], method="damerau")) == 2


@pytest.mark.parametrize(
    "left,right",
    [
        ("smple_1", "sample_1"),          # a letter dropped inside the name
        ("patinet1_b1", "patient1_b1"),   # a transposition, and the corpus holds it
    ],
)
def test_a_slip_inside_the_name_still_merges(left, right):
    """The rule reads the end of the name and nothing else."""
    assert matching.group_names([left, right], method="damerau") == [sorted([left, right])]


def test_a_chain_carries_evidence_that_the_names_are_one_sample():
    """The design note and the code agree about a chain, and this pins both.

    `patient1_batch1`, `patietn1_batch1` and `pateint1_batch1` are the same
    name typed by two people who slipped in different places. Each wrong
    spelling is one edit from the right one, the two of them are two edits from
    each other, and the middle name is the evidence that the three are one
    sample.
    """
    names = ["patient1_batch1", "patietn1_batch1", "pateint1_batch1"]
    assert matching.group_names(names, method="damerau") == [sorted(names)]

    ends = ["patietn1_batch1", "pateint1_batch1"]
    assert matching.damerau_levenshtein_distance(*matching.comparable_letters(*ends)) == 2
    assert len(matching.group_names(ends, method="damerau")) == 2
