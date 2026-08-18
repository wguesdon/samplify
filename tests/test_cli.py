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
