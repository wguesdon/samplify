"""Diagnosis, proposal and application, for a CSV column of sample names.

This module holds no console output. The library returns data and the CLI in
:mod:`samplify.cli` renders it, so the same calls work inside a script.

The two halves are deliberately separate. :func:`propose_csv` may call a model.
:func:`apply_mapping` never does, so the result of applying a reviewed mapping
file is the same on any machine and on any day.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from typing import Any

import pandas as pd

from . import matching, rules
from .harmonizer import harmonize, resolve_model
from .mapping import Group, MappingFile


def diagnose(names: list[str]) -> dict:
    """Run heuristic checks on a list of sample names.

    The checks are cheap, they need no model, and they decide whether a model
    call is worth making at all.

    Args:
        names: Unique sample name strings to inspect.

    Returns:
        A dictionary with these keys.

        ``delimiter_mix``
            True when more than one delimiter style is present.
        ``abbreviations_detected``
            The abbreviations found, as labels from :mod:`samplify.rules`.
        ``zero_padding``
            True when the same number appears both padded and unpadded.
        ``case_mix``
            True when upper and lower case are both present.
        ``verdict``
            ``"inconsistencies_found"`` or ``"appears_consistent"``.
    """
    if not names:
        return {
            "delimiter_mix": False,
            "abbreviations_detected": [],
            "zero_padding": False,
            "case_mix": False,
            "verdict": "appears_consistent",
        }

    delimiters_used = {d for name in names for d in "_-." if d in name}
    delimiter_mix = len(delimiters_used) > 1

    abbreviations_detected = rules.detect_abbreviations(names)

    padded: set[str] = set()
    unpadded: set[str] = set()
    for name in names:
        for token in matching._DIGIT_RUN.findall(name):
            if len(token) > 1 and token.startswith("0"):
                padded.add(token.lstrip("0") or "0")
            else:
                unpadded.add(token)
    zero_padding = bool(padded & unpadded)

    has_upper = any(c.isupper() for name in names for c in name)
    has_lower = any(c.islower() for name in names for c in name)
    case_mix = has_upper and has_lower

    inconsistent = delimiter_mix or bool(abbreviations_detected) or zero_padding or case_mix
    return {
        "delimiter_mix": delimiter_mix,
        "abbreviations_detected": abbreviations_detected,
        "zero_padding": zero_padding,
        "case_mix": case_mix,
        "verdict": "inconsistencies_found" if inconsistent else "appears_consistent",
    }


def _min_similarity(members: list[str]) -> float | None:
    """Return the lowest pairwise similarity inside a group.

    Args:
        members: The raw names in one group.

    Returns:
        The lowest similarity of the letter skeletons, or None for a group of
        one.
    """
    if len(members) < 2:
        return None
    scores = [
        matching.similarity(
            matching.letter_skeleton(a),
            matching.letter_skeleton(b),
            method=matching.DEFAULT_DISTANCE,
        )
        for i, a in enumerate(members)
        for b in members[i + 1:]
    ]
    return round(min(scores), 4)


def _build_groups(
    clusters: list[list[str]],
    occurrences: dict[str, int],
    method: str,
    canonical: dict[str, str] | None = None,
    corpus: "Counter[str] | None" = None,
) -> list[Group]:
    """Turn clusters of names into numbered groups.

    Args:
        clusters: One list of member names per group.
        occurrences: How many rows carry each name.
        method: The backend that formed the clusters.
        canonical: An explicit canonical name per member, from a model call.
            When None, the canonical name is derived from the rules.
        corpus: How often each letter skeleton appears across the dataset, used
            to settle a two-member group.

    Returns:
        The groups, numbered from 1 in a deterministic order.
    """
    groups: list[Group] = []
    ordered = sorted(clusters, key=lambda c: (c[0], len(c)))

    for index, members in enumerate(ordered, start=1):
        if canonical is not None:
            proposed = canonical.get(members[0], matching.rule_normalise(members[0]))
        else:
            proposed = matching.canonical_for_group(members, occurrences, corpus)
        groups.append(
            Group(
                id=index,
                members=list(members),
                proposed=proposed,
                final=proposed,
                occurrences={m: occurrences.get(m, 0) for m in members},
                method=method,
                min_similarity=_min_similarity(members),
            )
        )
    return groups


def propose(
    names: list[str],
    *,
    method: str = "auto",
    threshold: float = 0.85,
    occurrences: dict[str, int] | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> MappingFile:
    """Cluster sample names and propose a canonical name for each cluster.

    Args:
        names: The raw sample names. Duplicates are collapsed.
        method: One of :data:`samplify.matching.METHODS`. ``"rules"`` applies
            the character-level rules only. ``"hamming"`` and ``"levenshtein"``
            add typo tolerance. ``"llm"`` sends every name to a model.
            ``"auto"`` clusters offline first and then sends one representative
            per cluster to the model, which keeps the request small.
        threshold: The lowest similarity that still counts as a match, for the
            distance backends.
        occurrences: How many rows carry each name.
        api_key: OpenRouter API key, for the backends that call a model.
        model: OpenRouter model string.

    Returns:
        A mapping file with every group still marked ``proposed``.

    Raises:
        ValueError: If ``method`` is not a known backend.
    """
    if method not in matching.METHODS:
        raise ValueError(f"Unknown method: {method!r}. Use one of {matching.METHODS}.")

    unique = sorted(set(names))
    occurrences = occurrences or {}
    findings = diagnose(unique)
    near_misses = [list(pair) for pair in matching.find_near_misses(unique)]
    canonical_pattern = ""
    used_model: str | None = None

    if not unique:
        return MappingFile(groups=[], method=method, diagnosis=findings)

    corpus = matching.skeleton_corpus(unique, occurrences)

    if method in matching.OFFLINE_METHODS:
        clusters = matching.group_names(unique, method=method, threshold=threshold)
        groups = _build_groups(clusters, occurrences, method, corpus=corpus)

    elif method == "llm":
        result = harmonize(unique, api_key=api_key, model=model)
        canonical_pattern = result.get("canonical_pattern", "")
        used_model = resolve_model(model)
        clusters = _cluster_by_canonical(unique, result["mapping"])
        groups = _build_groups(clusters, occurrences, method, canonical=result["mapping"])

    else:  # auto
        offline = matching.group_names(
            unique, method=matching.DEFAULT_DISTANCE, threshold=threshold
        )

        if findings["verdict"] == "appears_consistent" and all(len(c) == 1 for c in offline):
            # Nothing to fix and nothing to merge. Skip the model entirely.
            groups = _build_groups(offline, occurrences, "rules", corpus=corpus)
        else:
            representatives = [
                matching.canonical_for_group(c, occurrences, corpus) for c in offline
            ]
            rep_to_cluster = dict(zip(representatives, offline))
            result = harmonize(
                sorted(rep_to_cluster), api_key=api_key, model=model
            )
            canonical_pattern = result.get("canonical_pattern", "")
            used_model = resolve_model(model)
            clusters, canonical = _merge_clusters_by_model(rep_to_cluster, result["mapping"])
            groups = _build_groups(clusters, occurrences, "auto", canonical=canonical)

    return MappingFile(
        groups=groups,
        method=method,
        model=used_model,
        diagnosis=findings,
        near_misses=near_misses,
        canonical_pattern=canonical_pattern,
    )


def _cluster_by_canonical(names: list[str], mapping: dict[str, str]) -> list[list[str]]:
    """Group names that a model gave the same canonical form.

    Args:
        names: The raw names.
        mapping: The model's mapping from original to canonical.

    Returns:
        One list of members per canonical name, each sorted.
    """
    clusters: dict[str, list[str]] = {}
    for name in names:
        clusters.setdefault(mapping.get(name, name), []).append(name)
    return [sorted(members) for _, members in sorted(clusters.items())]


def _merge_clusters_by_model(
    rep_to_cluster: dict[str, list[str]],
    mapping: dict[str, str],
) -> tuple[list[list[str]], dict[str, str]]:
    """Merge offline clusters whose representatives agree, and guard the digits.

    The model may join two offline clusters that the distance backend kept
    apart. That merge is accepted only when the two representatives carry the
    same digit signature. A model that proposes joining ``p111`` and ``p112``
    is refused, because the numbers are the identity of the sample.

    Args:
        rep_to_cluster: One representative name per offline cluster.
        mapping: The model's mapping from representative to canonical name.

    Returns:
        The merged clusters, and the canonical name for the first member of
        each.
    """
    by_canonical: dict[str, list[str]] = {}
    for rep in sorted(rep_to_cluster):
        by_canonical.setdefault(mapping.get(rep, rep), []).append(rep)

    clusters: list[list[str]] = []
    canonical: dict[str, str] = {}

    for canonical_name, reps in sorted(by_canonical.items()):
        # Split the model's proposal back apart wherever the digits disagree.
        by_signature: dict[tuple[str, ...], list[str]] = {}
        for rep in reps:
            by_signature.setdefault(matching.digit_signature(rep), []).append(rep)

        for _, safe_reps in sorted(by_signature.items()):
            members = sorted(m for rep in safe_reps for m in rep_to_cluster[rep])
            clusters.append(members)
            canonical[members[0]] = canonical_name

    return clusters, canonical


def propose_csv(
    path: str | os.PathLike,
    column: str,
    *,
    method: str = "auto",
    threshold: float = 0.85,
    api_key: str | None = None,
    model: str | None = None,
) -> MappingFile:
    """Read a CSV column and propose a mapping for the names in it.

    Args:
        path: The input CSV file.
        column: The column holding the sample identifiers.
        method: The backend, as in :func:`propose`.
        threshold: The similarity threshold for the distance backends.
        api_key: OpenRouter API key.
        model: OpenRouter model string.

    Returns:
        A mapping file with every group still marked ``proposed``, carrying the
        input path and the column so that ``apply`` needs neither again.

    Raises:
        FileNotFoundError: If the CSV does not exist.
        ValueError: If the column is not in the CSV.
    """
    path = Path(path)
    df = pd.read_csv(path)
    if column not in df.columns:
        raise ValueError(
            f"Column {column!r} not found in {path}. Available: {list(df.columns)}"
        )

    names = df[column].dropna().astype(str).tolist()
    occurrences = {k: int(v) for k, v in pd.Series(names).value_counts().items()}

    result = propose(
        sorted(set(names)),
        method=method,
        threshold=threshold,
        occurrences=occurrences,
        api_key=api_key,
        model=model,
    )
    result.input_file = str(path.resolve())
    result.column = column
    return result


def apply_mapping(
    mapping: MappingFile,
    *,
    data_path: str | os.PathLike | None = None,
    column: str | None = None,
    output_path: str | os.PathLike | None = None,
    canonical_column: str | None = None,
    json_log_path: str | os.PathLike | None = None,
    csv_log_path: str | os.PathLike | None = None,
    mapping_path: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Apply a reviewed mapping to a CSV, with no model call.

    The original column is never overwritten. A new column holds the canonical
    name, so the input remains in the output and any decision stays reversible.

    Args:
        mapping: The reviewed mapping file.
        data_path: The CSV to apply it to. Defaults to the file recorded in the
            mapping.
        column: The column of sample names. Defaults to the column recorded in
            the mapping.
        output_path: Where to write the result. Nothing is written when None.
        canonical_column: The name of the new column. Defaults to
            ``"{column}_canonical"``.
        json_log_path: Where to write the JSON log.
        csv_log_path: Where to write the change table as CSV.
        mapping_path: The mapping file path, recorded in the log.

    Returns:
        A tuple of the DataFrame with the canonical column added, and the log.

    Raises:
        ValueError: If any group is still awaiting a decision, if two groups
            collide on one canonical name in a mapping no person reviewed, or
            if the column is missing.
        FileNotFoundError: If the CSV does not exist.
    """
    resolved_data = data_path or mapping.input_file
    if resolved_data is None:
        raise ValueError(
            "No data file given and the mapping file records none. Pass --data."
        )
    resolved_column = column or mapping.column
    if resolved_column is None:
        raise ValueError(
            "No column given and the mapping file records none. Pass --column."
        )

    # Raises while any group is still proposed.
    final_mapping = mapping.final_mapping()

    collisions = mapping.collisions()
    if collisions and not mapping.reviewed:
        detail = "; ".join(
            f"{name!r} from groups {ids}" for name, ids in list(collisions.items())[:5]
        )
        raise ValueError(
            f"{len(collisions)} canonical name(s) are produced by more than one group, "
            f"and no person reviewed this mapping: {detail}. "
            f"Run 'samplify review' and decide, or edit the mapping file."
        )

    path = Path(resolved_data)
    df = pd.read_csv(path)
    if resolved_column not in df.columns:
        raise ValueError(
            f"Column {resolved_column!r} not found in {path}. Available: {list(df.columns)}"
        )

    if canonical_column is None:
        canonical_column = f"{resolved_column}_canonical"

    df[canonical_column] = df[resolved_column].map(
        lambda x: final_mapping.get(str(x), x) if pd.notna(x) else x
    )

    value_counts = df[resolved_column].astype(str).value_counts().to_dict()
    changes = [
        {
            "original": original,
            "canonical": canonical_name,
            "changed": original != canonical_name,
            "occurrences": int(value_counts.get(original, 0)),
            "group": next(
                (g.id for g in mapping.groups if original in g.members), None
            ),
        }
        for original, canonical_name in sorted(final_mapping.items())
    ]

    names_changed = sum(1 for c in changes if c["changed"])
    summary = mapping.summary()
    summary.update(
        {
            "total_rows": len(df),
            "unique_names": len(changes),
            "names_changed": names_changed,
            "names_unchanged": len(changes) - names_changed,
        }
    )

    log: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_file": str(path.resolve()),
        "mapping_file": mapping_path,
        "column": resolved_column,
        "canonical_column": canonical_column,
        "method": mapping.method,
        "model": mapping.model,
        "reviewed": mapping.reviewed,
        "diagnosis": mapping.diagnosis,
        "canonical_pattern": mapping.canonical_pattern,
        "near_misses": mapping.near_misses,
        "summary": summary,
        "changes": changes,
    }

    if output_path is not None:
        df.to_csv(output_path, index=False)
    if json_log_path is not None:
        import json

        with open(json_log_path, "w") as fh:
            json.dump(log, fh, indent=2)
            fh.write("\n")
    if csv_log_path is not None:
        pd.DataFrame(changes).to_csv(csv_log_path, index=False)

    return df, log


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
    method: str = "auto",
    threshold: float = 0.85,
) -> tuple[pd.DataFrame, dict]:
    """Propose and apply in one call, with no review step.

    This is the one-shot path kept from version 0.1.0. It accepts every
    proposal, so the log it writes records ``reviewed: false``. Prefer
    :func:`propose_csv`, ``samplify review`` and :func:`apply_mapping` when a
    person is available to check the groups.

    Args:
        path: The input CSV file.
        column: The column holding the sample identifiers.
        output_path: Where to write the result CSV.
        json_log_path: Where to write the JSON log.
        csv_log_path: Where to write the change table as CSV.
        canonical_column: The name of the new column.
        api_key: OpenRouter API key.
        model: OpenRouter model string.
        method: The backend, as in :func:`propose`.
        threshold: The similarity threshold for the distance backends.

    Returns:
        A tuple of the DataFrame with the canonical column added, and the log.
    """
    mapping = propose_csv(
        path, column, method=method, threshold=threshold, api_key=api_key, model=model
    )
    mapping.accept_all()
    return apply_mapping(
        mapping,
        data_path=path,
        column=column,
        output_path=output_path,
        canonical_column=canonical_column,
        json_log_path=json_log_path,
        csv_log_path=csv_log_path,
    )
