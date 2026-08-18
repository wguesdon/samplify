"""Diagnosis, proposal and application, for a CSV column of sample names.

This module holds no console output. The library returns data and the CLI in
:mod:`samplify.cli` renders it, so the same calls work inside a script.

The two halves are deliberately separate. :func:`propose_csv` may call a model.
:func:`apply_mapping` never does, so the result of applying a reviewed mapping
file is the same on any machine and on any day.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from typing import Any

import pandas as pd

from . import matching, rules
from .harmonizer import DEFAULT_PROVIDER, harmonize, resolve_base_url, resolve_model
from .mapping import Group, MappingFile


def is_the_same_file(destination: str | os.PathLike, source: str | os.PathLike) -> bool:
    """Report whether two paths name one file.

    A hard link is a second name for one file, and two names that differ still
    reach the same bytes. ``Path.resolve`` follows a symbolic link and knows
    nothing of a hard link, so comparing the resolved names let an output alias
    of the input through the guard and the input was overwritten.

    Args:
        destination: The path a command would write.
        source: A path the command reads.

    Returns:
        True when the two paths name one file, or when the destination does not
        exist yet and its resolved name equals the resolved source.
    """
    destination, source = Path(destination), Path(source)
    try:
        if destination.exists() and source.exists():
            return destination.samefile(source)
    except OSError:
        pass
    return destination.resolve() == source.resolve()


def _read_csv(path: Path, column: str) -> pd.DataFrame:
    """Read a CSV without letting pandas reinterpret an identifier.

    The default reader infers a type per column, and both of its guesses
    destroy a sample name. It reads ``007`` as the number 7 and drops the zero
    padding, and it reads the name ``NA`` as a missing value and deletes it.
    Every column is therefore read as text, and no value is treated as missing.

    Args:
        path: The CSV to read.
        column: The column of sample names, checked for a duplicate.

    Returns:
        The whole file as text.

    Raises:
        ValueError: If the column is absent, or if the header holds it twice.
    """
    # utf-8-sig, because pandas strips a byte order mark and the default
    # encoding does not. A file that Excel wrote starts with one, and the two
    # readers then disagreed about the first column name: this one saw
    # "\ufeffsample_id" and pandas saw "sample_id". The duplicate check below
    # read the wrong name and passed a file that holds the column twice.
    header: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh), [])
    if header.count(column) > 1:
        raise ValueError(
            f"Column {column!r} appears {header.count(column)} times in {path}. "
            f"pandas renames the second one, so half the names would be "
            f"invisible. Give each column its own name."
        )

    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if column not in df.columns:
        raise ValueError(
            f"Column {column!r} not found in {path}. Available: {list(df.columns)}"
        )
    return df


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
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
    timeout: float | None = None,
) -> MappingFile:
    """Cluster sample names and propose a canonical name for each cluster.

    Args:
        names: The raw sample names. Duplicates are collapsed.
        method: One of :data:`samplify.matching.METHODS`. ``"rules"`` applies
            the character-level rules only. ``"damerau"`` adds typo tolerance.
            ``"llm"`` sends every name to a model. ``"auto"`` clusters offline
            first and then sends one representative per cluster to the model,
            which keeps the request small.
        threshold: The lowest similarity that still counts as a match, for the
            distance backends.
        occurrences: How many rows carry each name.
        api_key: OpenRouter API key, for the backends that call a model.
        model: The model string.
        provider: ``"openrouter"`` or ``"ollama"``, for the backends that call a
            model.
        base_url: The server to call, for the backends that call a model.
        timeout: Seconds to wait for the answer.

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
    # Both reports hold pairs that samplify refuses to merge and a person has
    # to decide. The first differ by one digit and the second by one letter.
    near_misses = [
        list(pair)
        for pair in sorted(
            set(matching.find_near_misses(unique))
            | set(matching.find_letter_variants(unique))
        )
    ]
    canonical_pattern = ""
    used_model: str | None = None
    used_provider: str | None = None
    used_base_url: str | None = None

    if not unique:
        return MappingFile(groups=[], method=method, diagnosis=findings)

    corpus = matching.skeleton_corpus(unique, occurrences)

    if method in matching.OFFLINE_METHODS:
        clusters = matching.group_names(unique, method=method, threshold=threshold)
        groups = _build_groups(clusters, occurrences, method, corpus=corpus)

    elif method == "llm":
        result = harmonize(
            unique,
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
            timeout=timeout,
        )
        canonical_pattern = result.get("canonical_pattern", "")
        used_model = resolve_model(model, provider=provider)
        used_provider = provider
        used_base_url = resolve_base_url(provider, base_url)
        clusters, canonical = _cluster_by_canonical(unique, result["mapping"])
        groups = _build_groups(clusters, occurrences, method, canonical=canonical)

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
            # Two clusters can normalise to one representative, and a plain
            # dict then kept one of them and dropped the other, so a sample
            # disappeared from the file a person reviews. The members are
            # gathered under the shared representative instead, and the
            # identity split below takes them apart again.
            rep_to_cluster: dict[str, list[str]] = {}
            for representative, cluster in zip(representatives, offline):
                rep_to_cluster.setdefault(representative, []).extend(cluster)
            result = harmonize(
                sorted(rep_to_cluster),
                api_key=api_key,
                model=model,
                provider=provider,
                base_url=base_url,
                timeout=timeout,
            )
            canonical_pattern = result.get("canonical_pattern", "")
            used_model = resolve_model(model, provider=provider)
            used_provider = provider
            used_base_url = resolve_base_url(provider, base_url)
            clusters, canonical = _merge_clusters_by_model(rep_to_cluster, result["mapping"])
            groups = _build_groups(clusters, occurrences, "auto", canonical=canonical)

    return MappingFile(
        groups=groups,
        method=method,
        model=used_model,
        provider=used_provider,
        base_url=used_base_url,
        diagnosis=findings,
        near_misses=near_misses,
        canonical_pattern=canonical_pattern,
    )


def _split_by_identity(members: list[str]) -> list[list[str]]:
    """Split a list of names so that no group mixes two identities.

    A group holds one digit signature and no forbidden pair. The model paths
    assemble their groups from representatives, and a representative can carry
    members of more than one identity, so the assembled list is split again.

    Args:
        members: The names of one assembled group.

    Returns:
        One list per identity, each sorted, in a deterministic order.
    """
    by_signature: dict[tuple[str, ...], list[str]] = {}
    for member in members:
        by_signature.setdefault(matching.digit_signature(member), []).append(member)

    return [
        group
        for _, same_identity in sorted(by_signature.items())
        for group in matching.split_on_a_substitution(sorted(same_identity))
    ]


def _cluster_by_canonical(
    names: list[str],
    mapping: dict[str, str],
) -> tuple[list[list[str]], dict[str, str]]:
    """Group names that a model gave the same canonical form, and guard the digits.

    The identity rule applies to the model here exactly as it applies in
    :func:`_merge_clusters_by_model`. A model that gives one canonical name to
    ``p111`` and ``p112`` is refused, and each name keeps its own group.

    Args:
        names: The raw names.
        mapping: The model's mapping from original to canonical.

    Returns:
        The clusters, and the canonical name for the first member of each.
    """
    by_canonical: dict[str, list[str]] = {}
    for name in sorted(names):
        by_canonical.setdefault(mapping.get(name, name), []).append(name)

    clusters: list[list[str]] = []
    canonical: dict[str, str] = {}

    for canonical_name, members in sorted(by_canonical.items()):
        by_signature: dict[tuple[str, ...], list[str]] = {}
        for member in members:
            by_signature.setdefault(matching.digit_signature(member), []).append(member)

        canonical_signature = matching.digit_signature(canonical_name)
        canonical_skeleton = matching.letter_skeleton(canonical_name)
        for signature, safe_members in sorted(by_signature.items()):
            for group in matching.split_on_a_substitution(sorted(safe_members)):
                clusters.append(group)
                # The name belongs to one digit signature and one set of
                # letters. Giving it to the other halves of a refused merge
                # renames p112 to p111 at the apply step, which is the merge
                # the split just prevented.
                fits = signature == canonical_signature and (
                    len(safe_members) == len(group)
                    or matching.letter_skeleton(group[0]) == canonical_skeleton
                )
                if fits:
                    canonical[group[0]] = canonical_name
                else:
                    canonical[group[0]] = matching.rule_normalise(group[0]) or group[0]

    return clusters, canonical


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

        canonical_signature = matching.digit_signature(canonical_name)
        canonical_skeleton = matching.letter_skeleton(canonical_name)
        for signature, safe_reps in sorted(by_signature.items()):
            # The substitution rule reads the representatives, because those
            # are the names the model was shown and the names it joined.
            for kept_reps in matching.split_on_a_substitution(sorted(safe_reps)):
                gathered = sorted(m for rep in kept_reps for m in rep_to_cluster[rep])
                # One representative can carry members of more than one
                # identity, so the members are split as well as the
                # representatives.
                for members in _split_by_identity(gathered):
                    clusters.append(members)
                    # The name belongs to one digit signature and one set of
                    # letters. Giving it to the other halves of a refused merge
                    # would rename p112 to p111 at the apply step, which is the
                    # merge the split just prevented.
                    fits = (
                        signature == canonical_signature
                        and matching.digit_signature(members[0]) == canonical_signature
                        and (
                            len(safe_reps) == len(kept_reps)
                            or matching.letter_skeleton(kept_reps[0]) == canonical_skeleton
                        )
                    )
                    canonical[members[0]] = canonical_name if fits else (
                        matching.rule_normalise(members[0]) or members[0]
                    )

    return clusters, canonical


def propose_csv(
    path: str | os.PathLike,
    column: str,
    *,
    method: str = "auto",
    threshold: float = 0.85,
    api_key: str | None = None,
    model: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
    timeout: float | None = None,
) -> MappingFile:
    """Read a CSV column and propose a mapping for the names in it.

    Args:
        path: The input CSV file.
        column: The column holding the sample identifiers.
        method: The backend, as in :func:`propose`.
        threshold: The similarity threshold for the distance backends.
        api_key: OpenRouter API key.
        model: The model string.
        provider: ``"openrouter"`` or ``"ollama"``.
        base_url: The server to call.
        timeout: Seconds to wait for the answer.

    Returns:
        A mapping file with every group still marked ``proposed``, carrying the
        input path and the column so that ``apply`` needs neither again.

    Raises:
        FileNotFoundError: If the CSV does not exist.
        ValueError: If the column is not in the CSV.
    """
    path = Path(path)
    df = _read_csv(path, column)

    # An empty cell is not a sample name. It carries no identity, and a group
    # built from it would rename a row to nothing.
    names = [value for value in df[column].tolist() if value.strip()]
    occurrences = {k: int(v) for k, v in pd.Series(names).value_counts().items()}

    result = propose(
        sorted(set(names)),
        method=method,
        threshold=threshold,
        occurrences=occurrences,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        timeout=timeout,
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

    # Two groups landing on one name is the most consequential thing this tool
    # does, so the log records it whether or not apply refuses. A reviewed file
    # is allowed to hold one, because a person signed for it, and it still has
    # to be said out loud.
    collisions = mapping.collisions()
    # `is not True` and not `not ...`. Reading a file goes through a check that
    # refuses anything but a boolean, and a caller building a MappingFile in
    # Python does not. Every value except True is a refusal here, so the string
    # "false" cannot switch the guard off by being truthy.
    if collisions and mapping.reviewed is not True:
        detail = "; ".join(
            f"{name!r} from groups {ids}" for name, ids in list(collisions.items())[:5]
        )
        raise ValueError(
            f"{len(collisions)} canonical name(s) are produced by more than one group, "
            f"and this mapping records reviewed={mapping.reviewed!r}: {detail}. "
            f"Run 'samplify review' and decide, or edit the mapping file."
        )

    path = Path(resolved_data)
    df = _read_csv(path, resolved_column)

    # The mapping was built from one column of one file. Applying it to a file
    # that shares no name with it changes nothing, and the log still reports
    # every name in the mapping as changed.
    present = sum(1 for name in set(df[resolved_column]) if name in final_mapping)
    if final_mapping and not present:
        raise ValueError(
            f"No name of the mapping appears in column {resolved_column!r} of "
            f"{path}. The mapping was built from {mapping.input_file!r}. "
            f"Check the --data and --column options."
        )

    # Every output goes somewhere else, and this command reads two files. The
    # data CSV holds the original spelling and the mapping file holds the
    # decisions a person made, and neither survives being written over. One
    # character of a shell command is the difference between
    # --output clean.csv and --output data.csv.
    inputs = [("the input", path)]
    if mapping_path is not None:
        inputs.append(("the mapping file", Path(mapping_path)))
    for label, destination in (
        ("--output", output_path),
        ("--json-log", json_log_path),
        ("--csv-log", csv_log_path),
    ):
        if destination is None:
            continue
        for description, source in inputs:
            if is_the_same_file(destination, source):
                raise ValueError(
                    f"{label} points at {source}, which is {description}. "
                    f"samplify writes no output over a file it reads, so that "
                    f"the original spelling and the decisions both survive."
                )

    if canonical_column is None:
        canonical_column = f"{resolved_column}_canonical"

    if canonical_column == resolved_column:
        raise ValueError(
            f"The canonical column and the source column are both "
            f"{resolved_column!r}. samplify writes the canonical name in a new "
            f"column, so that the original spelling stays in the output."
        )
    if canonical_column in df.columns:
        raise ValueError(
            f"{path} already holds a column named {canonical_column!r}. "
            f"Pass --canonical-column with another name, so that no column of "
            f"the input is overwritten."
        )

    df[canonical_column] = df[resolved_column].map(lambda x: final_mapping.get(x, x))

    value_counts = df[resolved_column].value_counts().to_dict()
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
            # The count of rows, which is what a person checks against the
            # input. The counts above describe the mapping, and a mapping name
            # that no row carries counts in them and changes nothing here.
            "rows_changed": int((df[resolved_column] != df[canonical_column]).sum()),
        }
    )

    log: dict[str, Any] = {
        "collisions": {name: ids for name, ids in collisions.items()},
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
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
    timeout: float | None = None,
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
        model: The model string.
        provider: ``"openrouter"`` or ``"ollama"``.
        base_url: The server to call.
        timeout: Seconds to wait for the answer.
        method: The backend, as in :func:`propose`.
        threshold: The similarity threshold for the distance backends.

    Returns:
        A tuple of the DataFrame with the canonical column added, and the log.
    """
    mapping = propose_csv(
        path,
        column,
        method=method,
        threshold=threshold,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        timeout=timeout,
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
