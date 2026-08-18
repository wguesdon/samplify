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
