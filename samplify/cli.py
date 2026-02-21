"""
Command-line interface for samplify.

Usage examples:
    samplify names "sample_1_batch_1" "sample1_batch2" "sample-1-b3"
    samplify names --file names.txt
    samplify csv data.csv --column sample_id
    samplify csv data.csv --column sample_id --output out.csv --json-log log.json
"""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from .harmonizer import harmonize

console = Console()


# ── "names" subcommand (original behaviour) ───────────────────────────────


def _run_names(args: argparse.Namespace) -> int:
    names: list[str] = list(args.names)
    if args.file:
        try:
            with open(args.file) as fh:
                file_names = [line.strip() for line in fh if line.strip()]
            names.extend(file_names)
        except FileNotFoundError:
            console.print(f"[red]Error:[/red] File not found: {args.file}")
            return 1

    if not names:
        console.print("[yellow]No sample names provided. Use --help for usage.[/yellow]")
        return 1

    console.print(f"[dim]Harmonizing {len(names)} sample names...[/dim]")

    try:
        result = harmonize(names, model=args.model)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    if args.output:
        with open(args.output, "w") as fh:
            json.dump(result, fh, indent=2)
        console.print(f"[green]Mapping written to {args.output}[/green]")
    elif args.json_output:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"\n[bold]Inferred pattern:[/bold] {result['canonical_pattern']}\n")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Original", style="yellow")
        table.add_column("Canonical", style="green")
        for original, canonical in result["mapping"].items():
            changed = original != canonical
            table.add_row(
                original,
                canonical,
                *(["[bold]✓[/bold]"] if changed else [""]),
            )
        console.print(table)

    return 0


# ── "csv" subcommand ───────────────────────────────────────────────────────


def _run_csv(args: argparse.Namespace) -> int:
    from .csv_processor import harmonize_csv

    canonical_column = args.canonical_column or f"{args.column}_canonical"

    try:
        _df, _log = harmonize_csv(
            args.file,
            args.column,
            output_path=args.output,
            json_log_path=args.json_log,
            csv_log_path=args.csv_log,
            canonical_column=canonical_column,
            model=args.model,
        )
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    return 0


# ── Entry point ────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="samplify",
        description="Harmonize inconsistent bioinformatics sample names using an LLM.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ── names subcommand ──
    names_parser = subparsers.add_parser(
        "names",
        help="Harmonize sample names given on the command line or from a text file.",
    )
    names_parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help="Sample names to harmonize (space-separated).",
    )
    names_parser.add_argument(
        "--file",
        "-f",
        metavar="PATH",
        help="Text file with one sample name per line.",
    )
    names_parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Write JSON mapping to this file instead of stdout.",
    )
    names_parser.add_argument(
        "--model",
        "-m",
        metavar="MODEL",
        default=None,
        help="OpenRouter model string (default: openai/gpt-4o-mini).",
    )
    names_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print raw JSON output (useful for piping).",
    )

    # ── csv subcommand ──
    csv_parser = subparsers.add_parser(
        "csv",
        help="Harmonize a sample-ID column in a CSV file.",
    )
    csv_parser.add_argument(
        "file",
        metavar="FILE",
        help="Path to the input CSV file.",
    )
    csv_parser.add_argument(
        "--column",
        "-c",
        metavar="COLUMN",
        required=True,
        help="Column name containing the sample identifiers.",
    )
    csv_parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        default=None,
        help="Path for the output CSV (input + canonical column).",
    )
    csv_parser.add_argument(
        "--json-log",
        metavar="PATH",
        default=None,
        dest="json_log",
        help="Path for the JSON summary log file.",
    )
    csv_parser.add_argument(
        "--csv-log",
        metavar="PATH",
        default=None,
        dest="csv_log",
        help="Path for the CSV change log file.",
    )
    csv_parser.add_argument(
        "--canonical-column",
        metavar="NAME",
        default=None,
        dest="canonical_column",
        help="Name of the new canonical column (default: {column}_canonical).",
    )
    csv_parser.add_argument(
        "--model",
        "-m",
        metavar="MODEL",
        default=None,
        help="OpenRouter model string (default: openai/gpt-4o-mini).",
    )

    args = parser.parse_args(argv)

    if args.command == "names":
        return _run_names(args)
    elif args.command == "csv":
        return _run_csv(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
