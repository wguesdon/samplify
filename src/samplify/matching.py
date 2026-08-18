"""Deterministic matching of sample names, with no model call.

Three of the four backends in samplify run here. The ``rules`` backend applies
the character-level rules in :mod:`samplify.rules`. The ``hamming`` and
``levenshtein`` backends group names that survive those rules but still differ,
which is what a typo produces.

The identity guard
------------------

A distance measure on its own is not safe for sample names. ``p111`` and
``p112`` sit one Hamming step apart, and they are two different patients.
Merging them loses a row and reports no error.

Every function here therefore treats the digits of a name as its identity. Two
names are compared only when their digit sequence matches exactly, and the
typo tolerance applies to the letters alone. A pair whose digits differ is
never grouped, however similar the letters look.
"""

from __future__ import annotations

import re
from collections import Counter

from . import rules

#: Backends that need no API key.
OFFLINE_METHODS = ("rules", "hamming", "levenshtein", "damerau")

#: Every backend the CLI accepts.
METHODS = OFFLINE_METHODS + ("llm", "auto")

#: The distance used when a caller does not choose one. A transposition is one
#: keystroke, and Damerau-Levenshtein is the measure that agrees.
DEFAULT_DISTANCE = "damerau"

_DIGIT_RUN = re.compile(r"\d+")

#: The shortest letter skeleton for which one inserted, deleted or swapped
#: letter counts as a typing error on its own. Below this length the same edit
#: separates two real terms. ``wt`` and ``wnt`` are wildtype and the Wnt gene
#: family, ``t`` and ``tp`` are a treatment and a timepoint, and ``k`` and
#: ``ko`` are a plate letter and a knockout. A short name therefore has to
#: clear the ratio like any other pair.
MIN_SLIP_LENGTH = 5


# ── String distances ───────────────────────────────────────────────────────


def hamming_distance(a: str, b: str) -> int | None:
    """Count the positions at which two strings of equal length differ.

    Args:
        a: The first string.
        b: The second string.

    Returns:
        The number of differing positions, or None when the lengths differ.
        Hamming distance is undefined for strings of unequal length, so the
        caller must decide what to do rather than receive a misleading number.
    """
    if len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y)


def levenshtein_distance(a: str, b: str) -> int:
    """Count the single-character edits that turn one string into another.

    The edits counted are insertion, deletion and substitution. The
    implementation is the standard two-row dynamic program, which is enough for
    the short strings a sample name produces.

    Args:
        a: The first string.
        b: The second string.

    Returns:
        The edit distance between the two strings.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[j] + 1,      # deletion
                    current[j - 1] + 1,   # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1]


def damerau_levenshtein_distance(a: str, b: str) -> int:
    """Count the edits that turn one string into another, transposition included.

    This is the optimal string alignment variant. It counts insertion,
    deletion, substitution and the swap of two adjacent characters. The swap
    matters here: ``patietn`` for ``patient`` is one slip of the fingers, and
    plain Levenshtein charges two edits for it, which pushes a real typo below
    any sensible threshold.

    Args:
        a: The first string.
        b: The second string.

    Returns:
        The edit distance between the two strings.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    rows, cols = len(a) + 1, len(b) + 1
    grid = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        grid[i][0] = i
    for j in range(cols):
        grid[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            grid[i][j] = min(
                grid[i - 1][j] + 1,          # deletion
                grid[i][j - 1] + 1,          # insertion
                grid[i - 1][j - 1] + cost,   # substitution
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                grid[i][j] = min(grid[i][j], grid[i - 2][j - 2] + 1)  # transposition

    return grid[-1][-1]


def similarity(a: str, b: str, method: str = DEFAULT_DISTANCE) -> float:
    """Score how alike two strings are, on a scale of 0.0 to 1.0.

    Args:
        a: The first string.
        b: The second string.
        method: ``"damerau"``, ``"levenshtein"`` or ``"hamming"``.

    Returns:
        1.0 for identical strings and 0.0 for nothing in common. Two strings of
        unequal length score 0.0 under ``"hamming"``, because the measure does
        not apply to them.

    Raises:
        ValueError: If ``method`` is not a distance backend.
    """
    if a == b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0

    if method == "hamming":
        distance = hamming_distance(a, b)
        if distance is None:
            return 0.0
    elif method == "levenshtein":
        distance = levenshtein_distance(a, b)
    elif method == "damerau":
        distance = damerau_levenshtein_distance(a, b)
    else:
        raise ValueError(
            f"Unknown distance method: {method!r}. "
            f"Use 'damerau', 'levenshtein' or 'hamming'."
        )

    return 1.0 - (distance / longest)


# ── Identity and normalisation ─────────────────────────────────────────────


def digit_signature(name: str) -> tuple[str, ...]:
    """Extract the identity of a name, which is its sequence of numbers.

    Zero padding is removed, so that ``sample01`` and ``sample1`` share one
    signature. A letter run that follows a number is part of the identity only
    when no digit follows it. The ``a`` of ``sample_9a`` labels a replicate and
    stays. The ``b`` of ``p1b1`` introduces the next number of the name and
    goes, so that ``p1b1`` and ``p1_b1`` share one signature.

    A letter in any script counts, because a cohort that labels its replicates
    ``sample_9α`` and ``sample_9β`` names two samples exactly as ``9a`` and
    ``9b`` do.

    Args:
        name: A raw sample name.

    Returns:
        The numbers found in the name, in order, each without leading zeros and
        each carrying the letters that identify it.

    Example:
        >>> digit_signature("p111-batch03")
        ('111', '3')
        >>> digit_signature("sample_9a")
        ('9a',)
        >>> digit_signature("p1b1")
        ('1', '1')
    """
    lowered = name.lower()
    signature: list[str] = []
    index = 0

    while index < len(lowered):
        if not lowered[index].isdigit():
            index += 1
            continue

        start = index
        while index < len(lowered) and lowered[index].isdigit():
            index += 1
        digits = lowered[start:index]

        letters_start = index
        while index < len(lowered) and lowered[index].isalpha():
            index += 1
        suffix = lowered[letters_start:index]

        # A letter run with a digit behind it belongs to the next component of
        # the name. Read the letters again from the start of the run, so that
        # the number behind them opens its own component.
        if index < len(lowered) and lowered[index].isdigit():
            suffix = ""
            index = letters_start

        signature.append((digits.lstrip("0") or "0") + suffix)

    return tuple(signature)


def letter_skeleton(name: str) -> str:
    """Reduce a name to the lower-case letters it contains.

    The digits are the identity and the letters are the description, so the
    typo tolerance works on this value alone.

    Args:
        name: A raw sample name.

    Returns:
        The lower-case letters of the name, with every digit, delimiter and
        symbol removed.

    Example:
        >>> letter_skeleton("Patient-111_BatchA")
        'patientbatcha'
    """
    return "".join(c for c in name.lower() if c.isalpha())


def rule_normalise(name: str) -> str:
    """Apply the character-level rules to one name, with no model call.

    The rules are the delimiter, the case, the zero-padding, the character set
    and the abbreviation expansions defined in :mod:`samplify.rules`.

    Args:
        name: A raw sample name.

    Returns:
        The canonical form of the name.

    Example:
        >>> rule_normalise("Sample_1")
        'sample1'
        >>> rule_normalise("sample1")
        'sample1'
    """
    tokens = rules.split_tokens(name)
    if not tokens:
        return ""

    # A number belongs to the word in front of it. This runs before the
    # expansion so that s_8 and s8 both reach the abbreviation table as one
    # token. Without it, sample_1 and sample1 normalise to two different
    # strings, and the delimiter before a number is the most common difference
    # of all.
    joined_tokens: list[str] = []
    for token in tokens:
        if token.isdigit() and joined_tokens and not joined_tokens[-1][-1].isdigit():
            joined_tokens[-1] = joined_tokens[-1] + token
        else:
            joined_tokens.append(token)

    expanded = [piece for piece in (_expand_token(t) for t in joined_tokens) if piece]
    return rules.NON_IDENTIFIER.sub("", rules.CANONICAL_DELIMITER.join(expanded))


def _expand_token(token: str) -> str:
    """Expand one token against the abbreviation table.

    Args:
        token: A single lower-case token from a sample name.

    Returns:
        The expanded token, or the token unchanged when no rule applies.
    """
    for abbrev in rules.ABBREVIATIONS:
        for alias in abbrev.aliases:
            match = re.fullmatch(abbrev.alias_regex(alias), token)
            if match is None:
                continue
            number = _DIGIT_RUN.search(token)
            if number is None:
                return abbrev.canonical
            return f"{abbrev.canonical}{number.group().lstrip('0') or '0'}"

    # Not an abbreviation. Strip zero-padding from a bare number so that
    # sample_01 and sample_1 agree.
    if token.isdigit():
        return token.lstrip("0") or "0"

    # A word followed by a number, such as "sample007".
    split = re.fullmatch(r"([a-z]+)(\d+)", token)
    if split is not None:
        word, number = split.groups()
        return f"{word}{number.lstrip('0') or '0'}"

    return token


# ── Grouping ───────────────────────────────────────────────────────────────


class _UnionFind:
    """Disjoint-set structure used to merge pairs into groups."""

    def __init__(self, items: list[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        """Return the representative of the set holding ``item``."""
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        """Merge the sets holding ``a`` and ``b``."""
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Order the roots so that the result never depends on input order.
            first, second = sorted((root_a, root_b))
            self._parent[second] = first

    def groups(self) -> list[list[str]]:
        """Return every set, each sorted, in a deterministic order."""
        buckets: dict[str, list[str]] = {}
        for item in self._parent:
            buckets.setdefault(self.find(item), []).append(item)
        return [sorted(members) for _, members in sorted(buckets.items())]


def group_names(
    names: list[str],
    *,
    method: str = DEFAULT_DISTANCE,
    threshold: float = 0.85,
) -> list[list[str]]:
    """Group names that refer to the same sample.

    Two names join the same group when their digit signature matches exactly
    and their letter skeletons score at or above ``threshold``. Names whose
    digits differ never join, which is what keeps ``p111`` and ``p112`` apart.

    Args:
        names: The unique raw sample names.
        method: ``"rules"`` for exact agreement after normalisation, or
            ``"damerau"``, ``"levenshtein"`` or ``"hamming"`` for typo
            tolerance.
        threshold: The lowest similarity that still counts as a match. Ignored
            by the ``"rules"`` method.

    Returns:
        One list per group, each sorted, in a deterministic order. A name that
        matches nothing forms a group of one.

    Raises:
        ValueError: If ``method`` is not an offline backend.
    """
    if method not in OFFLINE_METHODS:
        raise ValueError(
            f"Unknown offline method: {method!r}. Use one of {OFFLINE_METHODS}."
        )
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"threshold must be between 0.0 and 1.0. Got {threshold}. "
            f"A similarity is a ratio, so a value outside that range either "
            f"merges every name in a block or merges none of them."
        )

    unique = sorted(set(names))
    union = _UnionFind(unique)

    # Blocking. Only names that share a digit signature are ever compared, so
    # the comparison count stays small and two different patients cannot merge.
    blocks: dict[tuple[str, ...], list[str]] = {}
    for name in unique:
        blocks.setdefault(digit_signature(name), []).append(name)

    for block in blocks.values():
        if len(block) < 2:
            continue
        for i, left in enumerate(block):
            for right in block[i + 1:]:
                if _matches(left, right, method=method, threshold=threshold):
                    union.union(left, right)

    return union.groups()


#: Edit kinds that a keystroke produces, whatever the length of the name.
SLIP_KINDS = ("insertion or deletion", "transposition")


def describe_difference(a: str, b: str) -> str:
    """Name the kind of difference between two sample names.

    The label explains why two names did or did not join a group, and it is
    what the review step and the QC report show to a person.

    Args:
        a: The first name.
        b: The second name.

    Returns:
        One of ``"identical"``, ``"formatting only"``, ``"insertion or
        deletion"``, ``"transposition"``, ``"substitution"``, ``"different
        identifiers"`` or ``"unrelated"``.
    """
    if a == b:
        return "identical"
    if digit_signature(a) != digit_signature(b):
        return "different identifiers"
    normalised = rule_normalise(a)
    if normalised and normalised == rule_normalise(b):
        return "formatting only"

    left, right = letter_skeleton(a), letter_skeleton(b)
    distance = damerau_levenshtein_distance(left, right)
    if distance != 1:
        return "unrelated"
    if len(left) != len(right):
        return "insertion or deletion"
    if levenshtein_distance(left, right) == 2:
        return "transposition"
    return "substitution"


def _matches(a: str, b: str, *, method: str, threshold: float) -> bool:
    """Report whether two names in the same block belong together.

    A single inserted, deleted or swapped letter matches on its own, provided
    both letter skeletons hold at least :data:`MIN_SLIP_LENGTH` letters. Those
    are the shapes a slipped keystroke makes, and a ratio threshold cannot see
    them in a short name: ``smple`` against ``sample`` scores 0.833, below any
    sensible cut, and it is plainly a typo.

    Below that length the same edit tells two real terms apart, so the pair has
    to clear the ratio like any other. ``wt`` and ``wnt`` differ by one inserted
    letter and they are wildtype and the Wnt gene family.

    A single substituted letter never gets that treatment, and must clear the
    ratio instead. A substitution is the one edit that also carries meaning.
    Cohorts label replicates ``sample1a`` and ``sample1b``, and those two names
    differ by exactly one substituted letter.

    Args:
        a: The first name.
        b: The second name.
        method: The offline backend in use.
        threshold: The lowest similarity that counts as a match.

    Returns:
        True when the two names should join one group.
    """
    left, right = letter_skeleton(a), letter_skeleton(b)

    # An empty normalised form is not agreement. Two names built only from
    # characters that the rules drop both normalise to the empty string, and
    # reading that as a match merges every one of them into one sample.
    normalised = rule_normalise(a)
    if normalised and normalised == rule_normalise(b):
        return True
    if method == "rules":
        return False

    # Two names with no letter at all score 1.0 against each other, because the
    # ratio compares two empty strings. A name of that shape carries no
    # evidence, so the ratio may not decide it. Two names that differ only in
    # their numbers already left this function at the blocking step.
    if not left or not right:
        return False

    if (
        method != "hamming"
        and min(len(left), len(right)) >= MIN_SLIP_LENGTH
        and describe_difference(a, b) in SLIP_KINDS
    ):
        return True

    return similarity(left, right, method=method) >= threshold


def find_near_misses(names: list[str]) -> list[tuple[str, str]]:
    """Find pairs that read alike and differ by one inserted or dropped digit.

    These pairs are the ones the grouping refuses to merge, because the digits
    are the identity. ``patient11`` and ``patient111`` are either two patients
    or one patient and a doubled keystroke, and no rule can tell which. The
    tool reports the pair and the person decides.

    A substituted digit is deliberately not reported. ``patient111`` and
    ``patient112`` differ that way, and so does almost every other pair of
    samples in a normal cohort, so reporting it would bury the real cases. An
    inserted or dropped digit changes the length of the number, which is the
    shape a slipped keystroke actually has.

    Args:
        names: The unique raw sample names.

    Returns:
        Every pair as a sorted tuple, in a deterministic order.
    """
    unique = sorted(set(names))
    by_skeleton: dict[str, list[str]] = {}
    for name in unique:
        by_skeleton.setdefault(letter_skeleton(name), []).append(name)

    series = _number_series(unique)

    pairs: list[tuple[str, str]] = []
    for skeleton, members in by_skeleton.items():
        if len(members) < 2:
            continue
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                if _one_digit_slip(
                    digit_signature(left), digit_signature(right), series, skeleton
                ):
                    pairs.append((left, right))
    return sorted(pairs)


def _number_series(names: list[str]) -> dict[tuple[str, int], set[int]]:
    """Collect the numbers the dataset uses at each position of each name shape.

    Args:
        names: The unique raw sample names.

    Returns:
        A dictionary from the letter skeleton and the component position to the
        whole numbers seen there.
    """
    series: dict[tuple[str, int], set[int]] = {}
    for name in names:
        skeleton = letter_skeleton(name)
        for index, component in enumerate(digit_signature(name)):
            if component.isdigit():
                series.setdefault((skeleton, index), set()).add(int(component))
    return series


def _one_digit_slip(
    left: tuple[str, ...],
    right: tuple[str, ...],
    series: dict[tuple[str, int], set[int]],
    skeleton: str,
) -> bool:
    """Report whether two signatures differ by one digit that looks like a slip.

    The comparison runs component by component. Joining the numbers into one
    string would lose the boundary between them, and ``patient11_batch2`` would
    then look like a slip of ``patient1_batch1``, which it is not.

    A pair is dropped when both numbers sit inside the numbering series the
    dataset already uses. In a cohort numbered 1 to 12, ``sample_1`` and
    ``sample_10`` differ by an inserted digit and both have a neighbour in the
    series, so both are ordinary members of it. In a cohort holding 11, 111 and
    112, the number 11 has no neighbour, so the pair 11 and 111 is worth a look.

    Args:
        left: The digit signature of the first name.
        right: The digit signature of the second name.
        series: The numbers the dataset uses, from :func:`_number_series`.
        skeleton: The letter skeleton shared by both names.

    Returns:
        True when the pair is worth reporting to a person.
    """
    if len(left) != len(right) or left == right:
        return False

    differing = [(index, a, b) for index, (a, b) in enumerate(zip(left, right)) if a != b]
    if len(differing) != 1:
        return False

    index, a, b = differing[0]
    if abs(len(a) - len(b)) != 1 or damerau_levenshtein_distance(a, b) != 1:
        return False

    if not (a.isdigit() and b.isdigit()):
        return True

    observed = series.get((skeleton, index), set())
    return not (_in_series(int(a), observed) and _in_series(int(b), observed))


def _in_series(value: int, observed: set[int]) -> bool:
    """Report whether a number has a neighbour in the numbers the dataset uses.

    Args:
        value: The number to test.
        observed: Every number seen at the same position of the same name shape.

    Returns:
        True when ``value - 1`` or ``value + 1`` also appears.
    """
    return (value - 1) in observed or (value + 1) in observed


def skeleton_corpus(names: list[str], occurrences: dict[str, int] | None = None) -> Counter[str]:
    """Count how often each letter skeleton appears across the whole dataset.

    A group of two spellings gives the medoid nothing to work with, because
    each name is one edit from the other. The rest of the dataset breaks that
    tie. In a file of twenty ``sample_n`` names, the skeleton ``sample``
    appears twenty times and ``sampel`` appears once, so the correct spelling
    is the one the dataset already agrees on.

    Args:
        names: Every raw name in the dataset.
        occurrences: How many rows carry each name.

    Returns:
        A counter from letter skeleton to weight.
    """
    corpus: Counter[str] = Counter()
    for name in names:
        weight = 1 if occurrences is None else max(occurrences.get(name, 1), 1)
        corpus[letter_skeleton(name)] += weight
    return corpus


def canonical_for_group(
    group: list[str],
    occurrences: dict[str, int] | None = None,
    corpus: Counter[str] | None = None,
) -> str:
    """Choose the canonical name for one group of names.

    The winner is the frequency-weighted medoid: the normalised form with the
    smallest total distance to every other form in the group, counting each
    form once per row it appears in.

    This is what separates the correct spelling from a typo. Each typo sits one
    edit from the correct form and two edits from the other typos, so the
    correct form is always the closest to the rest of the group, even when
    every spelling appears exactly once. Frequency then settles the ordinary
    case, where the right spelling is simply the common one.

    A group of exactly two spellings gives the medoid nothing to decide, so the
    rest of the dataset breaks that tie through ``corpus``. Ties then break
    towards the more frequent form, then the longer one, then the alphabetically
    first, so the result never depends on the input order.

    Args:
        group: The raw names that belong to one sample.
        occurrences: How many rows carry each raw name. A missing name counts
            once.
        corpus: How often each letter skeleton appears across the whole
            dataset, from :func:`skeleton_corpus`.

    Returns:
        The canonical name for the group.
    """
    weights: Counter[str] = Counter()
    for name in group:
        weight = 1 if occurrences is None else max(occurrences.get(name, 1), 1)
        # A name built only from characters that the rules drop normalises to
        # the empty string. Keep the raw name in that condition, because an
        # empty canonical name renames a sample to nothing.
        weights[rule_normalise(name) or name] += weight

    if len(weights) == 1:
        return next(iter(weights))

    def cost(candidate: str) -> tuple[int, int, int, int, str]:
        total = sum(
            weight * damerau_levenshtein_distance(candidate, other)
            for other, weight in weights.items()
        )
        agreement = 0 if corpus is None else corpus.get(letter_skeleton(candidate), 0)
        return (total, -agreement, -weights[candidate], -len(candidate), candidate)

    return min(weights, key=cost)
