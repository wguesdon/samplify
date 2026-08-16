"""
Tests for samplify csv_processor module.

Unit tests run without any API calls.
Live tests are marked @pytest.mark.live and require OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from samplify import mapping as mapping_module
from samplify.csv_processor import apply_mapping, diagnose, harmonize_csv, propose, propose_csv
from samplify.mapping import MappingFile


# ── Unit tests (no API) ────────────────────────────────────────────────────


def test_diagnose_mixed_delimiters():
    names = ["sample-1-batch1", "sample_2_batch1", "sample-3-batch2"]
    findings = diagnose(names)
    assert findings["delimiter_mix"] is True
    assert findings["verdict"] == "inconsistencies_found"


def test_diagnose_abbreviations():
    names = ["b1_ctrl_rep1", "b2_ctrl_rep2"]
    findings = diagnose(names)
    abbrevs = findings["abbreviations_detected"]
    # b1 should trigger batch abbreviation, ctrl should trigger control
    assert any("batch" in a for a in abbrevs), f"Expected batch abbrev, got: {abbrevs}"
    assert any("control" in a for a in abbrevs), f"Expected control abbrev, got: {abbrevs}"
    assert findings["verdict"] == "inconsistencies_found"


def test_diagnose_zero_padding():
    names = ["sample01_batch1", "sample1_batch2"]
    findings = diagnose(names)
    assert findings["zero_padding"] is True
    assert findings["verdict"] == "inconsistencies_found"


def test_diagnose_case_mix():
    names = ["Sample_1_Batch1", "sample_2_batch1"]
    findings = diagnose(names)
    assert findings["case_mix"] is True
    assert findings["verdict"] == "inconsistencies_found"


def test_diagnose_consistent():
    names = ["sample_1_batch_1", "sample_2_batch_1", "sample_3_batch_2"]
    findings = diagnose(names)
    assert findings["delimiter_mix"] is False
    assert findings["zero_padding"] is False
    assert findings["case_mix"] is False
    # Abbreviations may or may not be found; check verdict only when no others triggered
    if not findings["abbreviations_detected"]:
        assert findings["verdict"] == "appears_consistent"


def test_diagnose_empty():
    findings = diagnose([])
    assert findings["verdict"] == "appears_consistent"
    assert findings["delimiter_mix"] is False
    assert findings["abbreviations_detected"] == []


def test_harmonize_csv_mock(tmp_path):
    """harmonize_csv adds canonical column and builds correct log structure."""
    # Create a temp CSV
    csv_path = tmp_path / "samples.csv"
    df_input = pd.DataFrame(
        {
            "sample_id": ["s1-b1", "s1_batch2", "s1-b1", "s2_batch1"],
            "value": [10, 20, 30, 40],
        }
    )
    df_input.to_csv(csv_path, index=False)

    mock_harmonize_result = {
        "canonical_pattern": "sample{n}_batch{m}",
        "mapping": {
            "s1-b1": "sample1_batch1",
            "s1_batch2": "sample1_batch2",
            "s2_batch1": "sample2_batch1",
        },
    }

    with patch("samplify.csv_processor.harmonize", return_value=mock_harmonize_result):
        df_out, log = harmonize_csv(
            csv_path,
            "sample_id",
            api_key="fake-key",
        )

    # Canonical column present
    assert "sample_id_canonical" in df_out.columns
    assert df_out["sample_id_canonical"].tolist() == [
        "sample1_batch1",
        "sample1_batch2",
        "sample1_batch1",
        "sample2_batch1",
    ]

    # Log structure
    assert "timestamp" in log
    assert log["column"] == "sample_id"
    assert log["canonical_column"] == "sample_id_canonical"
    assert log["summary"]["total_rows"] == 4
    assert log["summary"]["unique_names"] == 3
    assert isinstance(log["changes"], list)
    assert len(log["changes"]) == 3
    for change in log["changes"]:
        assert "original" in change
        assert "canonical" in change
        assert "changed" in change
        assert "occurrences" in change


def test_harmonize_csv_custom_canonical_column(tmp_path):
    csv_path = tmp_path / "samples.csv"
    df_input = pd.DataFrame({"sid": ["sample_1", "sample_2"]})
    df_input.to_csv(csv_path, index=False)

    consistent_diagnose = {
        "delimiter_mix": False,
        "abbreviations_detected": [],
        "zero_padding": False,
        "case_mix": False,
        "verdict": "appears_consistent",
    }
    with patch("samplify.csv_processor.diagnose", return_value=consistent_diagnose):
        df_out, log = harmonize_csv(csv_path, "sid", canonical_column="sid_norm")

    assert "sid_norm" in df_out.columns
    assert log["canonical_column"] == "sid_norm"


def test_harmonize_csv_missing_column(tmp_path):
    csv_path = tmp_path / "samples.csv"
    pd.DataFrame({"other_col": ["a", "b"]}).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="Column 'sample_id' not found"):
        harmonize_csv(csv_path, "sample_id")


def test_harmonize_csv_writes_outputs(tmp_path):
    csv_path = tmp_path / "samples.csv"
    df_input = pd.DataFrame({"sample_id": ["sample_1", "sample_2"]})
    df_input.to_csv(csv_path, index=False)

    out_csv = tmp_path / "out.csv"
    out_json = tmp_path / "log.json"
    out_csv_log = tmp_path / "log.csv"

    consistent_diagnose = {
        "delimiter_mix": False,
        "abbreviations_detected": [],
        "zero_padding": False,
        "case_mix": False,
        "verdict": "appears_consistent",
    }
    with patch("samplify.csv_processor.diagnose", return_value=consistent_diagnose):
        harmonize_csv(
            csv_path,
            "sample_id",
            output_path=out_csv,
            json_log_path=out_json,
            csv_log_path=out_csv_log,
        )

    assert out_csv.exists()
    assert out_json.exists()
    assert out_csv_log.exists()

    with open(out_json) as fh:
        log_data = json.load(fh)
    assert "timestamp" in log_data
    assert "summary" in log_data

    log_df = pd.read_csv(out_csv_log)
    assert set(log_df.columns) >= {"original", "canonical", "changed", "occurrences"}


# ── Live tests (require real API key) ──────────────────────────────────────


@pytest.mark.live
def test_harmonize_csv_live(tmp_path):
    """Full pipeline with a real API call: check canonical column and log files."""
    csv_path = tmp_path / "samples.csv"
    df_input = pd.DataFrame(
        {
            "sample_id": [
                "sample_1_batch_1",
                "sample1_batch2",
                "sample-1-b3",
                "sample_2_batch_1",
            ],
            "measurement": [1.0, 2.0, 3.0, 4.0],
        }
    )
    df_input.to_csv(csv_path, index=False)

    out_csv = tmp_path / "out.csv"
    out_json = tmp_path / "log.json"
    out_csv_log = tmp_path / "log.csv"

    df_out, log = harmonize_csv(
        csv_path,
        "sample_id",
        output_path=out_csv,
        json_log_path=out_json,
        csv_log_path=out_csv_log,
    )

    # Canonical column is present
    assert "sample_id_canonical" in df_out.columns
    assert len(df_out) == 4

    # Output files exist
    assert out_csv.exists()
    assert out_json.exists()
    assert out_csv_log.exists()

    # JSON log has required keys
    with open(out_json) as fh:
        log_data = json.load(fh)
    for key in ("timestamp", "input_file", "column", "canonical_column", "model",
                "diagnosis", "canonical_pattern", "summary", "changes"):
        assert key in log_data, f"Missing key in JSON log: {key}"

    assert log_data["summary"]["total_rows"] == 4
    assert log_data["summary"]["unique_names"] == 3  # s-1-b3 shares sample_1_batch_1? No, 3 unique

    # CSV log has correct columns
    log_df = pd.read_csv(out_csv_log)
    assert set(log_df.columns) >= {"original", "canonical", "changed", "occurrences"}

    print("\nLive CSV harmonize result:")
    for _, row in log_df.iterrows():
        print(f"  {row['original']!r:30s} → {row['canonical']!r}  (changed={row['changed']})")


# ── propose and apply, offline (no API key needed) ─────────────────────────

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example"


def test_propose_csv_offline_groups_the_delimiter_variants():
    mapping = propose_csv(EXAMPLE_DIR / "delimiter_case.csv", "sample_id", method="rules")
    merges = mapping.merges()
    assert len(merges) == 1
    assert sorted(merges[0].members) == ["S1_B1", "s01_b01", "s1-b1"]
    assert merges[0].proposed == "sample1_batch1"


def test_propose_csv_offline_groups_the_typos():
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    merges = mapping.merges()
    assert len(merges) == 1
    assert merges[0].proposed == "patient1_batch1"
    assert len(merges[0].members) == 4


def test_propose_csv_never_merges_two_patient_numbers():
    mapping = propose_csv(EXAMPLE_DIR / "near_miss_trap.csv", "sample_id", method="damerau")
    assert mapping.merges() == []
    assert len(mapping.near_misses) == 2


def test_propose_csv_makes_no_model_call_on_a_clean_file():
    """auto skips the model when the heuristics find nothing and nothing clusters."""
    mapping = propose_csv(EXAMPLE_DIR / "clean_samples.csv", "sample_id", method="auto")
    assert mapping.model is None
    assert mapping.summary()["unchanged"] == 3


def test_propose_csv_records_the_input_and_column():
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="rules")
    assert mapping.column == "sample_id"
    assert mapping.input_file.endswith("typos.csv")


def test_propose_csv_counts_occurrences():
    mapping = propose_csv(EXAMPLE_DIR / "near_miss_trap.csv", "sample_id", method="rules")
    counts = {m: g.occurrences[m] for g in mapping.groups for m in g.members}
    assert counts["patient11_batch1"] == 2
    assert counts["patient112_batch1"] == 1


def test_propose_rejects_an_unknown_method():
    with pytest.raises(ValueError, match="Unknown method"):
        propose(["a"], method="fuzzy")


def test_apply_refuses_while_a_group_is_pending(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    with pytest.raises(ValueError, match="still proposed"):
        apply_mapping(mapping, output_path=tmp_path / "out.csv")


def test_apply_refuses_an_unreviewed_collision(tmp_path):
    """Two groups landing on one name is a silent merge, so it stops."""
    mapping = propose_csv(EXAMPLE_DIR / "near_miss_trap.csv", "sample_id", method="rules")
    mapping.accept_all()
    for group in mapping.groups:
        group.final = "one_name_for_everything"

    with pytest.raises(ValueError, match="more than one group"):
        apply_mapping(mapping, output_path=tmp_path / "out.csv")


def test_apply_allows_a_collision_a_person_reviewed(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "near_miss_trap.csv", "sample_id", method="rules")
    mapping.accept_all()
    for group in mapping.groups:
        group.final = "one_name_for_everything"
    mapping.mark_reviewed()

    df, _log = apply_mapping(mapping, output_path=tmp_path / "out.csv")
    assert set(df["sample_id_canonical"]) == {"one_name_for_everything"}


def test_apply_keeps_the_original_column(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "delimiter_case.csv", "sample_id", method="rules")
    mapping.accept_all()
    df, _log = apply_mapping(mapping, output_path=tmp_path / "out.csv")

    assert "sample_id" in df.columns
    assert df["sample_id"].tolist() == ["S1_B1", "s1-b1", "s01_b01", "S2_B1", "s2-b2"]
    assert df["sample_id_canonical"].tolist() == [
        "sample1_batch1",
        "sample1_batch1",
        "sample1_batch1",
        "sample2_batch1",
        "sample2_batch2",
    ]


def test_apply_honours_a_rejected_group(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "delimiter_case.csv", "sample_id", method="rules")
    mapping.accept_all()
    for group in mapping.merges():
        group.status = "rejected"
    mapping.mark_reviewed()

    df, _log = apply_mapping(mapping, output_path=tmp_path / "out.csv")
    assert df.loc[0, "sample_id_canonical"] == "S1_B1"


def test_apply_is_deterministic(tmp_path):
    """The claim the whole design rests on: no model call, same bytes every time."""
    mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="damerau")
    mapping.accept_all()

    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    apply_mapping(mapping, output_path=first)
    apply_mapping(mapping, output_path=second)

    assert first.read_bytes() == second.read_bytes()


def test_apply_reload_from_disk_is_deterministic(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="damerau")
    mapping.accept_all()
    path = mapping_module.write(mapping, tmp_path / "m.json")

    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    apply_mapping(mapping, output_path=first)
    apply_mapping(mapping_module.read(path), output_path=second)

    assert first.read_bytes() == second.read_bytes()


def test_apply_needs_a_column_when_the_mapping_records_none(tmp_path):
    mapping = MappingFile(groups=[], input_file=str(EXAMPLE_DIR / "typos.csv"))
    with pytest.raises(ValueError, match="No column given"):
        apply_mapping(mapping, output_path=tmp_path / "out.csv")


def test_catalogue_recovers_the_ground_truth():
    """example/mislabel_catalogue.csv carries its own answer in the true_sample column."""
    truth = pd.read_csv(EXAMPLE_DIR / "mislabel_catalogue.csv")
    expected = dict(zip(truth["sample_id"], truth["true_sample"]))

    mapping = propose_csv(EXAMPLE_DIR / "mislabel_catalogue.csv", "sample_id", method="damerau")

    assert len(mapping.groups) == truth["true_sample"].nunique()
    for group in mapping.groups:
        truths = {expected[member] for member in group.members}
        assert len(truths) == 1, f"group {group.id} mixes {truths}"


def test_catalogue_reports_the_added_digit():
    mapping = propose_csv(EXAMPLE_DIR / "mislabel_catalogue.csv", "sample_id", method="damerau")
    assert mapping.near_misses == [["sample_10", "sample_100"]]


def test_apply_log_records_that_nobody_reviewed(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    mapping.accept_all()
    _df, log = apply_mapping(mapping, output_path=tmp_path / "out.csv")
    assert log["reviewed"] is False
    assert log["method"] == "damerau"
