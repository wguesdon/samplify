"""
CSV-aware sample name harmonization: diagnosis, LLM harmonization, and dual-format logging.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .harmonizer import harmonize

console = Console()

# Abbreviation token patterns (matched against individual delimiter-split tokens)
_ABBREV_PATTERNS: list[tuple[str, str]] = [
    (r"b\d+", "batch (b<n>)"),
    (r"bat\d+", "batch (bat<n>)"),
    (r"rep\d*", "replicate (rep)"),
    (r"r\d+", "replicate (r<n>)"),
    (r"ctrl", "control (ctrl)"),
    (r"samp", "sample (samp)"),
    (r"wt", "wildtype (wt)"),
    (r"ko", "knockout (ko)"),
    (r"trt", "treatment (trt)"),
]


def diagnose(names: list[str]) -> dict:
    """
    Run heuristic checks on a list of sample names and return a findings dict.

    Parameters
    ----------
    names:
        List of unique sample name strings to inspect.

    Returns
    -------
    dict with keys:
        delimiter_mix         - True if more than one delimiter style is present
        abbreviations_detected - list of abbreviation descriptions found
        zero_padding          - True if mixed zero-padded and non-padded numbers
        case_mix              - True if both upper and lower case letters present
        verdict               - "inconsistencies_found" | "appears_consistent"
    """
    if not names:
        return {
            "delimiter_mix": False,
            "abbreviations_detected": [],
            "zero_padding": False,
            "case_mix": False,
            "verdict": "appears_consistent",
        }

    # Delimiter mix: check which of _, -, . appear across all names
    delimiters_used = set()
    for name in names:
        if "_" in name:
            delimiters_used.add("_")
        if "-" in name:
            delimiters_used.add("-")
        if "." in name:
            delimiters_used.add(".")
    delimiter_mix = len(delimiters_used) > 1

    # Abbreviations: split each name by common delimiters and check each token
    abbreviations_detected: list[str] = []
    seen_abbrevs: set[str] = set()
    for name in names:
        tokens = re.split(r"[_\-\.\s]", name.lower())
        for token in tokens:
            for pattern, description in _ABBREV_PATTERNS:
                if description not in seen_abbrevs and re.fullmatch(pattern, token):
                    abbreviations_detected.append(description)
                    seen_abbrevs.add(description)

    # Zero padding: look for numbers that appear both with and without leading zeros
    # Extract all numeric tokens from all names
    padded: set[str] = set()
    unpadded: set[str] = set()
    for name in names:
        for token in re.findall(r"\d+", name):
            if len(token) > 1 and token.startswith("0"):
                padded.add(token.lstrip("0") or "0")
            else:
                unpadded.add(token)
    zero_padding = bool(padded & unpadded)

    # Case mix: any uppercase letters alongside any lowercase
    has_upper = any(c.isupper() for name in names for c in name)
    has_lower = any(c.islower() for name in names for c in name)
    case_mix = has_upper and has_lower

    inconsistent = delimiter_mix or bool(abbreviations_detected) or zero_padding or case_mix
    verdict = "inconsistencies_found" if inconsistent else "appears_consistent"

    return {
        "delimiter_mix": delimiter_mix,
        "abbreviations_detected": abbreviations_detected,
        "zero_padding": zero_padding,
        "case_mix": case_mix,
        "verdict": verdict,
    }


def _print_diagnosis(findings: dict) -> None:
    lines: list[str] = []

    verdict = findings["verdict"]
    verdict_colour = "red" if verdict == "inconsistencies_found" else "green"
    lines.append(f"[bold {verdict_colour}]Verdict:[/bold {verdict_colour}] {verdict}")

    lines.append(
        f"  Delimiter mix:          [{('red' if findings['delimiter_mix'] else 'green')}]"
        f"{findings['delimiter_mix']}[/]"
    )
    abbrevs = findings["abbreviations_detected"]
    abbrev_str = ", ".join(abbrevs) if abbrevs else "none"
    lines.append(f"  Abbreviations detected: {abbrev_str}")
    lines.append(
        f"  Zero-padding mix:       [{('red' if findings['zero_padding'] else 'green')}]"
        f"{findings['zero_padding']}[/]"
    )
    lines.append(
        f"  Case mix:               [{('red' if findings['case_mix'] else 'green')}]"
        f"{findings['case_mix']}[/]"
    )

    console.print(Panel("\n".join(lines), title="[bold]Diagnosis[/bold]", expand=False))


def _print_changes(changes: list[dict]) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Original", style="yellow")
    table.add_column("Canonical", style="green")
    table.add_column("Changed", justify="center")
    table.add_column("Occurrences", justify="right")

    for entry in changes:
        changed_str = "[bold green]yes[/bold green]" if entry["changed"] else "no"
        table.add_row(
            entry["original"],
            entry["canonical"],
            changed_str,
            str(entry["occurrences"]),
        )

    console.print(table)


def harmonize_csv(
    path: str | os.PathLike,
    column: str,
    *,
    output_path: str | os.PathLike | None = None,
    json_log_path: str | os.PathLike | None = None,
    csv_log_path: str | os.PathLike | None = None,
    canonical_column: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Load a CSV, diagnose sample-name inconsistencies, harmonize via LLM if needed,
    and write results with a new canonical column plus optional log files.

    Parameters
    ----------
    path:
        Path to the input CSV file.
    column:
        Column name containing the sample identifiers.
    output_path:
        If given, write the output CSV (input + canonical column) here.
    json_log_path:
        If given, write a JSON summary log here.
    csv_log_path:
        If given, write a CSV change log (original, canonical, changed, occurrences) here.
    canonical_column:
        Name for the new canonical column. Defaults to ``"{column}_canonical"``.
    api_key:
        OpenRouter API key. Falls back to OPENROUTER_API_KEY env var.
    model:
        OpenRouter model string. Falls back to OPENROUTER_MODEL env var.

    Returns
    -------
    tuple of (DataFrame with canonical column added, log dict)
    """
    path = Path(path)
    df = pd.read_csv(path)

    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in {path}. Available: {list(df.columns)}")

    if canonical_column is None:
        canonical_column = f"{column}_canonical"

    unique_names: list[str] = df[column].dropna().unique().tolist()

    # --- Diagnosis ---
    findings = diagnose(unique_names)
    _print_diagnosis(findings)

    # --- Harmonize (or skip) ---
    resolved_model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    if findings["verdict"] == "appears_consistent":
        console.print("[green]Names appear consistent — skipping LLM call.[/green]")
        mapping: dict[str, str] = {n: n for n in unique_names}
        canonical_pattern = "No changes needed (names already consistent)"
    else:
        console.print("[dim]Calling LLM to harmonize names…[/dim]")
        result = harmonize(unique_names, api_key=api_key, model=model)
        mapping = result["mapping"]
        canonical_pattern = result.get("canonical_pattern", "")

    # --- Map canonical names back to every row ---
    df[canonical_column] = df[column].map(lambda x: mapping.get(x, x) if pd.notna(x) else x)

    # --- Count occurrences per unique name ---
    value_counts = df[column].value_counts().to_dict()

    # --- Build changes list ---
    changes: list[dict] = []
    for original in unique_names:
        canonical = mapping.get(original, original)
        changes.append(
            {
                "original": original,
                "canonical": canonical,
                "changed": original != canonical,
                "occurrences": int(value_counts.get(original, 0)),
            }
        )

    names_changed = sum(1 for c in changes if c["changed"])
    names_unchanged = len(changes) - names_changed

    # --- Print change table and summary ---
    _print_changes(changes)
    console.print(
        f"\n[bold]{len(unique_names)}[/bold] unique names processed, "
        f"[bold green]{names_changed}[/bold green] changed, "
        f"[bold]{names_unchanged}[/bold] unchanged."
    )

    # --- Build log dict ---
    log: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_file": str(path.resolve()),
        "column": column,
        "canonical_column": canonical_column,
        "model": resolved_model,
        "diagnosis": findings,
        "canonical_pattern": canonical_pattern,
        "summary": {
            "total_rows": len(df),
            "unique_names": len(unique_names),
            "names_changed": names_changed,
            "names_unchanged": names_unchanged,
        },
        "changes": changes,
    }

    # --- Write outputs ---
    if output_path is not None:
        df.to_csv(output_path, index=False)
        console.print(f"[green]Output CSV written to {output_path}[/green]")

    if json_log_path is not None:
        with open(json_log_path, "w") as fh:
            json.dump(log, fh, indent=2)
        console.print(f"[green]JSON log written to {json_log_path}[/green]")

    if csv_log_path is not None:
        log_df = pd.DataFrame(changes)
        log_df.to_csv(csv_log_path, index=False)
        console.print(f"[green]CSV log written to {csv_log_path}[/green]")

    return df, log
