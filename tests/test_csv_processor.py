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

from samplify.csv_processor import diagnose, harmonize_csv


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
