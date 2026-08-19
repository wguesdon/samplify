"""Property tests for the three claims samplify makes about every input.

The tests elsewhere pin down named cases. These generate names instead, so they
cover shapes nobody thought to write down. Each one states a claim that must
hold for every input, and hypothesis looks for the input that breaks it.

The claims are the ones a person relies on when they accept a mapping.

1. No group ever holds two different digit signatures. The numbers identify the
   sample, so a group that mixes two of them has merged two samples.
2. ``apply`` never changes the source column, and the output holds one row for
   each input row.
3. The result never depends on the order of the input.
"""

from __future__ import annotations

import csv as csv_module
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from samplify import matching
from samplify.csv_processor import apply_mapping, propose_csv

# ── Generating a sample name ───────────────────────────────────────────────

WORDS = ("sample", "patient", "ctrl", "wildtype", "ko", "batch", "rep", "donor",
         "s", "p", "b", "tec", "mono")

_words = st.sampled_from(WORDS)
_numbers = st.one_of(
    st.integers(min_value=0, max_value=250).map(str),
    st.integers(min_value=1, max_value=30).map(lambda n: f"{n:03d}"),
)
_delimiters = st.sampled_from(("_", "-", ".", " "))
_signs = st.sampled_from(("", "", "", "+", "-", "'"))


@st.composite
def sample_names(draw: st.DrawFn) -> str:
    """Build one name that looks like a name a laboratory writes.

    Args:
        draw: The hypothesis draw function.

    Returns:
        A raw sample name of one to three components, each a word with an
        optional number, joined by a delimiter and carrying an optional sign.
    """
    parts = []
    for _ in range(draw(st.integers(min_value=1, max_value=3))):
        word = draw(_words)
        if draw(st.booleans()):
            word += draw(st.sampled_from(("", "_", "-"))) + draw(_numbers)
        parts.append(word + draw(_signs))

    name = draw(_delimiters).join(parts)
    if draw(st.booleans()):
        name = name.upper()
    elif draw(st.booleans()):
        name = name.capitalize()
    return name


name_lists = st.lists(sample_names(), min_size=1, max_size=25, unique=True)


# ── Claim 1: a group never mixes two identities ────────────────────────────


@given(names=name_lists, method=st.sampled_from(matching.OFFLINE_METHODS))
@settings(max_examples=250, deadline=None)
def test_a_group_never_holds_two_digit_signatures(names, method):
    """The numbers identify the sample, so a group may hold only one set."""
    for group in matching.group_names(names, method=method):
        signatures = {matching.digit_signature(member) for member in group}
        assert len(signatures) == 1, (group, signatures)


@given(names=name_lists, method=st.sampled_from(matching.OFFLINE_METHODS))
@settings(max_examples=250, deadline=None)
def test_every_name_reaches_exactly_one_group(names, method):
    """A lost name drops a row and a repeated name is ambiguous."""
    groups = matching.group_names(names, method=method)
    members = [member for group in groups for member in group]
    assert sorted(members) == sorted(set(names))


# ── Claim 3: the order of the input decides nothing ────────────────────────


@given(names=name_lists, method=st.sampled_from(matching.OFFLINE_METHODS))
@settings(max_examples=250, deadline=None)
def test_the_grouping_does_not_depend_on_the_input_order(names, method):
    forward = matching.group_names(names, method=method)
    backward = matching.group_names(list(reversed(names)), method=method)
    assert forward == backward


@given(names=name_lists)
@settings(max_examples=200, deadline=None)
def test_the_canonical_name_does_not_depend_on_the_input_order(names):
    for group in matching.group_names(names, method="damerau"):
        assert matching.canonical_for_group(group) == matching.canonical_for_group(
            list(reversed(group))
        )


@given(names=name_lists)
@settings(max_examples=200, deadline=None)
def test_a_reported_pair_is_never_a_merged_pair(names):
    """A pair is either merged or reported for a person, and never both."""
    merged: set[tuple[str, str]] = set()
    for group in matching.group_names(names, method="damerau"):
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                merged.add((min(left, right), max(left, right)))

    reported = set(matching.find_near_misses(names)) | set(
        matching.find_letter_variants(names)
    )
    assert merged & reported == set()


# ── Claim 2: apply changes no column and loses no row ──────────────────────


@given(names=st.lists(sample_names(), min_size=1, max_size=20))
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_apply_keeps_every_row_and_never_touches_the_source_column(names):
    """The output holds every value of the input, plus one new column.

    The quoting is the writer's. A value that needs no quote carries none, so
    the comparison reads the values and not the bytes of the file.
    """
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        with open(source, "w", newline="") as handle:
            writer = csv_module.writer(handle)
            writer.writerow(["sample_id", "value"])
            for position, name in enumerate(names):
                writer.writerow([name, position])

        mapping = propose_csv(source, "sample_id", method="damerau")
        mapping.accept_all()
        output = Path(directory) / "out.csv"
        frame, log = apply_mapping(mapping, output_path=output)

        written = pd.read_csv(output, dtype=str, keep_default_na=False)
        assert list(written["sample_id"]) == names
        assert list(written["value"]) == [str(p) for p in range(len(names))]
        assert len(written) == len(names)
        assert log["summary"]["total_rows"] == len(names)
        assert "sample_id_canonical" in written.columns


@given(names=st.lists(sample_names(), min_size=1, max_size=20))
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_apply_never_writes_an_empty_canonical_name(names):
    """A rename to nothing loses the identity of the row."""
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        with open(source, "w", newline="") as handle:
            writer = csv_module.writer(handle)
            writer.writerow(["sample_id"])
            for name in names:
                writer.writerow([name])

        mapping = propose_csv(source, "sample_id", method="damerau")
        mapping.accept_all()
        frame, _ = apply_mapping(mapping)

        for value in frame["sample_id_canonical"]:
            assert isinstance(value, str) and value.strip(), repr(value)


@given(names=name_lists)
@settings(max_examples=200, deadline=None)
def test_two_runs_of_apply_give_the_same_mapping(names):
    """The same input gives the same proposal on any run."""
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        source.write_text("sample_id\n" + "\n".join(f'"{n}"' for n in names) + "\n")

        first = propose_csv(source, "sample_id", method="damerau")
        second = propose_csv(source, "sample_id", method="damerau")
        assert [g.to_dict() for g in first.groups] == [g.to_dict() for g in second.groups]
        assert first.near_misses == second.near_misses


# ── No decision and no input can lose a row ────────────────────────────────


@given(names=st.lists(sample_names(), min_size=1, max_size=15))
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_apply_keeps_every_row_and_every_other_column(names):
    """The row count and every column the tool does not write are untouched."""
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        with open(source, "w", newline="") as handle:
            writer = csv_module.writer(handle)
            writer.writerow(["sample_id", "n"])
            for position, name in enumerate(names):
                writer.writerow([name, position])

        mapping = propose_csv(source, "sample_id", method="damerau")
        mapping.accept_all()
        output = Path(directory) / "out.csv"
        apply_mapping(mapping, output_path=output)

        written = pd.read_csv(output, dtype=str, keep_default_na=False)
        assert list(written["sample_id"]) == names
        assert list(written["n"]) == [str(i) for i in range(len(names))]


@given(
    names=st.lists(sample_names(), min_size=1, max_size=12),
    decisions=st.lists(st.booleans(), min_size=1, max_size=12),
)
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_no_combination_of_decisions_loses_a_row(names, decisions):
    """A person may accept some groups and reject others in any pattern."""
    from samplify.mapping import STATUS_ACCEPTED, STATUS_REJECTED

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        with open(source, "w", newline="") as handle:
            writer = csv_module.writer(handle)
            writer.writerow(["sample_id"])
            for name in names:
                writer.writerow([name])

        mapping = propose_csv(source, "sample_id", method="damerau")
        for group, accept in zip(mapping.groups, decisions * len(mapping.groups)):
            group.status = STATUS_ACCEPTED if accept else STATUS_REJECTED
            group.final = group.proposed

        output = Path(directory) / "out.csv"
        apply_mapping(mapping, output_path=output)

        written = pd.read_csv(output, dtype=str, keep_default_na=False)
        assert list(written["sample_id"]) == names
        for value in written["sample_id_canonical"]:
            assert isinstance(value, str) and value.strip()


# ── The model can neither lose a name nor mix two identities ───────────────


@given(
    names=name_lists,
    method=st.sampled_from(["llm", "auto"]),
    merge_all=st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_no_model_answer_loses_a_name_or_mixes_two_identities(names, method, merge_all):
    """The model is asked to merge everything, and then to merge nothing.

    Neither answer may lose a name from the file a person reviews, and neither
    may put two identities in one group. A dictionary of representatives once
    dropped a whole cluster, and the offline rules once guarded only the
    offline path.
    """
    from unittest.mock import patch

    from samplify.csv_processor import propose

    unique = sorted(set(names))
    mapping = {name: "one_name" for name in unique} if merge_all else {}
    answer = {"canonical_pattern": "", "mapping": mapping}

    with patch("samplify.csv_processor.harmonize", return_value=answer):
        result = propose(unique, method=method, api_key="test")

    kept = sorted(member for group in result.groups for member in group.members)
    assert kept == unique

    for group in result.groups:
        assert len({matching.digit_signature(m) for m in group.members}) == 1
        for index, left in enumerate(group.members):
            for right in group.members[index + 1:]:
                assert matching.describe_difference(left, right) != "substitution"


@given(names=name_lists, method=st.sampled_from(matching.OFFLINE_METHODS))
@settings(max_examples=250, deadline=None)
def test_no_group_joins_two_names_where_one_gained_a_token(names, method):
    """No keystroke adds a token, so no group may hold that pair.

    A group formed by the normalisation rules is exempt, because those two
    names reduce to one string and the tokens are the same information written
    two ways.
    """
    for group in matching.group_names(names, method=method):
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if matching.rule_normalise(left) == matching.rule_normalise(right):
                    continue
                assert not matching._one_name_gained_a_token(left, right), (left, right)


# ── The row count of the output is the row count of the file ───────────────

_lines = st.one_of(
    sample_names(),
    st.just(""),
    st.just("   "),
    st.just('"a,b"'),
    st.just('"has ""quotes"""'),
)


@given(lines=st.lists(_lines, min_size=1, max_size=12))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_the_output_holds_one_row_for_each_record_of_the_file(lines):
    """The csv module is the ground truth for how many rows a file holds.

    A blank line is a record and pandas dropped it, so the output held fewer
    rows than the input. The count is read from the file rather than from the
    list of names, because a quoted newline makes one record of two lines.
    """
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        source.write_text("sample_id\n" + "\n".join(lines) + "\n", newline="")

        with open(source, newline="") as handle:
            records = list(csv_module.reader(handle))
        expected = len(records) - 1

        mapping = propose_csv(source, "sample_id", method="damerau")
        mapping.accept_all()
        output = Path(directory) / "out.csv"
        frame, log = apply_mapping(mapping, output_path=output)

        assert len(frame) == expected, (lines, len(frame), expected)
        assert log["summary"]["total_rows"] == expected


@given(names=st.lists(sample_names(), min_size=1, max_size=12))
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_every_value_of_a_column_the_tool_does_not_write_survives(names):
    """The promise the tool makes about the columns it never touches.

    A NUL byte cut a value short and a ragged row moved a whole column, and
    both were silent. The comparison reads the values, because the quoting of
    the file belongs to the writer.
    """
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "in.csv"
        with open(source, "w", newline="") as handle:
            writer = csv_module.writer(handle)
            writer.writerow(["sample_id", "note", "n"])
            for position, name in enumerate(names):
                writer.writerow([name, f"a,b {name}", position])

        mapping = propose_csv(source, "sample_id", method="damerau")
        mapping.accept_all()
        output = Path(directory) / "out.csv"
        apply_mapping(mapping, output_path=output)

        written = pd.read_csv(output, dtype=str, keep_default_na=False)
        assert list(written["note"]) == [f"a,b {name}" for name in names]
        assert list(written["n"]) == [str(i) for i in range(len(names))]


@given(names=name_lists, method=st.sampled_from(matching.OFFLINE_METHODS))
@settings(max_examples=400, deadline=None)
def test_no_group_joins_two_names_where_one_is_a_label_of_the_other(names, method):
    """A label added at an end of a name is not a slipped keystroke.

    Grouping is transitive and the match rule is not, so this claim is not
    implied by the rule that refuses the pair. A pair that normalises to one
    string is exempt, because no distance decided it.
    """
    for group in matching.group_names(names, method=method):
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if matching.rule_normalise(left) == matching.rule_normalise(right):
                    continue
                first, second = matching.comparable_letters(left, right)
                if first == second:
                    continue
                assert not (
                    first.startswith(second)
                    or second.startswith(first)
                    or first.endswith(second)
                    or second.endswith(first)
                ), (left, right, first, second)
