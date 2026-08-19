"""Draw the figure that records what the validation on real data changed.

The counts come from running ``samplify propose`` over the free-text sample
names of 390 study and field combinations of the ENA archive. The query and the
method are in ``docs/how_it_works.md``. Run this file to redraw
``docs/img/validation_ena.png``.

Usage:
    uv run python docs/make_validation_figure.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (after the backend is chosen)

#: The two colours are the ones ``samplify.plots`` already uses, so this figure
#: and the quality control figures read as one system. The pair clears the
#: colour-vision checks: worst deuteranopia and protanopia separation is
#: 21.1 and normal-vision separation is 28.7, both in OKLab times 100.
KEPT = "#2166ac"
REMOVED = "#b2182b"
GRID = "#e6e6e6"
TEXT = "#222222"
MUTED = "#666666"
SURFACE = "#ffffff"

#: One row per version. ``kept`` is the number of merges that version still
#: proposes and ``removed`` is the number that a later version took away.
#:
#: 0.4.1 proposed 350 merges. The edit cap of 0.5.0 removed 246, the sign rule
#: of 0.6.0 removed 30, the substitution rule of 0.7.0 removed 42 and the token
#: rules of 0.14.0 removed 6 more. The 26 that remain were each read by hand:
#: 24 are a difference of formatting, one is a real transposition and one moves
#: a replicate number. The six that 0.14.0 removed were reported as correct
#: after 0.7.0, and they were not.
#:
#: The rules of 0.15.0 to 0.19.0 remove none of the 26. Each one refuses a shape
#: that this corpus does not hold: a sign written in another typeface, a
#: fullwidth character, a token substituted inside a longer difference and a
#: label added at an end of a name. The last row records that.
ROWS: tuple[tuple[str, str, int, int], ...] = (
    ("0.4.1", "before the validation", 26, 324),
    ("0.5.0", "an edit cap of one", 26, 78),
    ("0.6.0", "a sign identifies a sample", 26, 48),
    ("0.7.0", "a substitution is reported, not merged", 26, 6),
    ("0.14.0", "a difference is judged by its token", 26, 0),
    ("0.19.0", "a label added at an end is not a slip", 26, 0),
)

#: The gap between the two segments of a bar, in units of the x axis. At this
#: figure width it renders as about two pixels, which separates the segments
#: without drawing a border around either one.
SEGMENT_GAP = 2.0


def draw(path: Path) -> Path:
    """Draw the figure and write it to ``path``.

    Args:
        path: Where to write the PNG.

    Returns:
        The path written.
    """
    figure, axes = plt.subplots(figsize=(9.0, 4.4), dpi=200)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    # Room above the plot for the title, the subtitle and the legend, in
    # that order. Each one gets its own band so none can overlap another.
    figure.subplots_adjust(top=0.74, left=0.28, right=0.97, bottom=0.16)

    positions = range(len(ROWS))
    for position, (_, _, kept, removed) in zip(positions, ROWS):
        axes.barh(position, kept, height=0.38, color=KEPT, zorder=3)
        if removed:
            axes.barh(
                position,
                removed - SEGMENT_GAP,
                left=kept + SEGMENT_GAP,
                height=0.38,
                color=REMOVED,
                zorder=3,
            )

        total = kept + removed
        axes.text(
            total + 6, position, str(total), va="center", ha="left",
            fontsize=10, color=TEXT, fontweight="bold",
        )
        if removed >= 40:
            axes.text(
                kept + SEGMENT_GAP + removed / 2, position, str(removed),
                va="center", ha="center", fontsize=9, color=SURFACE,
            )
        elif removed == 0:
            # Clear of the total label, which sits at the end of the bar.
            axes.text(
                kept + 34, position, "no wrong merge left",
                va="center", ha="left", fontsize=9, color=MUTED,
            )

    axes.set_yticks(list(positions))
    axes.set_yticklabels(
        [f"{version}\n{note}" for version, note, _, _ in ROWS],
        fontsize=9, color=TEXT,
    )
    axes.invert_yaxis()

    axes.set_xlim(0, 395)
    axes.set_xlabel("merges proposed across 390 study and field combinations",
                    fontsize=9, color=MUTED)
    axes.tick_params(axis="x", labelsize=8, colors=MUTED, length=0)
    axes.tick_params(axis="y", length=0)
    axes.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    axes.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        axes.spines[side].set_visible(False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=KEPT),
        plt.Rectangle((0, 0), 1, 1, color=REMOVED),
    ]
    axes.legend(
        handles,
        ["correct, still proposed", "removed by a later version"],
        loc="lower left", bbox_to_anchor=(0.0, 1.03), ncol=2,
        frameon=False, fontsize=9, labelcolor=TEXT, handlelength=1.2,
        handleheight=0.9, borderpad=0.0, columnspacing=1.6,
    )

    figure.text(
        0.03, 0.94, "What the validation on real data changed",
        ha="left", va="top", fontsize=13.5, color=TEXT,
    )
    figure.text(
        0.03, 0.865,
        "samplify on the free-text sample names of 20,000 human RNA-seq runs "
        "of the ENA archive",
        ha="left", va="top", fontsize=9.5, color=MUTED,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, facecolor=SURFACE)
    plt.close(figure)
    return path


if __name__ == "__main__":
    written = draw(Path(__file__).resolve().parent / "img" / "validation_ena.png")
    print(f"wrote {written}")
