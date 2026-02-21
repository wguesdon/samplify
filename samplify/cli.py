"""
Command-line interface for samplify.

Usage examples:
    samplify "sample_1_batch_1" "sample1_batch2" "sample-1-b3"
    samplify --file names.txt
    samplify --file names.txt --output mapping.json
"""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from .harmonizer import harmonize

console = Console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="samplify",
        description="Harmonize inconsistent bioinformatics sample names using an LLM.",
    )
    parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help="Sample names to harmonize (space-separated).",
    )
    parser.add_argument(
        "--file",
        "-f",
        metavar="PATH",
        help="Text file with one sample name per line.",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Write JSON mapping to this file instead of stdout.",
    )
    parser.add_argument(
        "--model",
        "-m",
        metavar="MODEL",
        default=None,
        help="OpenRouter model string (default: openai/gpt-4o-mini).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print raw JSON output (useful for piping).",
    )

    args = parser.parse_args(argv)

    # Collect names
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

    # Output
    if args.output:
        with open(args.output, "w") as fh:
            json.dump(result, fh, indent=2)
        console.print(f"[green]Mapping written to {args.output}[/green]")
    elif args.json_output:
        print(json.dumps(result, indent=2))
    else:
        # Pretty table
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


if __name__ == "__main__":
    sys.exit(main())
