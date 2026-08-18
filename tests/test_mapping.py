"""Tests for the mapping file: the artifact a person reviews.

The guards here are the ones that stop a silent merge. A group without a
decision must block the apply step, and two groups that land on one canonical
name must block it too unless a person looked at them.
"""

from __future__ import annotations

import json

import pytest

from samplify import cli
from samplify import mapping as mapping_module
from samplify.mapping import (
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    Group,
    MappingFile,
)


def _group(id_: int, members: list[str], proposed: str, status: str = STATUS_PROPOSED) -> Group:
    return Group(
        id=id_,
        members=members,
        proposed=proposed,
        final=proposed,
        status=status,
        occurrences={m: 1 for m in members},
    )


# ── Group behaviour ────────────────────────────────────────────────────────


def test_group_kinds():
    merge = _group(1, ["a", "b"], "a")
    rename = _group(2, ["c"], "c_clean")
    noop = _group(3, ["d"], "d")

    assert merge.is_merge and not merge.is_rename and not merge.is_noop
    assert rename.is_rename and not rename.is_merge
    assert noop.is_noop and not noop.is_rename


def test_group_rows_counts_every_member():
    group = Group(id=1, members=["a", "b"], proposed="a", final="a", occurrences={"a": 3, "b": 4})
    assert group.rows == 7


def test_resolved_raises_while_proposed():
    with pytest.raises(ValueError, match="still proposed"):
        _group(1, ["a", "b"], "a").resolved()


def test_resolved_accepted_maps_every_member_to_the_final_name():
    group = _group(1, ["a", "b"], "canonical", status=STATUS_ACCEPTED)
    assert group.resolved() == {"a": "canonical", "b": "canonical"}


def test_resolved_rejected_leaves_every_member_alone():
    """A rejection never deletes a row and never leaves a null value."""
    group = _group(1, ["a", "b"], "canonical", status=STATUS_REJECTED)
    assert group.resolved() == {"a": "a", "b": "b"}


# ── Mapping file behaviour ─────────────────────────────────────────────────


def test_final_mapping_refuses_while_a_group_is_pending():
    mapping = MappingFile(groups=[_group(1, ["a"], "a", status=STATUS_ACCEPTED), _group(2, ["b"], "b")])
    with pytest.raises(ValueError, match="still proposed"):
        mapping.final_mapping()


def test_final_mapping_after_accept_all():
    mapping = MappingFile(groups=[_group(1, ["a", "b"], "c"), _group(2, ["d"], "e")])
    mapping.accept_all()
    assert mapping.final_mapping() == {"a": "c", "b": "c", "d": "e"}


def test_accept_all_does_not_claim_a_review_happened():
    mapping = MappingFile(groups=[_group(1, ["a"], "b")])
    mapping.accept_all()
    assert mapping.reviewed is False


def test_mark_reviewed_records_the_time():
    mapping = MappingFile(groups=[])
    mapping.mark_reviewed()
    assert mapping.reviewed is True
    assert mapping.reviewed_at is not None


def test_collisions_finds_two_groups_with_one_canonical_name():
    mapping = MappingFile(
        groups=[
            _group(1, ["a"], "same", status=STATUS_ACCEPTED),
            _group(2, ["b"], "same", status=STATUS_ACCEPTED),
            _group(3, ["c"], "other", status=STATUS_ACCEPTED),
        ]
    )
    assert mapping.collisions() == {"same": [1, 2]}


def test_a_merge_inside_one_group_is_not_a_collision():
    mapping = MappingFile(groups=[_group(1, ["a", "b", "c"], "same", status=STATUS_ACCEPTED)])
    assert mapping.collisions() == {}


def test_a_rejected_group_cannot_collide():
    mapping = MappingFile(
        groups=[
            _group(1, ["a"], "same", status=STATUS_ACCEPTED),
            _group(2, ["b"], "same", status=STATUS_REJECTED),
        ]
    )
    assert mapping.collisions() == {}


def test_summary_counts():
    mapping = MappingFile(
        groups=[_group(1, ["a", "b"], "c"), _group(2, ["d"], "e"), _group(3, ["f"], "f")],
        near_misses=[["x", "y"]],
    )
    summary = mapping.summary()
    assert summary["groups"] == 3
    assert summary["merges"] == 1
    assert summary["renames"] == 1
    assert summary["unchanged"] == 1
    assert summary["pending"] == 3
    assert summary["near_misses"] == 1


# ── Round trip and validation ──────────────────────────────────────────────


def test_round_trip_keeps_every_field(tmp_path):
    original = MappingFile(
        groups=[_group(1, ["a", "b"], "c", status=STATUS_EDITED)],
        method="damerau",
        input_file="/data/samples.csv",
        column="sample_id",
        near_misses=[["p11", "p111"]],
        canonical_pattern="patient<n>_batch<m>",
    )
    original.mark_reviewed()

    path = mapping_module.write(original, tmp_path / "m.json")
    restored = mapping_module.read(path)

    assert restored.method == "damerau"
    assert restored.input_file == "/data/samples.csv"
    assert restored.column == "sample_id"
    assert restored.reviewed is True
    assert restored.near_misses == [["p11", "p111"]]
    assert restored.groups[0].status == STATUS_EDITED
    assert restored.final_mapping() == {"a": "c", "b": "c"}


def test_read_rejects_an_unsupported_schema_version(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"schema_version": 99, "groups": []}))
    with pytest.raises(ValueError, match="schema version"):
        mapping_module.read(path)


def test_read_rejects_a_name_in_two_groups(tmp_path):
    """One name, one group. Two would make the final mapping ambiguous."""
    document = {
        "schema_version": mapping_module.SCHEMA_VERSION,
        "groups": [
            _group(1, ["a", "b"], "x", status=STATUS_ACCEPTED).to_dict(),
            _group(2, ["b"], "y", status=STATUS_ACCEPTED).to_dict(),
        ],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="appears in group"):
        mapping_module.read(path)


def test_read_rejects_an_unknown_status(tmp_path):
    document = {
        "schema_version": mapping_module.SCHEMA_VERSION,
        "groups": [
            {"id": 1, "members": ["a"], "proposed": "a", "final": "a", "status": "maybe"}
        ],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="not one of"):
        mapping_module.read(path)


def test_read_rejects_a_group_with_no_members(tmp_path):
    document = {
        "schema_version": mapping_module.SCHEMA_VERSION,
        "groups": [
            {"id": 1, "members": [], "proposed": "a", "final": "a", "status": "accepted"}
        ],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="no members"):
        mapping_module.read(path)


def test_read_rejects_invalid_json(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        mapping_module.read(path)


# ── The review findings of 2026-08-18 ──────────────────────────────────────


def test_collisions_count_the_original_names_of_a_rejected_group():
    """A rejected group keeps its names, so they stay in the output namespace.

    Group 1 was rejected and keeps patient11_batch1. Group 2 was renamed onto
    that same name. Skipping the rejected group hid the collision, and apply
    then gave two patients one name with no message.
    """
    result = MappingFile(
        groups=[
            _group(1, ["patient11_batch1"], "patient11_batch1", STATUS_REJECTED),
            _group(2, ["patient111_batch1"], "patient11_batch1", STATUS_EDITED),
        ]
    )
    assert result.collisions() == {"patient11_batch1": [1, 2]}


def test_reviewed_must_be_a_boolean():
    """bool("false") is True, and the string switched the collision guard off."""
    document = {
        "schema_version": 1,
        "reviewed": "false",
        "groups": [
            {
                "id": 1,
                "members": ["a_1"],
                "proposed": "a1",
                "final": "a1",
                "status": STATUS_ACCEPTED,
            }
        ],
    }
    with pytest.raises(ValueError, match="must be true or false"):
        MappingFile.from_dict(document)


@pytest.mark.parametrize("value", [None, "", "   ", 3])
def test_a_canonical_name_that_is_not_a_name_is_refused(value):
    """str(None) gives the string None, and every member took that name."""
    document = {
        "id": 1,
        "members": ["a_1"],
        "proposed": value,
        "final": "a1",
        "status": STATUS_ACCEPTED,
    }
    with pytest.raises(ValueError, match="must be a string that holds a character"):
        Group.from_dict(document)


def test_a_member_that_is_not_a_name_is_refused():
    document = {
        "id": 1,
        "members": ["a_1", ""],
        "proposed": "a1",
        "final": "a1",
        "status": STATUS_ACCEPTED,
    }
    with pytest.raises(ValueError, match="must be a string that holds a character"):
        Group.from_dict(document)


def test_write_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "mapping.json"
    mapping_module.write(MappingFile(groups=[_group(1, ["a_1"], "a1")]), path)
    assert path.exists()
    assert list(tmp_path.iterdir()) == [path]


def test_a_failed_write_keeps_the_previous_file(tmp_path, monkeypatch):
    """This file holds the decisions a person made, so a crash must not lose them."""
    path = tmp_path / "mapping.json"
    mapping_module.write(MappingFile(groups=[_group(1, ["a_1"], "a1")]), path)
    before = path.read_text()

    def explode(*args, **kwargs):
        raise OSError("the disk is full")

    monkeypatch.setattr(mapping_module.json, "dump", explode)
    with pytest.raises(OSError):
        mapping_module.write(MappingFile(groups=[_group(2, ["b_2"], "b2")]), path)

    assert path.read_text() == before
    assert list(tmp_path.iterdir()) == [path]


def test_members_must_be_a_list():
    """A string is iterable, so "AB" would become the two samples A and B."""
    document = {
        "id": 1,
        "members": "AB",
        "proposed": "merged",
        "final": "merged",
        "status": STATUS_ACCEPTED,
    }
    with pytest.raises(ValueError, match="must be a list of names"):
        Group.from_dict(document)


def test_the_groups_key_must_be_a_list():
    with pytest.raises(ValueError, match="must be a list"):
        MappingFile.from_dict({"schema_version": 1, "groups": {"id": 1}})


@pytest.mark.parametrize("document", [[], [{"id": 1}], "text", 7, None])
def test_a_mapping_file_that_is_not_an_object_is_refused(document):
    """json.load returns whatever the file holds, and a list has no .get."""
    with pytest.raises(ValueError, match="holds an object"):
        MappingFile.from_dict(document)


def test_a_mapping_file_that_is_not_an_object_is_refused_on_disk(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text('[{"id": 1}]')
    with pytest.raises(ValueError, match="holds an object"):
        mapping_module.read(path)


@pytest.mark.parametrize("identifier", [None, "one", [], {}, True, False])
def test_a_group_id_that_is_not_a_number_is_refused(identifier):
    """int(None) raises TypeError, and this class documents ValueError."""
    document = {
        "id": identifier,
        "members": ["a_1"],
        "proposed": "a1",
        "final": "a1",
        "status": STATUS_ACCEPTED,
    }
    with pytest.raises(ValueError, match="An id must be a number"):
        Group.from_dict(document)


def test_a_group_id_given_as_text_is_read():
    """A number written as text is still a number, and JSON allows it."""
    group = Group.from_dict(
        {"id": "3", "members": ["a_1"], "proposed": "a1", "final": "a1",
         "status": STATUS_ACCEPTED}
    )
    assert group.id == 3


@pytest.mark.parametrize("status", ["corrupt", "", None, "ACCEPTED"])
def test_resolved_refuses_a_status_it_does_not_know(status):
    """Reading a file checks each field, and building a Group in Python does not."""
    group = Group(id=1, members=["a_1"], proposed="a1", final="a1", status=status)
    with pytest.raises(ValueError, match="which is not one of"):
        group.resolved()


@pytest.mark.parametrize("final", ["", "   ", None, 7])
def test_resolved_refuses_to_rename_a_member_to_nothing(final):
    group = Group(id=1, members=["a_1"], proposed="a1", final=final, status=STATUS_ACCEPTED)
    with pytest.raises(ValueError, match="must be a string that holds a character"):
        group.resolved()


@pytest.mark.parametrize("members", ["AB", "", None, 7, ["a_1", ""], ["a_1", None], []])
def test_resolved_refuses_members_that_cannot_name_a_sample(members):
    """A string is iterable, so members of "AB" read as the two samples A and B
    everywhere that a list is expected."""
    group = Group(id=1, members=members, proposed="a1", final="a1",
                  status=STATUS_ACCEPTED)
    with pytest.raises(ValueError):
        group.resolved()


def test_one_method_holds_every_check():
    """The file reader and the Python API call the same validator, so the two
    cannot drift apart about what a valid group is."""
    good = Group(id=1, members=["a_1"], proposed="a1", final="a1",
                 status=STATUS_ACCEPTED)
    good.validate()

    from_file = Group.from_dict(good.to_dict())
    from_file.validate()
    assert from_file.to_dict() == good.to_dict()


@pytest.mark.parametrize("entry", [None, "text", 7, []])
def test_a_group_entry_that_is_not_an_object_is_refused(entry):
    """`"groups": [null]` raised a TypeError, and this class documents ValueError."""
    with pytest.raises(ValueError, match="A group is an object"):
        MappingFile.from_dict({"schema_version": 1, "groups": [entry]})


def test_a_name_claimed_by_two_groups_is_refused_in_memory():
    """Reading a file refuses this, and building a MappingFile in Python did not.

    `dict.update` let the last group win, so one group decided the name of the
    sample and the other was ignored in silence.
    """
    result = MappingFile(
        groups=[
            _group(1, ["patient1_batch1"], "first", STATUS_ACCEPTED),
            _group(2, ["patient1_batch1"], "second", STATUS_ACCEPTED),
        ]
    )
    with pytest.raises(ValueError, match="belongs to one group"):
        result.final_mapping()


def test_a_repeated_member_is_refused():
    """It misleads the person at the moment they decide.

    `rows` sums the occurrences once for each entry, so it doubles, and
    `is_merge` reads two entries as two names, so a group holding one name asks
    for a decision that has nothing in it.
    """
    group = Group(
        id=1, members=["sample_1", "sample_1"], proposed="sample1",
        final="sample1", status=STATUS_ACCEPTED, occurrences={"sample_1": 3},
    )
    with pytest.raises(ValueError, match="more than once"):
        group.validate()
    with pytest.raises(ValueError, match="more than once"):
        group.resolved()


def test_validate_checks_the_id_as_the_file_reader_does():
    """`Group(id=True)` validated and resolved through the Python API.

    bool is a subclass of int in Python, so the id has to be refused by name.
    """
    group = Group(id=True, members=["a_1"], proposed="a1", final="a1",
                  status=STATUS_ACCEPTED)
    with pytest.raises(ValueError, match="An id must be a number"):
        group.validate()
    with pytest.raises(ValueError, match="An id must be a number"):
        group.resolved()


def test_occurrences_must_be_an_object():
    """`dict(None)` raises a TypeError, and this class documents ValueError."""
    group = Group(id=1, members=["a_1"], proposed="a1", final="a1",
                  status=STATUS_ACCEPTED, occurrences=None)
    with pytest.raises(ValueError, match="must be an object"):
        group.validate()

    # A file that omits the field, or holds null for it, reads as empty.
    restored = Group.from_dict(
        {"id": 1, "members": ["a_1"], "proposed": "a1", "final": "a1",
         "status": STATUS_ACCEPTED, "occurrences": None}
    )
    assert restored.occurrences == {}


@pytest.mark.parametrize("count", [None, -1, True, "two", 1.5])
def test_a_count_of_rows_must_be_a_whole_number(count):
    """`rows` sums these, and a null count crashed the sum with a TypeError
    rather than refusing the file. The review step prints that number."""
    group = Group(id=1, members=["s_1"], proposed="s1", final="s1",
                  status=STATUS_ACCEPTED, occurrences={"s_1": count})
    with pytest.raises(ValueError, match="count of rows"):
        group.validate()


def test_an_ordinary_count_is_accepted():
    group = Group(id=1, members=["s_1"], proposed="s1", final="s1",
                  status=STATUS_ACCEPTED, occurrences={"s_1": 2})
    group.validate()
    assert group.rows == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("near_misses", True),
        ("near_misses", 7),
        ("near_misses", "text"),
        ("near_misses", [["only one"]]),
        ("near_misses", ["not a pair"]),
        ("diagnosis", True),
        ("diagnosis", 7),
        ("diagnosis", []),
    ],
)
def test_a_malformed_top_level_field_is_refused(field, value):
    """`list(None)` and `dict(None)` raise a TypeError, and this class documents
    ValueError, so a caller had to catch two kinds of error for one file."""
    with pytest.raises(ValueError):
        MappingFile.from_dict({"schema_version": 1, "groups": [], field: value})


@pytest.mark.parametrize("field", ["near_misses", "diagnosis"])
def test_a_null_top_level_field_reads_as_empty(field):
    """A file that omits the field and a file that holds null read alike."""
    result = MappingFile.from_dict({"schema_version": 1, "groups": [], field: None})
    assert getattr(result, field) in ([], {})


def test_no_malformed_mapping_file_reaches_the_user_as_a_traceback(tmp_path):
    """Every command answers a malformed file with a message and exit code 1."""
    documents = [
        "[]", "null", "7", '"text"', "{}", "not json at all",
        '{"schema_version": 2, "groups": []}',
        '{"schema_version": 1}',
        '{"schema_version": 1, "groups": [null]}',
        '{"schema_version": 1, "groups": {}}',
        '{"schema_version": 1, "groups": [], "reviewed": "yes"}',
        '{"schema_version": 1, "groups": [], "near_misses": null}',
        '{"schema_version": 1, "groups": [], "near_misses": 7}',
        '{"schema_version": 1, "groups": [], "diagnosis": 7}',
    ]
    for index, document in enumerate(documents):
        path = tmp_path / f"{index}.json"
        path.write_text(document)
        for command in (
            ["review", str(path)],
            ["apply", str(path)],
            ["plot", str(path), "-o", str(tmp_path / "q.png")],
        ):
            assert cli.main(command) in (0, 1), (command[0], document)


@pytest.mark.parametrize(
    "field",
    ["input_file", "column", "model", "provider", "base_url",
     "canonical_pattern", "method", "created", "reviewed_at"],
)
@pytest.mark.parametrize("value", [1, True, [], {}, 3.5])
def test_every_text_field_of_a_mapping_file_must_be_text(field, value):
    """`Path(1)` raises a TypeError further down, and this class documents
    ValueError, so `apply` showed a traceback for a malformed mapping."""
    with pytest.raises(ValueError, match="must be text"):
        MappingFile.from_dict({"schema_version": 1, "groups": [], field: value})


@pytest.mark.parametrize("field", ["input_file", "column", "model", "base_url"])
def test_a_null_text_field_reads_as_absent(field):
    result = MappingFile.from_dict({"schema_version": 1, "groups": [], field: None})
    assert getattr(result, field) is None


def test_apply_refuses_a_mapping_whose_input_file_is_not_text(tmp_path, capsys):
    path = tmp_path / "mapping.json"
    path.write_text('{"schema_version":1,"groups":[],"input_file":1,"column":"sample_id"}')
    assert cli.main(["apply", str(path)]) == 1
    assert "must be text" in " ".join(capsys.readouterr().out.split())


def test_no_shape_of_any_field_answers_with_the_wrong_error():
    """One sweep over every field of a mapping file and every wrong shape.

    Reviews reported one field at a time for four passes. This asserts the
    whole surface at once: a malformed value answers with ValueError and never
    with a TypeError, an AttributeError or anything else.
    """
    group = {"id": 1, "members": ["s_1"], "proposed": "s1", "final": "s1",
             "status": STATUS_ACCEPTED}
    base = {"schema_version": 1, "groups": [group]}
    shapes = [None, True, False, 0, 1, -1, 3.5, "", "text", [], {}, [[]], [None],
              {"a": None}]
    fields = ("schema_version", "groups", "reviewed", "method", "model", "provider",
              "base_url", "input_file", "column", "near_misses", "diagnosis",
              "canonical_pattern", "created", "reviewed_at")

    for field in fields:
        for shape in shapes:
            document = dict(base)
            document[field] = shape
            try:
                MappingFile.from_dict(document)
            except ValueError:
                pass
            except Exception as exc:  # noqa: BLE001 - the point of the test
                raise AssertionError(
                    f"{field}={shape!r} raised {type(exc).__name__}: {exc}"
                ) from exc


@pytest.mark.parametrize("value", [1, "", None, [], True])
def test_a_group_names_its_method_in_text(value):
    group = Group(id=1, members=["s_1"], proposed="s1", final="s1",
                  status=STATUS_ACCEPTED, method=value)
    with pytest.raises(ValueError, match="must be text"):
        group.validate()


@pytest.mark.parametrize("value", ["x", 1.5, -0.1, True, []])
def test_a_recorded_similarity_is_a_ratio(value):
    """The review step prints this number to the person who is deciding."""
    group = Group(id=1, members=["s_1"], proposed="s1", final="s1",
                  status=STATUS_ACCEPTED, min_similarity=value)
    with pytest.raises(ValueError, match="ratio between 0.0 and 1.0"):
        group.validate()


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0, 1, None])
def test_an_ordinary_similarity_is_accepted(value):
    group = Group(id=1, members=["s_1"], proposed="s1", final="s1",
                  status=STATUS_ACCEPTED, min_similarity=value)
    group.validate()


def test_no_shape_of_any_group_field_answers_with_the_wrong_error():
    """The same sweep as the mapping file, for every field of a group."""
    shapes = [None, True, False, 0, 1, -1, 3.5, "", "text", [], {}, ["a", None]]
    base = {"id": 1, "members": ["s_1"], "proposed": "s1", "final": "s1",
            "status": STATUS_ACCEPTED, "occurrences": {"s_1": 1},
            "method": "damerau", "min_similarity": 0.9}

    for field in base:
        for shape in shapes:
            document = dict(base)
            document[field] = shape
            try:
                Group.from_dict(document).validate()
            except ValueError:
                pass
            except Exception as exc:  # noqa: BLE001 - the point of the test
                raise AssertionError(
                    f"{field}={shape!r} raised {type(exc).__name__}: {exc}"
                ) from exc


@pytest.mark.parametrize("value", [False, 0, "", [], "text", 7])
def test_a_falsey_occurrences_is_refused_and_not_read_as_empty(value):
    """`data.get("occurrences") or {}` turned False into an empty object, so a
    malformed file passed as a valid one."""
    document = {
        "id": 1, "members": ["s_1"], "proposed": "s1", "final": "s1",
        "status": STATUS_ACCEPTED, "occurrences": value,
    }
    with pytest.raises(ValueError):
        Group.from_dict(document)
