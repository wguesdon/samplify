"""Command-line interface for samplify.

Five commands. The first proposes, the second lets a person decide, the third
applies the decisions, the fourth is a quick look that writes nothing, and the
fifth redraws the figure from a mapping file.

    samplify propose data.csv --column sample_id -o mapping.json
    samplify review mapping.json
    samplify apply mapping.json --output clean.csv
    samplify names "sample_1_batch_1" "sample1_batch2" "sample-1-b3"
    samplify plot mapping.json -o qc.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import mapping as mapping_module
from . import matching
from .csv_processor import apply_mapping, is_the_same_file, propose, propose_csv
from .harmonizer import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TIMEOUT,
    DEFAULT_PROVIDER,
    OLLAMA_BASE_URL,
    PROVIDERS,
    harmonize,
    resolve_base_url,
)
from .mapping import (
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_REJECTED,
    Group,
    MappingFile,
)

console = Console()

_PROVIDER_HELP = (
    f"Which service answers, for the llm and auto backends (default: {DEFAULT_PROVIDER}). "
    "ollama runs a model on this machine and needs no API key."
)
_MODEL_HELP = (
    f"The model string (default: {DEFAULT_MODEL} for openrouter, "
    f"{DEFAULT_OLLAMA_MODEL} for ollama)."
)
_BASE_URL_HELP = (
    f"The server to call (default: the OpenRouter API, or {OLLAMA_BASE_URL} for ollama). "
    "OLLAMA_HOST is read when it is set."
)
_TIMEOUT_HELP = (
    f"Seconds to wait for the model (default: {DEFAULT_OLLAMA_TIMEOUT:.0f} for ollama)."
)


# ── Rendering ──────────────────────────────────────────────────────────────


def _ratio(value: str) -> float:
    """Read a similarity threshold from the command line.

    Args:
        value: The text the caller typed.

    Returns:
        The value as a float.

    Raises:
        argparse.ArgumentTypeError: If the value is not a ratio. A similarity
            is a ratio, so a value outside 0.0 to 1.0 either merges every name
            that shares a digit signature or merges none of them.
    """
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number.") from None
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError(
            f"{number} is not between 0.0 and 1.0."
        )
    return number


def _print_error(message: object) -> None:
    """Print an error message in red.

    The message text is escaped, because rich reads ``[plot]`` in
    ``uv add "samplify[plot]"`` as a style tag and drops it.

    Args:
        message: The exception or the text to print.
    """
    console.print(f"[red]Error:[/red] {escape(str(message))}")


def _print_diagnosis(findings: dict) -> None:
    """Print the heuristic findings from the propose step."""
    verdict = findings.get("verdict", "unknown")
    colour = "red" if verdict == "inconsistencies_found" else "green"
    abbrevs = findings.get("abbreviations_detected") or []
    lines = [
        f"[bold {colour}]Verdict:[/bold {colour}] {verdict}",
        f"  Delimiter mix:          {findings.get('delimiter_mix')}",
        f"  Abbreviations detected: {', '.join(abbrevs) if abbrevs else 'none'}",
        f"  Zero-padding mix:       {findings.get('zero_padding')}",
        f"  Case mix:               {findings.get('case_mix')}",
    ]
    console.print(Panel("\n".join(lines), title="[bold]Diagnosis[/bold]", expand=False))


#: The most pairs the console prints before it gives a count instead. A large
#: study produces hundreds, and the mapping file holds every one of them.
NEAR_MISS_DISPLAY_LIMIT = 20


def _print_near_misses(pairs: list[list[str]]) -> None:
    """Print the pairs that samplify refuses to merge."""
    if not pairs:
        return
    table = Table(
        show_header=True,
        header_style="bold red",
        title="Similar names that samplify never merges automatically",
    )
    table.add_column("Name A", style="yellow")
    table.add_column("Name B", style="yellow")
    table.add_column("Difference")
    for left, right in pairs[:NEAR_MISS_DISPLAY_LIMIT]:
        table.add_row(left, right, matching.describe_difference(left, right))
    console.print(table)

    if len(pairs) > NEAR_MISS_DISPLAY_LIMIT:
        console.print(
            f"[yellow]{len(pairs) - NEAR_MISS_DISPLAY_LIMIT} more pair(s) are in "
            f"the mapping file and not in this table.[/yellow]"
        )
    console.print(
        "[dim]Check each pair. Two patients and one patient with a typed digit "
        "look identical to the tool, and so do two cell types that differ by "
        "one letter.[/dim]\n"
    )


def _print_groups(groups: list[Group], title: str) -> None:
    """Print a table of groups."""
    if not groups:
        return
    table = Table(show_header=True, header_style="bold cyan", title=title)
    table.add_column("#", justify="right")
    table.add_column("Members", style="yellow")
    table.add_column("Canonical", style="green")
    table.add_column("Rows", justify="right")
    table.add_column("Status")
    for group in groups:
        table.add_row(
            str(group.id),
            "\n".join(f"{m}  ({group.occurrences.get(m, 0)})" for m in group.members),
            group.final,
            str(group.rows),
            group.status,
        )
    console.print(table)


def _print_summary(mapping: MappingFile) -> None:
    """Print the group counts."""
    summary = mapping.summary()
    console.print(
        f"\n[bold]{summary['groups']}[/bold] groups: "
        f"[bold green]{summary['merges']}[/bold green] merge, "
        f"[bold]{summary['renames']}[/bold] rename, "
        f"[bold]{summary['unchanged']}[/bold] unchanged, "
        f"[bold red]{summary['near_misses']}[/bold red] near miss."
    )


# ── propose ────────────────────────────────────────────────────────────────


def _warn_when_the_names_leave_this_machine(args: argparse.Namespace) -> None:
    """Say so before a model call sends the sample names to another machine.

    ``ollama`` is the private option, and it is private because the model runs
    here. ``OLLAMA_HOST`` is an environment variable, so a person can redirect
    every name to another host without typing an option and without reading a
    word about it. Sample names carry patient identifiers often enough that
    this has to be said out loud.

    Args:
        args: The parsed command line.
    """
    if args.method not in ("llm", "auto"):
        return

    url = resolve_base_url(args.provider, args.base_url)
    if args.provider == "ollama" and not any(
        host in url for host in ("localhost", "127.0.0.1", "[::1]")
    ):
        console.print(
            f"[yellow]The sample names go to ollama at {escape(url)}, which is "
            f"not this machine.[/yellow] The mapping file records that address."
        )


def _run_propose(args: argparse.Namespace) -> int:
    """Cluster the names in a CSV column and write a mapping file."""
    output = Path(args.output) if args.output else Path(f"{Path(args.file).stem}_mapping.json")
    _warn_when_the_names_leave_this_machine(args)

    # The mapping file and the figure go somewhere else. `-o data.csv` wrote the
    # mapping JSON over the CSV it had just read, and the names were gone.
    source = Path(args.file)
    for label, destination in (("--output", output), ("--plot", args.plot)):
        if destination is None:
            continue
        if is_the_same_file(destination, source):
            _print_error(
                f"{label} points at {source}, which is the input. samplify "
                f"writes no output over its own input."
            )
            return 1

    try:
        result = propose_csv(
            args.file,
            args.column,
            method=args.method,
            threshold=args.threshold,
            model=args.model,
            provider=args.provider,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except (ValueError, FileNotFoundError) as exc:
        _print_error(exc)
        return 1

    _print_diagnosis(result.diagnosis)
    _print_near_misses(result.near_misses)
    _print_groups(result.merges(), "Candidate merges, these need a decision")
    _print_groups(result.renames(), "Renames, one name each")
    _print_summary(result)

    if args.yes:
        result.accept_all()
        console.print(
            "\n[yellow]--yes given, so every group is accepted and no person "
            "reviewed them. The mapping file records reviewed: false.[/yellow]"
        )

    mapping_module.write(result, output)
    console.print(f"[green]Mapping written to {output}[/green]")

    if args.plot:
        code = _write_plot(result, args.plot)
        if code != 0:
            return code

    if not args.yes:
        console.print(f"[dim]Next: samplify review {output}[/dim]")
    return 0


# ── plot ───────────────────────────────────────────────────────────────────


def _write_plot(result: MappingFile, path: str, title: str | None = None, dpi: int = 150) -> int:
    """Draw the quality control figure and save it.

    Args:
        result: The mapping to draw.
        path: Where to save the figure.
        title: An explicit title, or None for the default.
        dpi: The resolution.

    Returns:
        The exit code.
    """
    # matplotlib is imported inside qc_figure, not at the top of plots.py, so
    # the call has to sit in the try block as well. Without it the missing
    # optional dependency reaches the user as a traceback.
    try:
        from .plots import qc_figure

        qc_figure(result, path=path, title=title, dpi=dpi)
    except ImportError as exc:
        _print_error(exc)
        return 1
    except OSError as exc:
        # A directory that does not exist, a full disk or a path with no write
        # permission. The figure is written last, so a traceback here also hid
        # the fact that the proposal itself had succeeded.
        _print_error(f"The figure could not be written to {path}: {exc}")
        return 1
    except ValueError as exc:
        # matplotlib decides the format from the extension of the path, and it
        # raises for one it cannot write. `-o qc.json` reached the user as a
        # traceback.
        _print_error(f"The figure could not be written to {path}: {exc}")
        return 1

    console.print(f"[green]QC figure written to {path}[/green]")
    return 0


def _run_plot(args: argparse.Namespace) -> int:
    """Draw the quality control figure for an existing mapping file."""
    # The figure goes somewhere else. Every other command already refuses to
    # write over its own input, and this one is the last of them.
    if is_the_same_file(args.output, args.mapping):
        _print_error(
            f"--output points at {args.mapping}, which is the input. samplify "
            f"writes no output over its own input."
        )
        return 1

    try:
        result = mapping_module.read(args.mapping)
    except (ValueError, FileNotFoundError) as exc:
        _print_error(exc)
        return 1
    return _write_plot(result, args.output, title=args.title, dpi=args.dpi)


# ── review ─────────────────────────────────────────────────────────────────

_REVIEW_HELP = (
    "[bold]a[/bold] accept   "
    "[bold]r[/bold] reject   "
    "[bold]e[/bold] edit the canonical name   "
    "[bold]A[/bold] accept all remaining   "
    "[bold]q[/bold] save and quit"
)


def _review_group(group: Group, index: int, total: int) -> str:
    """Ask a person what to do with one group.

    Args:
        group: The group awaiting a decision.
        index: The position of this group in the review.
        total: How many groups need a decision.

    Returns:
        The key the person pressed.
    """
    kind = "MERGE" if group.is_merge else "RENAME"
    body = [f"[bold]{kind}[/bold]  group {group.id}  ({index} of {total})", ""]
    for member in group.members:
        body.append(f"  {member}   [dim]{group.occurrences.get(member, 0)} rows[/dim]")
    body.append("")
    body.append(f"  canonical: [green]{group.proposed}[/green]")
    if group.min_similarity is not None:
        body.append(f"  lowest similarity in the group: {group.min_similarity}")
    console.print(Panel("\n".join(body), expand=False))
    console.print(_REVIEW_HELP)
    return Prompt.ask("Decision", choices=["a", "r", "e", "A", "q"], default="a")


def _run_review(args: argparse.Namespace) -> int:
    """Walk a person through every pending group and save the decisions."""
    try:
        result = mapping_module.read(args.mapping)
    except (ValueError, FileNotFoundError) as exc:
        _print_error(exc)
        return 1

    pending = result.pending()
    if not pending:
        console.print("[green]Every group already has a decision.[/green]")
        _print_summary(result)
        return 0

    if not sys.stdin.isatty():
        console.print(
            "[red]Error:[/red] review needs a terminal. For a pipeline, rerun "
            "propose with --yes, which records that no person reviewed the mapping."
        )
        return 1

    _print_near_misses(result.near_misses)

    # Merges carry the risk, so they come first.
    ordered = [g for g in pending if g.is_merge] + [g for g in pending if not g.is_merge]
    total = len(ordered)

    for index, group in enumerate(ordered, start=1):
        answer = _review_group(group, index, total)

        if answer == "a":
            group.status = STATUS_ACCEPTED
            group.final = group.proposed
        elif answer == "r":
            group.status = STATUS_REJECTED
            group.final = group.proposed
        elif answer == "e":
            # An empty answer renames every member of the sample to nothing,
            # so ask again until the name holds a character.
            new_name = ""
            while not new_name:
                new_name = Prompt.ask("Canonical name", default=group.proposed).strip()
                if not new_name:
                    console.print("[red]A canonical name must hold a character.[/red]")
            group.final = new_name
            group.status = STATUS_EDITED if new_name != group.proposed else STATUS_ACCEPTED
        elif answer == "A":
            for remaining in ordered[index - 1:]:
                if remaining.status == mapping_module.STATUS_PROPOSED:
                    remaining.status = STATUS_ACCEPTED
                    remaining.final = remaining.proposed
            break
        elif answer == "q":
            break

    if not result.pending():
        result.mark_reviewed()

    mapping_module.write(result, args.mapping)
    _print_summary(result)
    console.print(f"[green]Decisions saved to {args.mapping}[/green]")
    if result.pending():
        console.print(
            f"[yellow]{len(result.pending())} group(s) still have no decision. "
            f"apply will refuse until they do.[/yellow]"
        )

    # This warning comes last, because a reviewed file switches off the same
    # check in apply. A person who typed one name for two groups must read it
    # here, and it scrolled off the screen above the summary.
    collisions = result.collisions()
    if collisions:
        detail = "; ".join(
            f"{name} from groups {ids}" for name, ids in list(collisions.items())[:5]
        )
        console.print(
            f"[red]Warning:[/red] {len(collisions)} name(s) come from more than "
            f"one group: {detail}. Those samples join at the apply step. "
            f"apply does not refuse a reviewed mapping, so correct the file now "
            f"if that is not what you decided."
        )
    return 0


# ── apply ──────────────────────────────────────────────────────────────────


def _run_apply(args: argparse.Namespace) -> int:
    """Apply a reviewed mapping to a CSV, with no model call."""
    try:
        result = mapping_module.read(args.mapping)
        df, log = apply_mapping(
            result,
            data_path=args.data,
            column=args.column,
            output_path=args.output,
            canonical_column=args.canonical_column,
            json_log_path=args.json_log,
            csv_log_path=args.csv_log,
            mapping_path=str(args.mapping),
        )
    except (ValueError, FileNotFoundError) as exc:
        _print_error(exc)
        return 1

    summary = log["summary"]
    console.print(
        f"[bold]{summary['total_rows']}[/bold] rows, "
        f"[bold]{summary['unique_names']}[/bold] unique names, "
        f"[bold green]{summary['names_changed']}[/bold green] changed."
    )
    if not log["reviewed"]:
        console.print("[yellow]This mapping was not reviewed by a person.[/yellow]")

    # apply refuses a collision in a mapping that no person reviewed, and it
    # allows one in a reviewed mapping because a person signed for it. Joining
    # two groups into one name is the most consequential thing this tool does,
    # so it is never done in silence.
    for name, ids in log["collisions"].items():
        console.print(
            f"[red]Groups {ids} all became {escape(name)}.[/red] "
            f"Those samples are now one sample in the output."
        )
    for label, path in (
        ("Output CSV", args.output),
        ("JSON log", args.json_log),
        ("CSV log", args.csv_log),
    ):
        if path:
            console.print(f"[green]{label} written to {path}[/green]")
    if not args.output:
        console.print("[dim]No --output given, so nothing was written.[/dim]")
    return 0


# ── names ──────────────────────────────────────────────────────────────────


def _run_names(args: argparse.Namespace) -> int:
    """Show what the backend proposes for a handful of names. Writes nothing."""
    names: list[str] = list(args.names)
    if args.file:
        try:
            # utf-8-sig, as the CSV reader uses, so a file that Excel wrote does
            # not carry a byte order mark into its first name.
            with open(args.file, encoding="utf-8-sig") as fh:
                names.extend(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            _print_error(f"File not found: {args.file}")
            return 1
        except (OSError, ValueError) as exc:
            # A file in another encoding, or one this user may not read. The
            # decode happens while the lines are read, so it escaped the block
            # above and reached the user as a traceback.
            _print_error(f"{args.file} could not be read: {exc}")
            return 1

    if not names:
        console.print("[yellow]No sample names given. Use --help for usage.[/yellow]")
        return 1

    _warn_when_the_names_leave_this_machine(args)

    try:
        if args.method in ("llm", "auto"):
            # propose runs the whole backend, including the guards that a raw
            # model answer has to pass. Calling harmonize here showed the answer
            # of the model and not the answer of samplify, and it left the auto
            # method with no handler at all.
            result = propose(
                names,
                method=args.method,
                threshold=args.threshold,
                model=args.model,
                provider=args.provider,
                base_url=args.base_url,
                timeout=args.timeout,
            )
            pairs = sorted(
                (member, group.proposed)
                for group in result.groups
                for member in group.members
            )
            pattern = result.canonical_pattern or f"method={args.method}"
        else:
            groups = matching.group_names(
                names, method=args.method, threshold=args.threshold
            )
            pairs = sorted(
                (member, matching.canonical_for_group(group))
                for group in groups
                for member in group
            )
            pattern = f"offline, method={args.method}"
    except ValueError as exc:
        _print_error(exc)
        return 1

    if args.json_output:
        print(json.dumps({"canonical_pattern": pattern, "mapping": dict(pairs)}, indent=2))
        return 0

    console.print(f"\n[bold]Inferred pattern:[/bold] {pattern}\n")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Original", style="yellow")
    table.add_column("Canonical", style="green")
    table.add_column("Changed", justify="center")
    for original, canonical in pairs:
        table.add_row(original, canonical, "yes" if original != canonical else "")
    console.print(table)
    return 0


# ── Entry point ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every command."""
    parser = argparse.ArgumentParser(
        prog="samplify",
        description=(
            "Find sample names that are the same sample spelled differently, "
            "and let a person confirm each group before anything is renamed."
        ),
    )
    parser.add_argument("--version", action="store_true", help="Print the version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    method_help = (
        "rules: character rules only, no model. "
        "damerau: add typo tolerance, no model. "
        "llm: send every name to a model. "
        "auto: cluster offline, then send one name per cluster to a model."
    )

    propose_parser = subparsers.add_parser(
        "propose", help="Cluster the names in a CSV column and write a mapping file."
    )
    propose_parser.add_argument("file", metavar="FILE", help="The input CSV file.")
    propose_parser.add_argument(
        "--column", "-c", required=True, help="Column holding the sample identifiers."
    )
    propose_parser.add_argument(
        "--output", "-o", default=None, help="Mapping file to write (default: <stem>_mapping.json)."
    )
    propose_parser.add_argument(
        "--method", "-M", default="auto", choices=list(matching.METHODS), help=method_help
    )
    propose_parser.add_argument(
        "--threshold",
        type=_ratio,
        default=0.85,
        help="Lowest similarity that still counts as a match (default: 0.85).",
    )
    propose_parser.add_argument(
        "--model", "-m", default=None, help=_MODEL_HELP
    )
    propose_parser.add_argument(
        "--provider", "-p", default=DEFAULT_PROVIDER, choices=list(PROVIDERS), help=_PROVIDER_HELP
    )
    propose_parser.add_argument("--base-url", dest="base_url", default=None, help=_BASE_URL_HELP)
    propose_parser.add_argument(
        "--timeout", type=float, default=None, help=_TIMEOUT_HELP
    )
    propose_parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept every group without a review. The file records reviewed: false.",
    )
    propose_parser.add_argument(
        "--plot", default=None, metavar="PATH", help="Also write the QC figure here."
    )

    plot_parser = subparsers.add_parser(
        "plot", help="Draw the quality control figure for a mapping file."
    )
    plot_parser.add_argument("mapping", metavar="MAPPING", help="The mapping file to draw.")
    plot_parser.add_argument(
        "--output", "-o", required=True, help="Where to write the figure, as .png or .pdf."
    )
    plot_parser.add_argument("--title", default=None, help="Figure title.")
    plot_parser.add_argument("--dpi", type=int, default=150, help="Resolution (default: 150).")

    review_parser = subparsers.add_parser(
        "review", help="Decide each group in a mapping file. Needs a terminal."
    )
    review_parser.add_argument("mapping", metavar="MAPPING", help="The mapping file to review.")

    apply_parser = subparsers.add_parser(
        "apply", help="Apply a reviewed mapping to a CSV. Never calls a model."
    )
    apply_parser.add_argument("mapping", metavar="MAPPING", help="The reviewed mapping file.")
    apply_parser.add_argument(
        "--data", default=None, help="The CSV to apply it to (default: the file in the mapping)."
    )
    apply_parser.add_argument(
        "--column", "-c", default=None, help="The column of names (default: the one in the mapping)."
    )
    apply_parser.add_argument("--output", "-o", default=None, help="Where to write the result CSV.")
    apply_parser.add_argument(
        "--canonical-column",
        dest="canonical_column",
        default=None,
        help="Name of the new column (default: {column}_canonical).",
    )
    apply_parser.add_argument("--json-log", dest="json_log", default=None, help="JSON log path.")
    apply_parser.add_argument("--csv-log", dest="csv_log", default=None, help="CSV log path.")

    names_parser = subparsers.add_parser(
        "names", help="Show what a backend proposes for names given directly. Writes nothing."
    )
    names_parser.add_argument("names", nargs="*", metavar="NAME", help="Sample names.")
    names_parser.add_argument("--file", "-f", default=None, help="Text file, one name per line.")
    names_parser.add_argument(
        "--method",
        "-M",
        default=matching.DEFAULT_DISTANCE,
        choices=list(matching.METHODS),
        help=method_help,
    )
    names_parser.add_argument(
        "--threshold", type=_ratio, default=0.85, help="Match threshold."
    )
    names_parser.add_argument("--model", "-m", default=None, help=_MODEL_HELP)
    names_parser.add_argument(
        "--provider", "-p", default=DEFAULT_PROVIDER, choices=list(PROVIDERS), help=_PROVIDER_HELP
    )
    names_parser.add_argument("--base-url", dest="base_url", default=None, help=_BASE_URL_HELP)
    names_parser.add_argument("--timeout", type=float, default=None, help=_TIMEOUT_HELP)
    names_parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Print raw JSON."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        from . import __version__

        console.print(f"samplify {__version__}")
        return 0

    handlers = {
        "propose": _run_propose,
        "review": _run_review,
        "apply": _run_apply,
        "names": _run_names,
        "plot": _run_plot,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
