"""Tests for the quality control figure.

The figure is checked for the things a broken plot gets wrong: it must draw
every panel, it must save a file, and it must not fail on the empty case or on
a file where nothing needs fixing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
