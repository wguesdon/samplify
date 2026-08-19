"""Tests for the quality control figure.

The figure is checked for the things a broken plot gets wrong: it must draw
every panel, it must save a file, and it must not fail on the empty case or on
a file where nothing needs fixing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samplify import cli
from samplify import matching
from samplify.csv_processor import propose_csv
from samplify.mapping import MappingFile

matplotlib = pytest.importorskip("matplotlib", reason="plotting is an optional extra")

from samplify.plots import qc_figure  # noqa: E402  (after the optional import check)

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example"


def test_qc_figure_writes_a_file(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="damerau")
    path = tmp_path / "qc.png"
    qc_figure(mapping, path=str(path))

    assert path.exists()
    assert path.stat().st_size > 10_000


def test_qc_figure_draws_four_panels(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "cohort_messy.csv", "sample_id", method="damerau")
    figure = qc_figure(mapping, path=str(tmp_path / "qc.png"))
    assert len(figure.axes) == 4


def test_qc_figure_titles_name_the_column_and_method(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    figure = qc_figure(mapping, path=str(tmp_path / "qc.png"))
    assert "sample_id" in figure._suptitle.get_text()
    assert "damerau" in figure._suptitle.get_text()


def test_qc_figure_handles_a_clean_file(tmp_path):
    """Nothing to merge and nothing to flag must still draw."""
    mapping = propose_csv(EXAMPLE_DIR / "clean_samples.csv", "sample_id", method="rules")
    path = tmp_path / "qc.png"
    qc_figure(mapping, path=str(path))
    assert path.exists()


def test_qc_figure_handles_an_empty_mapping(tmp_path):
    path = tmp_path / "qc.png"
    qc_figure(MappingFile(groups=[]), path=str(path))
    assert path.exists()


def test_qc_figure_accepts_an_explicit_title(tmp_path):
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="rules")
    figure = qc_figure(mapping, path=str(tmp_path / "qc.png"), title="A cohort")
    assert figure._suptitle.get_text() == "A cohort"


def test_cli_reports_a_missing_matplotlib(tmp_path, monkeypatch, capsys):
    """The optional dependency must reach the user as a message, not a traceback.

    plots.py imports matplotlib inside qc_figure, so the call and not the import
    is what raises. The CLI has to catch it there.
    """

    def _no_matplotlib(*args, **kwargs):
        raise ImportError('Install it with: uv add "samplify[plot]"')

    monkeypatch.setattr("samplify.plots.qc_figure", _no_matplotlib)
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="rules")

    code = cli._write_plot(mapping, str(tmp_path / "qc.png"))

    # The extra name has to survive the print. rich reads [plot] as a style tag.
    assert code == 1
    assert 'uv add "samplify[plot]"' in capsys.readouterr().out


# ── The review findings of 2026-08-18 ──────────────────────────────────────


def test_a_group_that_fits_is_kept_when_a_larger_one_does_not():
    """A break dropped every group behind the first one that was too large."""
    from samplify.plots import _ordered_names
    from samplify.mapping import Group

    def group(id_: int, members: list[str]) -> Group:
        return Group(id=id_, members=members, proposed=members[0], final=members[0])

    mapping = MappingFile(
        groups=[
            group(1, ["a_1", "a_2", "a_3"]),
            group(2, ["b_1", "b_2", "b_3"]),
            group(3, ["c_1"]),
        ]
    )
    names, blocks = _ordered_names(mapping, limit=4)

    # Group 2 does not fit behind group 1, and group 3 still does.
    assert names == ["a_1", "a_2", "a_3", "c_1"]
    assert len(blocks) == 2


def test_the_heatmap_scores_the_value_that_decided_the_group():
    """The panel showed the whole raw name, which took no part in the decision.

    The decision is a conjunction. A pair whose numbers differ was never
    compared, whatever its letters look like, and a pair inside one signature
    was decided on its letters alone.
    """
    from samplify.plots import _similarity_matrix

    # Identical letters, different numbers. The identity rule refused this pair.
    blocked = _similarity_matrix(["patient11_batch2", "patient111_batch2"])
    assert blocked[0][1] == 0.0

    # One signature, one dropped letter. This is the pair that merged.
    compared = _similarity_matrix(["patient1_batch1", "patietn1_batch1"])
    assert 0.85 < compared[0][1] < 1.0


def test_a_figure_that_cannot_be_written_gives_an_error_not_a_traceback(tmp_path, capsys):
    """A directory that does not exist reached the user as a FileNotFoundError.

    The figure is written last, so the traceback also hid the fact that the
    proposal itself had succeeded.
    """
    mapping = propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau")
    code = cli._write_plot(mapping, str(tmp_path / "no_such_directory" / "qc.png"))

    assert code == 1
    assert "could not be written" in capsys.readouterr().out


def test_plot_writes_no_figure_over_its_own_mapping(tmp_path, capsys):
    """Every command refuses to write over its own input, and this is the last."""
    from samplify import mapping as mapping_module

    path = tmp_path / "mapping.json"
    mapping_module.write(
        propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau"), path
    )
    before = path.read_text()

    assert cli.main(["plot", str(path), "-o", str(path)]) == 1
    assert "which is the input" in " ".join(capsys.readouterr().out.split())
    assert path.read_text() == before


def test_a_format_matplotlib_cannot_write_gives_an_error(tmp_path, capsys):
    """matplotlib decides the format from the extension and raises for one it
    cannot write, and `-o qc.json` reached the user as a traceback."""
    from samplify import mapping as mapping_module

    path = tmp_path / "mapping.json"
    mapping_module.write(
        propose_csv(EXAMPLE_DIR / "typos.csv", "sample_id", method="damerau"), path
    )

    assert cli.main(["plot", str(path), "-o", str(tmp_path / "qc.json")]) == 1
    assert "could not be written" in " ".join(capsys.readouterr().out.split())


def test_the_panel_shows_the_value_that_decided_the_pair():
    """The decision reads the differing token, and the panel read the whole
    name, so `sample_A` against `sample_AA` showed 0.875 while the tool had
    refused the pair."""
    from samplify.plots import _similarity_matrix

    refused = _similarity_matrix(["sample_A", "sample_AA"])[0][1]
    assert refused < 0.85
    assert len(matching.group_names(["sample_A", "sample_AA"], method="damerau")) == 2

    merged = _similarity_matrix(["patient1_batch1", "patietn1_batch1"])[0][1]
    assert merged >= 0.85
    assert len(matching.group_names(
        ["patient1_batch1", "patietn1_batch1"], method="damerau"
    )) == 1
