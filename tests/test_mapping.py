"""Tests for the mapping file: the artifact a person reviews.

The guards here are the ones that stop a silent merge. A group without a
decision must block the apply step, and two groups that land on one canonical
name must block it too unless a person looked at them.
"""

from __future__ import annotations

import json

import pytest

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
