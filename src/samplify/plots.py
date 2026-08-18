"""Quality control figures for a proposed mapping.

The figure answers the question a person asks before they review anything: how
bad is this file, and which names need my attention. It is a scan, not a
verdict, and every panel points at the groups and the pairs a person must
decide.

matplotlib is an optional dependency. Install it with the ``plot`` extra.

    uv add "samplify[plot]"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import matching
from .mapping import MappingFile

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.figure import Figure

#: Shown when a name is longer than the axis can carry.
LABEL_LIMIT = 26

#: Above this many names the heatmap stops being readable, so it is trimmed to
#: the names that a person actually has to decide.
HEATMAP_LIMIT = 40

_COLOURS = {
    "merge": "#2166ac",
    "rename": "#67a9cf",
    "unchanged": "#bdbdbd",
    "flag": "#b2182b",
    "grid": "#e6e6e6",
    "text": "#222222",
}


def _require_matplotlib() -> Any:
    """Import matplotlib, or explain how to install it.

    Returns:
        The ``matplotlib.pyplot`` module.

    Raises:
        ImportError: If matplotlib is not installed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Plotting needs matplotlib, which is an optional dependency. "
            'Install it with: uv add "samplify[plot]"'
        ) from exc
    return plt


def _shorten(label: str) -> str:
    """Trim a name so that it fits on an axis.

    Args:
        label: The name to trim.

    Returns:
        The name, cut in the middle if it is too long.
    """
    if len(label) <= LABEL_LIMIT:
        return label
    keep = (LABEL_LIMIT - 1) // 2
    return f"{label[:keep]}…{label[-keep:]}"


def _ordered_names(mapping: MappingFile, limit: int) -> tuple[list[str], list[tuple[int, int, str]]]:
    """Order the names by group and report where each block starts and ends.

    Args:
        mapping: The proposed mapping.
        limit: The largest number of names to include.

    Returns:
        The ordered names, and one entry per block as the start index, the size
        and the group kind.
    """
    groups = sorted(
        mapping.groups,
        key=lambda g: (-len(g.members), g.members[0]),
    )

    names: list[str] = []
    blocks: list[tuple[int, int, str]] = []
    for group in groups:
        # Skip a group that does not fit and keep reading. A break here dropped
        # every group behind the first one that was too large, including the
        # small ones that still had room.
        if len(names) + len(group.members) > limit and names:
            continue
        kind = "merge" if group.is_merge else ("rename" if group.is_rename else "unchanged")
        blocks.append((len(names), len(group.members), kind))
        names.extend(group.members)
    return names, blocks


def _similarity_matrix(names: list[str]) -> list[list[float]]:
    """Build the pairwise similarity matrix for a list of names.

    The score compares the letter skeletons, which is the value that decided
    each group. Scoring the whole raw name showed a person a measure that took
    no part in the decision. It also makes the near misses visible: a pair with
    identical letters and different numbers reads 1.0 and carries no outline,
    which is the reason samplify refused to merge it.

    Args:
        names: The names, already in display order.

    Returns:
        A square matrix of similarities between 0.0 and 1.0.
    """
    skeletons = [matching.letter_skeleton(n) for n in names]
    return [
        [matching.similarity(a, b, method=matching.DEFAULT_DISTANCE) for b in skeletons]
        for a in skeletons
    ]


def _panel_heatmap(ax: Any, mapping: MappingFile) -> None:
    """Draw the similarity matrix with one outlined block per group."""
    from matplotlib.patches import Rectangle

    names, blocks = _ordered_names(mapping, HEATMAP_LIMIT)
    if not names:
        ax.axis("off")
        return

    matrix = _similarity_matrix(names)

    # Names that share a stem are all similar to each other, so a fixed 0 to 1
    # scale paints the whole panel one colour and hides the blocks. The scale
    # starts at the lowest pair actually present.
    off_diagonal = sorted(
        matrix[i][j] for i in range(len(names)) for j in range(len(names)) if i != j
    )
    # The floor is the 20th percentile rather than the minimum. One unusual
    # name, such as a heavily abbreviated one, would otherwise set the floor on
    # its own and push every other pair into the same dark band.
    floor = off_diagonal[len(off_diagonal) // 5] if off_diagonal else 0.0
    ax.imshow(matrix, cmap="Blues", vmin=floor, vmax=1.0, interpolation="nearest")

    labels = [_shorten(n) for n in names]
    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.set_yticklabels(labels, fontsize=6)

    for start, size, kind in blocks:
        ax.add_patch(
            Rectangle(
                (start - 0.5, start - 0.5),
                size,
                size,
                fill=False,
                edgecolor=_COLOURS["merge"] if kind == "merge" else _COLOURS["unchanged"],
                linewidth=1.6 if kind == "merge" else 0.8,
            )
        )

    total = len(mapping.groups)
    shown = len(blocks)
    suffix = "" if shown == total else f", {shown} of {total} groups shown"
    ax.set_title(
        f"Letter similarity, ordered by group{suffix}\n"
        f"darker means more alike, and the numbers are not in this panel",
        fontsize=10,
        color=_COLOURS["text"],
    )


def _panel_group_sizes(ax: Any, mapping: MappingFile) -> None:
    """Draw how many spellings each sample arrived with."""
    merges = sorted(mapping.merges(), key=lambda g: (len(g.members), g.final))
    if not merges:
        ax.text(0.5, 0.5, "No sample arrived with more than one spelling.",
                ha="center", va="center", fontsize=9, color=_COLOURS["text"])
        ax.axis("off")
        ax.set_title("Spellings per sample", fontsize=10, color=_COLOURS["text"])
        return

    labels = [_shorten(g.final)[:22] for g in merges]
    sizes = [len(g.members) for g in merges]
    ax.barh(range(len(merges)), sizes, color=_COLOURS["merge"])
    ax.set_yticks(range(len(merges)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("spellings found", fontsize=8)
    ax.set_xticks(range(0, max(sizes) + 1))
    ax.tick_params(axis="x", labelsize=7)
    ax.set_title("Spellings per sample", fontsize=10, color=_COLOURS["text"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _panel_counts(ax: Any, mapping: MappingFile) -> None:
    """Draw the count of names before and the count of samples after."""
    summary = mapping.summary()
    unique_names = sum(len(g.members) for g in mapping.groups)
    samples = summary["groups"]

    bars = [
        ("names in the column", unique_names, _COLOURS["unchanged"]),
        ("samples after grouping", samples, _COLOURS["merge"]),
        ("groups needing a merge", summary["merges"], _COLOURS["rename"]),
        ("pairs to check by hand", summary["near_misses"], _COLOURS["flag"]),
    ]
    labels = [b[0] for b in bars]
    values = [b[1] for b in bars]
    colours = [b[2] for b in bars]

    ax.bar(range(len(bars)), values, color=colours)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels(labels, fontsize=7, rotation=20, ha="right")
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title("What the mapping does", fontsize=10, color=_COLOURS["text"])
    for index, value in enumerate(values):
        ax.text(index, value, str(value), ha="center", va="bottom", fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _panel_flags(ax: Any, mapping: MappingFile) -> None:
    """List the pairs that a person must decide, with the reason for each."""
    ax.axis("off")
    ax.set_title("Names that need a person", fontsize=10, color=_COLOURS["text"], pad=4)

    rows: list[tuple[str, str, str, str]] = []
    for pair in mapping.near_misses:
        rows.append((_shorten(pair[0]), _shorten(pair[1]), "digit added or dropped", "no"))

    for group in sorted(mapping.merges(), key=lambda g: -len(g.members)):
        reference = group.proposed
        for member in group.members:
            kind = matching.describe_difference(member.strip(), reference)
            if kind not in ("identical", "formatting only"):
                rows.append((_shorten(member), _shorten(reference), kind, "yes"))

    if not rows:
        ax.text(0.5, 0.6, "Nothing was flagged.", ha="center", va="center", fontsize=9)
        return

    rows = rows[:9]
    height = min(0.95, 0.115 * (len(rows) + 1))
    table = ax.table(
        cellText=rows,
        colLabels=["name", "compared with", "difference", "merged"],
        cellLoc="left",
        colLoc="left",
        colWidths=[0.28, 0.28, 0.30, 0.14],
        bbox=(0.0, 0.95 - height, 1.0, height),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6)

    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor(_COLOURS["grid"])
        if row == 0:
            cell.set_text_props(weight="bold")
        elif rows[row - 1][3] == "no":
            cell.set_text_props(color=_COLOURS["flag"])


def qc_figure(
    mapping: MappingFile,
    *,
    path: str | None = None,
    title: str | None = None,
    dpi: int = 150,
) -> Figure:
    """Draw the four-panel quality control figure for a mapping.

    The panels are the similarity matrix ordered by group, the number of
    spellings per sample, the counts before and after, and the list of names
    that need a decision.

    Args:
        mapping: A proposed or reviewed mapping.
        path: Where to save the figure. Nothing is written when None.
        title: The figure title. A default is built from the mapping when None.
        dpi: The resolution used when the figure is saved.

    Returns:
        The matplotlib figure.

    Raises:
        ImportError: If matplotlib is not installed.
    """
    plt = _require_matplotlib()

    # The similarity matrix carries the argument, so it holds the whole left
    # column. The three summary panels stack on the right.
    figure = plt.figure(figsize=(14, 9))
    figure.patch.set_facecolor("white")
    grid = figure.add_gridspec(
        3,
        2,
        width_ratios=[1.25, 0.9],
        height_ratios=[1.0, 0.8, 1.0],
        hspace=0.55,
        wspace=0.42,
    )

    _panel_heatmap(figure.add_subplot(grid[:, 0]), mapping)
    _panel_group_sizes(figure.add_subplot(grid[0, 1]), mapping)
    _panel_counts(figure.add_subplot(grid[1, 1]), mapping)
    _panel_flags(figure.add_subplot(grid[2, 1]), mapping)

    if title is None:
        source = mapping.column or "sample names"
        title = f"samplify quality control: {source}, method {mapping.method}"
    figure.suptitle(title, fontsize=14, color=_COLOURS["text"], y=0.98)

    if path is not None:
        figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    return figure
