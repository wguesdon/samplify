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
from samplify import matching
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


# ── The model-backed backends, with the model replaced ─────────────────────


def test_llm_groups_the_names_the_model_joins(tmp_path):
    csv_path = tmp_path / "names.csv"
    csv_path.write_text("sample_id,value\nS1_B1,1\ns1-b1,2\nP2_B1,3\n")
    answer = {
        "canonical_pattern": "patientN_batchN",
        "mapping": {
            "S1_B1": "patient1_batch1",
            "s1-b1": "patient1_batch1",
            "P2_B1": "patient2_batch1",
        },
    }

    with patch("samplify.csv_processor.harmonize", return_value=answer):
        mapping = propose_csv(
            csv_path, "sample_id", method="llm", api_key="fake-key", model="acme/model-1"
        )

    assert len(mapping.groups) == 2
    assert mapping.model == "acme/model-1"
    merged = [group for group in mapping.groups if len(group.members) == 2][0]
    assert merged.members == ["S1_B1", "s1-b1"]
    assert merged.proposed == "patient1_batch1"


def test_auto_sends_one_name_for_each_offline_cluster():
    """The request holds the 8 representatives, not the 22 names in the file."""
    seen = {}

    def _fake_model(names, **kwargs):
        seen["names"] = list(names)
        return {"canonical_pattern": "", "mapping": {name: name for name in names}}

    with patch("samplify.csv_processor.harmonize", side_effect=_fake_model):
        mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="auto")

    assert len(seen["names"]) == 8
    assert len(mapping.groups) == 8


def test_the_mapping_file_records_the_provider_and_the_model(tmp_path):
    """A person reading the file must see which service answered."""
    csv_path = tmp_path / "names.csv"
    csv_path.write_text("sample_id,value\nS1_B1,1\ns1-b1,2\n")
    answer = {"canonical_pattern": "", "mapping": {"S1_B1": "s1_b1", "s1-b1": "s1_b1"}}

    with patch("samplify.csv_processor.harmonize", return_value=answer) as fake:
        mapping = propose_csv(
            csv_path, "sample_id", method="llm", provider="ollama", model="qwen3.5:9b"
        )

    assert fake.call_args.kwargs["provider"] == "ollama"
    assert mapping.provider == "ollama"
    assert mapping.model == "qwen3.5:9b"
    assert mapping.to_dict()["provider"] == "ollama"


def test_an_offline_method_records_no_provider():
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    assert mapping.provider is None
    assert mapping.model is None


def test_auto_refuses_a_model_merge_across_two_numbers(tmp_path):
    """The identity rule outranks the model, and the refused half keeps its name.

    Giving the model's canonical name to both halves would rename patient112 to
    patient111 at the apply step, which is the merge that the split prevented.
    """
    csv_path = tmp_path / "patients.csv"
    csv_path.write_text(
        "sample_id,value\nP111_B1,1\npatient111_batch1,2\npatient112_batch1,3\n"
    )

    def _fake_model(names, **kwargs):
        return {
            "canonical_pattern": "",
            "mapping": {name: "patient111_batch1" for name in names},
        }

    with patch("samplify.csv_processor.harmonize", side_effect=_fake_model):
        mapping = propose_csv(csv_path, "sample_id", method="auto")

    assert len(mapping.groups) == 2
    assert {group.proposed for group in mapping.groups} == {
        "patient111_batch1",
        "patient112_batch1",
    }
    assert mapping.collisions() == {}


# ── The review findings of 2026-08-18 ──────────────────────────────────────


def _accepted(path: Path, column: str = "sample_id") -> MappingFile:
    result = propose_csv(path, column, method="damerau")
    result.accept_all()
    return result


def test_zero_padding_survives_the_round_trip(tmp_path):
    """pandas read 007 as the number 7 and wrote 7 back into the source column."""
    source = tmp_path / "padded.csv"
    source.write_text("sample_id,value\n007,1\n007,2\n008,3\n")

    result = _accepted(source)
    output = tmp_path / "out.csv"
    apply_mapping(result, output_path=output)

    written = pd.read_csv(output, dtype=str)
    assert list(written["sample_id"]) == ["007", "007", "008"]


def test_a_sample_named_na_is_kept(tmp_path):
    """dropna deleted the sample, and apply wrote an empty cell in its place."""
    source = tmp_path / "na.csv"
    source.write_text("sample_id,value\nNA,1\nsample_1,2\n")

    result = _accepted(source)
    assert ["NA"] in [g.members for g in result.groups]

    output = tmp_path / "out.csv"
    apply_mapping(result, output_path=output)
    written = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert list(written["sample_id"]) == ["NA", "sample_1"]


def test_an_empty_cell_forms_no_group(tmp_path):
    source = tmp_path / "blank.csv"
    source.write_text("sample_id\n\nsample_1\n")

    result = propose_csv(source, "sample_id", method="damerau")
    assert [g.members for g in result.groups] == [["sample_1"]]


def test_apply_refuses_the_source_column_as_the_canonical_column(tmp_path):
    """This overwrote the original spelling, which apply must never do."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    result = _accepted(source)

    with pytest.raises(ValueError, match="both"):
        apply_mapping(result, canonical_column="sample_id")


def test_apply_refuses_to_overwrite_an_existing_column(tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("sample_id,sample_id_canonical\nS1_B1,old\ns1-b1,old\n")
    result = propose_csv(source, "sample_id", method="damerau")
    result.accept_all()

    with pytest.raises(ValueError, match="already holds a column"):
        apply_mapping(result)


def test_apply_refuses_a_csv_that_shares_no_name_with_the_mapping(tmp_path):
    """Applying to the wrong file changed nothing and reported every name changed."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    result = _accepted(source)

    other = tmp_path / "other.csv"
    other.write_text("sample_id\nPATIENT_99\nX_1\n")

    with pytest.raises(ValueError, match="No name of the mapping appears"):
        apply_mapping(result, data_path=other, column="sample_id")


def test_the_log_counts_the_rows_that_changed(tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\nsample1_batch1\n")
    result = _accepted(source)

    _, log = apply_mapping(result)
    assert log["summary"]["rows_changed"] == 2
    assert log["summary"]["total_rows"] == 3


def test_a_duplicate_column_name_is_refused(tmp_path):
    """pandas renames the second column, so half the names were invisible."""
    source = tmp_path / "dup.csv"
    source.write_text("sample_id,sample_id\nA_1,B_1\n")

    with pytest.raises(ValueError, match="appears 2 times"):
        propose_csv(source, "sample_id", method="damerau")


def test_the_llm_backend_keeps_two_numbers_apart():
    """The identity rule guarded the auto backend and not the llm backend."""
    answer = {
        "canonical_pattern": "patient<n>",
        "mapping": {"p111": "patient111", "p112": "patient111"},
    }
    with patch("samplify.csv_processor.harmonize", return_value=answer):
        result = propose(["p111", "p112"], method="llm", api_key="test")

    assert [g.members for g in result.groups] == [["p111"], ["p112"]]
    assert sorted(g.proposed for g in result.groups) == ["patient111", "patient112"]


# ── The review findings of 2026-08-18, second pass ─────────────────────────


def _answer(mapping: dict) -> dict:
    return {"canonical_pattern": "", "mapping": mapping}


@pytest.mark.parametrize("method", ["llm", "auto"])
def test_the_model_may_not_merge_across_a_substituted_letter(method):
    """The offline path refuses this merge, so the model path must too.

    Both names carry no digit, so the identity signature is empty for each and
    the digit guard alone lets them through. Primary B cells and Primary T
    cells are the two major lymphocyte lineages.
    """
    names = ["Primary B cells", "Primary T cells"]
    keys = names if method == "llm" else ["primary_b_cells", "primary_t_cells"]

    with patch("samplify.csv_processor.harmonize",
               return_value=_answer({k: "primary_cells" for k in keys})):
        result = propose(names, method=method, api_key="test")

    assert [g.members for g in result.groups] == [["Primary B cells"], ["Primary T cells"]]


@pytest.mark.parametrize("method", ["llm", "auto"])
def test_the_model_may_still_join_two_spellings_of_one_word(method):
    """The rule blocks a substitution and nothing else.

    ctrl and control are three edits apart, so no rule refuses them, and
    joining them is the reason the model backends exist.
    """
    names = ["ctrl_1", "control_1", "CONTROL-1"]
    keys = names if method == "llm" else ["ctrl1", "control1"]

    with patch("samplify.csv_processor.harmonize",
               return_value=_answer({k: "control_1" for k in keys})):
        result = propose(names, method=method, api_key="test")

    assert len(result.groups) == 1
    assert result.groups[0].proposed == "control_1"


@pytest.mark.parametrize(
    "answer",
    [
        '{"mapping": {"control": null}}',
        '{"mapping": {"control": 7}}',
        '{"mapping": {"control": "   "}}',
        '{"mapping": ["control"]}',
    ],
)
def test_a_canonical_name_the_model_returns_must_be_a_name(answer):
    """str(None) gives the string None, and a group would take those four
    characters as its sample name."""
    from samplify.harmonizer import _parse_answer

    with pytest.raises(ValueError):
        _parse_answer(answer, ["control"])


def test_the_log_records_a_collision_that_apply_allowed(tmp_path):
    """A reviewed mapping may join two groups, and it may not do so in silence.

    Joining two groups into one name is the most consequential thing this tool
    does. apply refuses it in a mapping no person reviewed, and it allows it in
    a reviewed one, so the reviewed case has to reach the log and the console.
    """
    source = tmp_path / "in.csv"
    source.write_text("sample_id\npatient11_batch1\npatient111_batch1\n")

    mapping = MappingFile(
        groups=[
            mapping_module.Group(
                id=1, members=["patient11_batch1"], proposed="patient11_batch1",
                final="patient11_batch1", status="accepted",
                occurrences={"patient11_batch1": 1},
            ),
            mapping_module.Group(
                id=2, members=["patient111_batch1"], proposed="patient111_batch1",
                final="patient11_batch1", status="accepted",
                occurrences={"patient111_batch1": 1},
            ),
        ],
        input_file=str(source), column="sample_id", reviewed=True,
    )

    _, log = apply_mapping(mapping)
    assert log["collisions"] == {"patient11_batch1": [1, 2]}


def test_the_log_holds_no_collision_when_there_is_none(tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = _accepted(source)
    _, log = apply_mapping(mapping)
    assert log["collisions"] == {}


@pytest.mark.parametrize("reviewed", ["false", "true", 1, [], None, 0])
def test_only_a_real_true_lets_a_collision_through(tmp_path, reviewed):
    """Reading a file refuses anything but a boolean, and the Python API cannot.

    A MappingFile built in code carried the string "false", which is truthy, and
    the collision guard read it as permission and merged two patients.
    """
    source = tmp_path / "in.csv"
    source.write_text("sample_id\npatient11_batch1\npatient112_batch1\n")

    mapping = MappingFile(
        groups=[
            mapping_module.Group(
                id=1, members=["patient11_batch1"], proposed="one", final="one",
                status="accepted", occurrences={"patient11_batch1": 1},
            ),
            mapping_module.Group(
                id=2, members=["patient112_batch1"], proposed="one", final="one",
                status="accepted", occurrences={"patient112_batch1": 1},
            ),
        ],
        input_file=str(source), column="sample_id", reviewed=reviewed,
    )

    with pytest.raises(ValueError, match="more than one group"):
        apply_mapping(mapping)


def test_a_real_true_still_lets_a_collision_through(tmp_path):
    """A person who signed for the merge is still obeyed."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id\npatient11_batch1\npatient112_batch1\n")
    mapping = MappingFile(
        groups=[
            mapping_module.Group(
                id=1, members=["patient11_batch1"], proposed="one", final="one",
                status="accepted", occurrences={"patient11_batch1": 1},
            ),
            mapping_module.Group(
                id=2, members=["patient112_batch1"], proposed="one", final="one",
                status="accepted", occurrences={"patient112_batch1": 1},
            ),
        ],
        input_file=str(source), column="sample_id", reviewed=True,
    )
    _, log = apply_mapping(mapping)
    assert log["collisions"] == {"one": [1, 2]}


def test_a_file_that_excel_wrote_is_read(tmp_path):
    """Excel writes a byte order mark and CRLF line endings."""
    source = tmp_path / "excel.csv"
    source.write_bytes("﻿sample_id,value\r\nS1_B1,1\r\ns1-b1,2\r\n".encode("utf-8"))

    mapping = propose_csv(source, "sample_id", method="damerau")
    assert [g.members for g in mapping.groups] == [["S1_B1", "s1-b1"]]


def test_a_duplicate_column_is_refused_behind_a_byte_order_mark(tmp_path):
    """pandas strips the mark and the default encoding does not.

    The two readers disagreed about the first column name, so the duplicate
    check read `\\ufeffsample_id`, counted one `sample_id`, and passed a file
    that holds the column twice. pandas then renamed the second one and half
    the names were invisible.
    """
    source = tmp_path / "excel_dup.csv"
    source.write_bytes("﻿sample_id,sample_id\r\nA_1,B_1\r\n".encode("utf-8"))

    with pytest.raises(ValueError, match="appears 2 times"):
        propose_csv(source, "sample_id", method="damerau")


def test_the_change_log_describes_what_the_output_did(tmp_path):
    """The CSV log is a record a person reads instead of the whole output.

    Every row of it has to match the output, and every count in it has to match
    the input, or the record is worse than none.
    """
    import csv as csv_module

    source = EXAMPLE_DIR / "cohort_messy.csv"
    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()

    output = tmp_path / "clean.csv"
    log_path = tmp_path / "changes.csv"
    _, log = apply_mapping(mapping, output_path=output, csv_log_path=log_path)

    written = pd.read_csv(output, dtype=str, keep_default_na=False)
    original = pd.read_csv(source, dtype=str, keep_default_na=False)
    changes = {row["original"]: row for row in csv_module.DictReader(open(log_path))}

    for name, canonical in zip(written["sample_id"], written["sample_id_canonical"]):
        assert name in changes, name
        assert changes[name]["canonical"] == canonical

    counts = original["sample_id"].value_counts().to_dict()
    for name, row in changes.items():
        assert int(row["occurrences"]) == counts[name], name

    rows_changed = int((written["sample_id"] != written["sample_id_canonical"]).sum())
    assert log["summary"]["rows_changed"] == rows_changed


@pytest.mark.parametrize("option", ["output_path", "json_log_path", "csv_log_path"])
def test_apply_writes_no_output_over_its_own_input(tmp_path, option):
    """samplify promises that the input survives the run.

    One character of a shell command separates `--output clean.csv` from
    `--output data.csv`, and a log written over the input would lose the file
    completely.
    """
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = _accepted(source)

    with pytest.raises(ValueError, match="which is the input"):
        apply_mapping(mapping, **{option: source})

    assert source.read_text() == "sample_id\nS1_B1\ns1-b1\n"


def test_apply_writes_to_another_path_as_before(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = _accepted(source)

    output = tmp_path / "clean.csv"
    apply_mapping(mapping, output_path=output, csv_log_path=tmp_path / "changes.csv")
    assert output.exists()
    assert source.read_text() == "sample_id\nS1_B1\ns1-b1\n"


@pytest.mark.parametrize("option", ["output_path", "json_log_path", "csv_log_path"])
def test_apply_writes_no_output_over_the_mapping_file(tmp_path, option):
    """This command reads two files, and neither survives being written over.

    The data CSV holds the original spelling and the mapping file holds the
    decisions a person made. The first was guarded and the second was not, so
    `apply mapping.json --output mapping.json` replaced a reviewed mapping with
    CSV data.
    """
    from samplify import mapping as mapping_module

    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping_file = tmp_path / "mapping.json"
    mapping = _accepted(source)
    mapping_module.write(mapping, mapping_file)
    before = mapping_file.read_text()

    with pytest.raises(ValueError, match="the mapping file"):
        apply_mapping(mapping, mapping_path=str(mapping_file),
                      **{option: mapping_file})

    assert mapping_file.read_text() == before


@pytest.mark.parametrize("method", ["llm", "auto"])
def test_the_model_paths_never_drop_a_name(method):
    """Two clusters can normalise to one representative.

    A plain dict then kept one of them and dropped the other, so a sample
    disappeared from the file a person reviews. `sampleI1` and `sampleİ1` are
    two identities that share the representative `samplei1`.
    """
    names = ["sampleI1", "sampleİ1", "patient1_batch1", "patietn1_batch1"]

    with patch("samplify.csv_processor.harmonize", return_value=_answer({})):
        result = propose(names, method=method, api_key="test")

    kept = sorted(member for group in result.groups for member in group.members)
    assert kept == sorted(names)
    for group in result.groups:
        signatures = {matching.digit_signature(m) for m in group.members}
        assert len(signatures) == 1, group.members


def test_two_groups_that_propose_one_name_are_refused_by_apply(tmp_path):
    """The two identities keep the same canonical name, and apply says so
    rather than joining them."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nsampleI1\nsampleİ1\n")

    with patch("samplify.csv_processor.harmonize", return_value=_answer({})):
        mapping = propose_csv(source, "sample_id", method="auto", api_key="test")
    mapping.accept_all()

    assert mapping.collisions() == {"samplei1": [1, 2]}
    with pytest.raises(ValueError, match="more than one group"):
        apply_mapping(mapping, output_path=tmp_path / "out.csv")


def test_a_mapping_read_from_a_file_remembers_where_it_came_from(tmp_path):
    """`apply` must refuse to write over the decisions even when the caller
    passes no path of its own, which a library caller has no way to do."""
    from samplify import mapping as mapping_module

    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    path = tmp_path / "mapping.json"
    mapping = _accepted(source)
    mapping_module.write(mapping, path)

    restored = mapping_module.read(path)
    assert restored.source_path == str(path)
    assert "source_path" not in restored.to_dict()

    before = path.read_text()
    with pytest.raises(ValueError, match="the mapping file"):
        apply_mapping(restored, output_path=path)
    assert path.read_text() == before

    # The ordinary path is untouched.
    apply_mapping(restored, output_path=tmp_path / "clean.csv")
    assert (tmp_path / "clean.csv").exists()


def test_a_tab_separated_file_says_why_it_cannot_be_read(tmp_path):
    """It reads as one column whose name holds every heading, and the list of
    available columns then shows one entry that looks like the header line."""
    source = tmp_path / "data.tsv"
    source.write_text("sample_id\tvalue\nS1_B1\t1\ns1-b1\t2\n")

    with pytest.raises(ValueError, match="separated by tabs"):
        propose_csv(source, "sample_id", method="damerau")


def test_an_ordinary_missing_column_still_lists_the_columns(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("sample_id,value\nS1_B1,1\n")

    with pytest.raises(ValueError, match="Available: \\['sample_id', 'value'\\]"):
        propose_csv(source, "absent", method="damerau")


@pytest.mark.parametrize("option", ["output_path", "json_log_path", "csv_log_path"])
def test_apply_writes_all_of_its_files_or_none_of_them(tmp_path, option):
    """A destination that cannot be written is found before the first write.

    The output CSV was written and then a log with a bad path failed, so the
    command reported an error while one of its files was already on disk.
    """
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = _accepted(source)

    destinations = {
        "output_path": tmp_path / "clean.csv",
        "json_log_path": tmp_path / "log.json",
        "csv_log_path": tmp_path / "changes.csv",
    }
    destinations[option] = tmp_path / "absent" / "file"

    with pytest.raises(ValueError, match="all of its files or none"):
        apply_mapping(mapping, **destinations)

    for path in destinations.values():
        assert not path.exists(), path


def test_apply_writes_all_three_when_every_path_is_good(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    mapping = _accepted(source)

    paths = {
        "output_path": tmp_path / "clean.csv",
        "json_log_path": tmp_path / "log.json",
        "csv_log_path": tmp_path / "changes.csv",
    }
    apply_mapping(mapping, **paths)
    for path in paths.values():
        assert path.exists(), path


def test_a_file_that_cannot_be_parsed_names_itself_and_the_cause(tmp_path):
    """A quote that is never closed gave a pandas traceback and no file name."""
    source = tmp_path / "broken.csv"
    source.write_text('sample_id,n\n"unclosed,1\nsample_2,2\n')

    with pytest.raises(ValueError) as error:
        propose_csv(source, "sample_id", method="damerau")

    message = str(error.value)
    assert "broken.csv" in message
    assert "quote" in message


def test_a_file_that_is_not_utf8_names_itself_and_the_option(tmp_path):
    """A spreadsheet on Windows writes cp1252, and the reader said only that.

    The message named a codec and a byte position, and no file and no way out.
    """
    source = tmp_path / "windows.csv"
    source.write_bytes(b"sample_id,note\nsample_1,caf\xe9\nsample_2,x\n")

    with pytest.raises(ValueError) as error:
        propose_csv(source, "sample_id", method="damerau")

    message = str(error.value)
    assert "windows.csv" in message
    assert "cp1252" in message


def test_the_encoding_of_the_input_is_the_encoding_of_the_output(tmp_path):
    """apply reads and writes one encoding, so no column it left alone changes."""
    source = tmp_path / "windows.csv"
    source.write_bytes(b"sample_id,note\nsample_1,caf\xe9\nsample-1,x\n")

    mapping = propose_csv(source, "sample_id", method="damerau", encoding="cp1252")
    assert mapping.encoding == "cp1252"
    mapping.accept_all()

    output = tmp_path / "out.csv"
    apply_mapping(mapping, output_path=output)

    written = output.read_bytes()
    assert b"caf\xe9" in written
    assert "café" in output.read_text(encoding="cp1252")


def test_the_encoding_survives_the_round_trip_through_the_mapping_file(tmp_path):
    """review writes the file and apply reads it, so the value must persist."""
    from samplify import mapping as mapping_module

    source = tmp_path / "windows.csv"
    source.write_bytes(b"sample_id\nsample_1\nsample-1\n")

    proposed = propose_csv(source, "sample_id", method="damerau", encoding="cp1252")
    proposed.accept_all()
    path = tmp_path / "mapping.json"
    mapping_module.write(proposed, path)

    read_back = mapping_module.read(path)
    assert read_back.encoding == "cp1252"


def test_a_mapping_file_naming_an_unknown_codec_is_refused(tmp_path):
    """The failure otherwise happened inside the reader and named no field."""
    from samplify import mapping as mapping_module

    source = tmp_path / "in.csv"
    source.write_text("sample_id\nsample_1\n")
    proposed = propose_csv(source, "sample_id", method="damerau")
    proposed.accept_all()
    path = tmp_path / "mapping.json"
    mapping_module.write(proposed, path)

    document = json.loads(path.read_text())
    document["encoding"] = "not-a-codec"
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="codec"):
        mapping_module.read(path)


def test_a_file_read_as_utf8_sig_is_not_written_with_a_byte_order_mark(tmp_path):
    """utf-8-sig strips a mark when it reads and adds one when it writes."""
    source = tmp_path / "plain.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n", encoding="utf-8")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    output = tmp_path / "out.csv"
    apply_mapping(mapping, output_path=output)

    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")


def test_a_row_with_more_values_than_the_header_is_refused(tmp_path):
    """pandas reads the first column as a row label, and the name is gone.

    The header `sample_id,other` with the row `s1,x,extra` produced the name
    `x`, and `s1` had become the label of the row.
    """
    source = tmp_path / "ragged.csv"
    source.write_text("sample_id,other\ns1,x,extra\n")

    with pytest.raises(ValueError) as error:
        propose_csv(source, "sample_id", method="damerau")

    message = str(error.value)
    assert "Line 2" in message
    assert "3 values" in message


def test_a_row_with_fewer_values_than_the_header_is_read(tmp_path):
    """The reader fills the missing place, and nothing the file held is lost."""
    source = tmp_path / "short.csv"
    source.write_text("sample_id,other\ns1\ns2,x\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    frame, _ = apply_mapping(mapping)

    assert list(frame["sample_id"]) == ["s1", "s2"]
    assert list(frame["other"]) == ["", "x"]


def test_a_nul_byte_in_any_column_is_refused(tmp_path):
    """The reader ends a value at the NUL and says nothing.

    A column samplify never touches reached the output cut short, which breaks
    the one promise the tool makes about the columns it does not write.
    """
    source = tmp_path / "binary.csv"
    source.write_bytes(b"sample_id,meta\ns1,a\x00b\n")

    with pytest.raises(ValueError) as error:
        propose_csv(source, "sample_id", method="damerau")

    assert "NUL" in str(error.value)


def test_no_file_is_written_when_a_destination_is_a_directory(tmp_path):
    """The output CSV is written first, so a bad log path left it on disk."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n")
    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()

    output = tmp_path / "out.csv"
    with pytest.raises(ValueError, match="directory"):
        apply_mapping(mapping, output_path=output, json_log_path=tmp_path)

    assert not output.exists()


def test_a_name_that_already_carries_a_canonical_name_is_reported(tmp_path):
    """A second file can hold a name that the mapping never saw.

    The mapping renames `sample_1` to `sample1`, and the second file already
    holds `sample1`. Both rows then read `sample1` although no person put the
    two names in one group. A reviewed mapping is reported and not refused,
    because a file already written in the canonical form is the usual reason.
    """
    source = tmp_path / "first.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n")
    second = tmp_path / "second.csv"
    second.write_text("sample_id\nsample_1\nsample1\nother_9\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    mapping.mark_reviewed()
    frame, log = apply_mapping(mapping, data_path=second)

    assert log["joined_without_a_decision"] == ["sample1"]
    assert log["summary"]["names_joined_without_a_decision"] == 1
    assert list(frame["sample_id_canonical"]) == ["sample1", "sample1", "other_9"]


def test_a_name_that_joins_a_group_is_refused_when_no_person_reviewed(tmp_path):
    """Two unchecked things would otherwise meet in one output.

    The names are in neither the mapping nor the review, and the mapping
    carries no signature either.
    """
    source = tmp_path / "first.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n")
    second = tmp_path / "second.csv"
    second.write_text("sample_id\nsample_1\nsample1\nother_9\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()

    with pytest.raises(ValueError) as error:
        apply_mapping(mapping, data_path=second)

    assert "sample1" in str(error.value)
    assert "reviewed=False" in str(error.value)


def test_the_unique_name_count_is_the_count_of_the_file(tmp_path):
    """A person reads it against the row count, so it reads the file.

    It reported the size of the mapping, so a run against a second file gave a
    count the file does not hold.
    """
    source = tmp_path / "first.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n")
    second = tmp_path / "second.csv"
    second.write_text("sample_id\nsample_1\nsample1\nother_9\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    mapping.mark_reviewed()
    _, log = apply_mapping(mapping, data_path=second)

    assert log["summary"]["total_rows"] == 3
    assert log["summary"]["unique_names"] == 3
    assert log["summary"]["names_in_the_mapping"] == 2


def test_nothing_is_reported_when_the_data_holds_no_such_name(tmp_path):
    """The usual run applies a mapping to the file it was built from."""
    source = tmp_path / "first.csv"
    source.write_text("sample_id\nsample_1\nsample-1\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    _, log = apply_mapping(mapping)

    assert log["joined_without_a_decision"] == []


def test_a_nul_byte_in_the_header_is_refused(tmp_path):
    """A NUL cuts a column name short, and the column asked for is not that one."""
    source = tmp_path / "binary.csv"
    source.write_bytes(b"sample_id\x00hidden,other\ns1,kept\n")

    with pytest.raises(ValueError, match="NUL"):
        propose_csv(source, "sample_id", method="damerau")


def test_the_line_number_of_a_ragged_row_counts_lines_and_not_rows(tmp_path):
    """A value that holds a newline makes one row of two lines.

    The number must be the line a person sees in an editor.
    """
    source = tmp_path / "multiline.csv"
    source.write_text('sample_id,note\ns1,"two\nlines"\ns2,x,extra\n')

    with pytest.raises(ValueError) as error:
        propose_csv(source, "sample_id", method="damerau")

    assert "Line 4" in str(error.value)


def test_a_repeated_column_name_reaches_the_output_as_it_arrived(tmp_path):
    """pandas renames the second one, and the header is part of the file.

    A header of `sample_id,note,note` reached the output as
    `sample_id,note,note.1`. The values were kept and the header was not.
    """
    source = tmp_path / "in.csv"
    source.write_text("sample_id,note,note\ns1,a,b\ns-1,c,d\n")

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    mapping.mark_reviewed()
    output = tmp_path / "out.csv"
    apply_mapping(mapping, output_path=output)

    lines = output.read_text().splitlines()
    assert lines[0] == "sample_id,note,note,sample_id_canonical"
    assert lines[1] == "s1,a,b,sample1"


def test_a_repeated_sample_column_is_still_refused(tmp_path):
    """Half the names would be invisible, so the header is not put back here."""
    source = tmp_path / "in.csv"
    source.write_text("sample_id,sample_id\ns1,s2\n")

    with pytest.raises(ValueError, match="appears 2 times"):
        propose_csv(source, "sample_id", method="damerau")


@pytest.mark.parametrize(
    "content,ending",
    [
        (b'sample_id,note\r\ns1,"two\r\nlines"\r\ns-1,plain\r\n', b"\r\n"),
        (b"sample_id,note\ns1,a\ns-1,b\n", b"\n"),
    ],
)
def test_the_file_decides_how_a_line_ends(tmp_path, content, ending):
    """pandas writes the separator of the machine, and the file is the source.

    A file written on Windows came back with every CRLF replaced by a LF, so
    samplify had changed a file it was not asked to change.
    """
    source = tmp_path / "in.csv"
    source.write_bytes(content)

    mapping = propose_csv(source, "sample_id", method="damerau")
    mapping.accept_all()
    mapping.mark_reviewed()
    output = tmp_path / "out.csv"
    apply_mapping(mapping, output_path=output)

    written = output.read_bytes()
    assert written.endswith(ending)
    assert written.count(ending) == content.count(ending)
    if ending == b"\r\n":
        # The newline inside the quoted value is part of that value.
        assert b'"two\r\nlines"' in written


def test_apply_opens_no_network_connection(tmp_path):
    """The claim the whole design rests on, checked at the socket.

    The tests around this one patch the harmoniser. This one forbids the
    connection itself, so a call added anywhere under `apply` fails here.
    """
    import socket

    mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="damerau")
    mapping.accept_all()
    mapping.mark_reviewed()

    def refuse(*args, **kwargs):
        raise AssertionError("apply opened a network connection")

    with patch.object(socket.socket, "connect", refuse), patch.object(
        socket.socket, "connect_ex", refuse
    ):
        frame, log = apply_mapping(mapping, output_path=tmp_path / "out.csv")

    assert log["summary"]["total_rows"] == len(frame)
