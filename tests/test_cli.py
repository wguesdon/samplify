"""Tests for the command line, for the parts that hold a decision.

The CLI renders what the library returns, so most of it needs no test. Two
places do. The threshold is a ratio that a caller types, and the review step
takes a canonical name from a person and writes it into the mapping file.
"""

from __future__ import annotations

import argparse

import pytest

from samplify import cli
from samplify.mapping import STATUS_EDITED, STATUS_PROPOSED, Group, MappingFile


# ── The threshold ──────────────────────────────────────────────────────────


def test_a_ratio_inside_the_range_is_accepted():
    assert cli._ratio("0.85") == 0.85
    assert cli._ratio("0") == 0.0
    assert cli._ratio("1") == 1.0


@pytest.mark.parametrize("value", ["-0.1", "1.5", "85"])
def test_a_ratio_outside_the_range_is_refused(value):
    """A threshold above 1.0 merges nothing and one below 0.0 merges everything."""
    with pytest.raises(argparse.ArgumentTypeError, match="between 0.0 and 1.0"):
        cli._ratio(value)


def test_text_that_is_not_a_number_is_refused():
    with pytest.raises(argparse.ArgumentTypeError, match="not a number"):
        cli._ratio("high")


def test_the_parser_refuses_a_threshold_outside_the_range(capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["propose", "data.csv", "-c", "sample_id", "--threshold", "1.5"]
        )
    assert "between 0.0 and 1.0" in capsys.readouterr().err


# ── The canonical name a person types ──────────────────────────────────────


def _pending(tmp_path):
    mapping = MappingFile(
        groups=[
            Group(
                id=1,
                members=["s1_b1", "sample_1_batch_1"],
                proposed="sample1_batch1",
                final="sample1_batch1",
                status=STATUS_PROPOSED,
                occurrences={"s1_b1": 1, "sample_1_batch_1": 1},
            )
        ]
    )
    path = tmp_path / "mapping.json"
    from samplify import mapping as mapping_module

    mapping_module.write(mapping, path)
    return path


def test_the_review_step_asks_again_for_an_empty_canonical_name(tmp_path, monkeypatch):
    """An empty answer renamed every member of the sample to nothing."""
    from samplify import mapping as mapping_module

    path = _pending(tmp_path)
    answers = iter(["", "   ", "cohort_1"])

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "_review_group", lambda *a, **k: "e")
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: next(answers))

    code = cli.main(["review", str(path)])
    assert code == 0

    result = mapping_module.read(path)
    assert result.groups[0].final == "cohort_1"
    assert result.groups[0].status == STATUS_EDITED


# ── The names must not leave the machine without a word ────────────────────


def _propose_args(**overrides):
    parser = cli.build_parser()
    argv = ["propose", "data.csv", "-c", "sample_id", "-M", "auto"]
    for flag, value in overrides.items():
        argv += [f"--{flag.replace('_', '-')}", value]
    return parser.parse_args(argv)


def test_no_warning_when_the_model_runs_on_this_machine(capsys):
    cli._warn_when_the_names_leave_this_machine(_propose_args(provider="ollama"))
    assert capsys.readouterr().out == ""


def test_a_warning_when_ollama_points_at_another_machine(capsys, monkeypatch):
    """OLLAMA_HOST is an environment variable, so no option has to be typed."""
    monkeypatch.setenv("OLLAMA_HOST", "otherbox:11434")
    cli._warn_when_the_names_leave_this_machine(_propose_args(provider="ollama"))
    # rich wraps the line, so the words are compared without the line breaks.
    printed = " ".join(capsys.readouterr().out.split())
    assert "otherbox" in printed
    assert "not this machine" in printed


def test_no_warning_when_no_model_is_called(capsys, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "otherbox:11434")
    parser = cli.build_parser()
    args = parser.parse_args(
        ["propose", "data.csv", "-c", "sample_id", "-M", "damerau", "-p", "ollama"]
    )
    cli._warn_when_the_names_leave_this_machine(args)
    assert capsys.readouterr().out == ""


def test_the_names_command_accepts_every_method_it_offers(monkeypatch, capsys):
    """-M auto was accepted by the parser and then refused by the backend.

    It reported "Unknown offline method: 'auto'", which named the option the
    person had just been offered.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    parser = cli.build_parser()
    for method in ("rules", "damerau"):
        assert cli.main(["names", "sample_1", "sample-1", "-M", method]) == 0

    # auto calls no model when the offline pass finds nothing to fix.
    capsys.readouterr()
    assert cli.main(["names", "sample_1", "sample_2", "-M", "auto"]) == 0

    # These two mix their delimiters, so auto does call the model and the error
    # has to name the missing key and nothing else.
    code = cli.main(["names", "sample_1", "sample-1", "-M", "auto"])
    printed = " ".join(capsys.readouterr().out.split())
    assert code == 1
    assert "No API key found" in printed
    assert "Unknown offline method" not in printed


# ── The review command, driven through every answer ────────────────────────


@pytest.mark.parametrize(
    "answers,expected_statuses,expected_reviewed",
    [
        (["a", "a", "a"], {"accepted"}, True),
        (["r", "r", "r"], {"rejected"}, True),
        (["e", "a", "a"], {"edited", "accepted"}, True),
        (["A"], {"accepted"}, True),
        (["q"], {"proposed"}, False),
    ],
)
def test_the_review_command_writes_what_the_person_answered(
    tmp_path, monkeypatch, answers, expected_statuses, expected_reviewed
):
    """Every answer the command accepts, driven end to end.

    The quit case must leave the file undecided, so that apply refuses it.
    """
    from samplify import mapping as mapping_module
    from samplify.csv_processor import propose_csv

    source = tmp_path / "in.csv"
    source.write_text(
        "sample_id\nS1_B1\ns1-b1\nP3_B2\np3-b2\nCTRL_rep1_b1\nctrl-r1-batch1\n"
    )
    path = tmp_path / "mapping.json"
    mapping_module.write(propose_csv(source, "sample_id", method="damerau"), path)

    stream = iter(answers)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "_review_group", lambda *a, **k: next(stream, "q"))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "typed_name")

    assert cli.main(["review", str(path)]) == 0

    result = mapping_module.read(path)
    assert {g.status for g in result.groups} == expected_statuses
    assert result.reviewed is expected_reviewed

    if expected_reviewed:
        assert result.final_mapping()
    else:
        with pytest.raises(ValueError, match="still proposed"):
            result.final_mapping()


@pytest.mark.parametrize("option", ["--output", "--plot"])
def test_propose_writes_no_output_over_its_own_input(tmp_path, option, capsys):
    """`-o data.csv` wrote the mapping JSON over the CSV it had just read."""
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")
    before = source.read_text()

    code = cli.main(
        ["propose", str(source), "-c", "sample_id", "-M", "damerau", "--yes",
         option, str(source)]
        + ([] if option == "--output" else ["-o", str(tmp_path / "m.json")])
    )

    assert code == 1
    assert "which is the input" in " ".join(capsys.readouterr().out.split())
    assert source.read_text() == before


def test_a_names_file_in_another_encoding_gives_an_error(tmp_path, capsys):
    """The decode happens while the lines are read, so it escaped the block
    that catches a missing file and reached the user as a traceback."""
    path = tmp_path / "names.txt"
    path.write_bytes("x\nsampl\xe9_1\n".encode("latin-1"))

    assert cli.main(["names", "--file", str(path), "-M", "damerau"]) == 1
    assert "could not be read" in " ".join(capsys.readouterr().out.split())


def test_a_names_file_that_excel_wrote_is_read(tmp_path, capsys):
    """utf-8-sig, as the CSV reader uses, so no byte order mark reaches a name."""
    path = tmp_path / "names.txt"
    path.write_bytes("﻿S1_B1\ns1-b1\n".encode("utf-8"))

    assert cli.main(["names", "--file", str(path), "-M", "damerau", "--json"]) == 0
    printed = capsys.readouterr().out
    assert '"S1_B1"' in printed
    assert "﻿" not in printed


def test_a_names_file_that_is_missing_still_says_so(tmp_path, capsys):
    assert cli.main(["names", "--file", str(tmp_path / "absent.txt")]) == 1
    assert "File not found" in " ".join(capsys.readouterr().out.split())


def test_propose_writes_all_of_its_files_or_none_of_them(tmp_path, capsys):
    """The mapping file was written and then a figure with a bad path failed,
    so the command reported an error while one of its files was on disk."""
    source = tmp_path / "data.csv"
    source.write_text("sample_id\nS1_B1\ns1-b1\n")

    code = cli.main([
        "propose", str(source), "-c", "sample_id", "-M", "damerau", "--yes",
        "-o", str(tmp_path / "mapping.json"),
        "--plot", str(tmp_path / "absent" / "qc.png"),
    ])

    assert code == 1
    assert "all of its files or none" in " ".join(capsys.readouterr().out.split())
    assert not (tmp_path / "mapping.json").exists()
