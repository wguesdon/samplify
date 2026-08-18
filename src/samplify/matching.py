"""Deterministic matching of sample names, with no model call.

Both offline backends run here. The ``rules`` backend applies the
character-level rules in :mod:`samplify.rules`. The ``damerau`` backend also
groups names that survive those rules but still differ by one keystroke, which
is what a typing error produces.

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
import unicodedata
from collections import Counter
from functools import lru_cache

from . import rules

#: Backends that need no API key.
#:
#: Version 0.7.0 stopped merging on a substituted letter, and that removed the
#: reason for two of the four backends that used to be here. ``hamming`` finds a
#: substituted character in a name of equal length and nothing else, so it
#: became a second name for ``rules``. ``levenshtein`` and ``damerau`` differ
#: only in what they charge for a transposition, and at a cap of one edit the
#: slip rule decides that case for both, so it became a second name for
#: ``damerau``. A choice that does not change the answer is worse than no
#: choice, because a person reads the name and believes it.
#:
#: :func:`hamming_distance`, :func:`levenshtein_distance` and
#: :func:`similarity` still take all three measures. The measures are correct
#: and a caller may want them. It is the backend list that shrank.
OFFLINE_METHODS = ("rules", "damerau")

#: Every backend the CLI accepts.
METHODS = OFFLINE_METHODS + ("llm", "auto")

#: The distance used when a caller does not choose one. A transposition is one
#: keystroke, and Damerau-Levenshtein is the measure that agrees.
DEFAULT_DISTANCE = "damerau"

#: A run of decimal digits. ``\d`` matches a decimal digit in every script, and
#: :func:`int` reads exactly those. Every test for a number in this module uses
#: ``str.isdecimal`` for the same reason. ``str.isdigit`` also accepts a
#: superscript such as ``²``, which :func:`int` then refuses, and a name holding
#: one crashed the near-miss search.
_DIGIT_RUN = re.compile(r"\d+")

#: The shortest letter skeleton for which one inserted, deleted or swapped
#: letter counts as a typing error on its own. Below this length the same edit
#: separates two real terms. ``wt`` and ``wnt`` are wildtype and the Wnt gene
#: family, ``t`` and ``tp`` are a treatment and a timepoint, and ``k`` and
#: ``ko`` are a plate letter and a knockout. A short name therefore has to
#: clear the ratio like any other pair.
#:
#: The value is measured and not chosen. Eleven pairs in the reference corpus
#: turn on this rule alone, which means the ratio refuses them and only the
#: rule can join them. Their shortest skeletons run from 1 to 4 letters, and
#: every one of the eleven is two different samples: ``KMM-1`` against ``MM1``
#: are two myeloma cell lines, ``SMB`` against ``USMB`` differ by a prefix, and
#: ``CPT2`` against ``CPT2-H`` differ by a condition. Five is therefore the
#: smallest value that refuses all eleven. No pair of five letters or more in
#: that corpus turns on the rule, so a larger value would change nothing there
#: and would only give up the short typing errors the rule exists for.
MIN_SLIP_LENGTH = 5

#: The most edits that samplify accepts between the letters of two names it
#: merges. A slipped keystroke is one edit, and it is one edit whatever the
#: length of the name.
#:
#: A ratio cannot say that on its own, because a ratio scales with the length
#: and a long shared context then hides a short difference that carries the
#: whole identity. On 20000 real ENA runs samplify merged
#: ``EVT-TS-1_paired-RNA`` with ``ST-TS-1_paired-RNA``, which are two cell
#: types two edits and a ratio of 0.857 apart. It merged
#: ``Mock_SKNSH transcriptome after vector transfection`` with the same name
#: written ``Mock_TGW``, which are two cell lines five edits and a ratio of
#: 0.889 apart. Both real typing errors in the same corpus were one edit apart.
#:
#: The cap costs a name with two typing errors, which stays in its own group. A
#: person then reads two samples where there is one, and that is the failure
#: this tool prefers. A wrong merge drops a row and reports nothing.
#:
#: The cap governs one pair, and a group is built from many pairs, so a chain of
#: one-edit steps can hold two ends that are two edits apart. That is deliberate
#: and it is not the case that :func:`split_on_a_substitution` repairs. A chain
#: carries evidence: some third name in the group is one edit from both ends,
#: and it is the reason to believe the two are one sample. A substitution
#: carries the opposite, because that edit usually marks a different sample and
#: no intermediate name changes what the letters mean. The reference corpus of
#: 390 study and field combinations holds no group at all in which a pair joined
#: by a distance sits above the cap.
MAX_TYPO_EDITS = 1

#: The most letters that may stand at one position before
#: :func:`find_letter_variants` treats that position as a field of the naming
#: scheme rather than a typing error. A 96-well plate writes ``A07`` through
#: ``H07``, and eight row letters stand at one position. Reporting the 28 pairs
#: that a plate row produces buries the two or three that matter. One study of
#: the reference corpus, PRJEB20147, held 1351 plate wells and produced 1754
#: such pairs.
#:
#: The value is measured and not chosen. In that corpus 1002 positions hold
#: exactly two letters and 349 hold three or more. Every position of three or
#: more that was read is a plate well or a replicate letter, such as
#: ``RNA-seq_A549_24h_A01`` through ``D01``, which is a field of the scheme and
#: not a typing error. The positions holding two letters carry the real
#: contrasts, such as ``3C1`` against ``3N1``. Two is therefore the value that
#: keeps the contrasts and drops the fields.
MAX_VARIANT_LETTERS = 2

#: The characters that identify a sample where they stand. A hyphen is here
#: because :func:`samplify.rules.prepare` has already replaced every hyphen
#: that separates two tokens, so any hyphen left is a sign.
_SIGN_CHARACTERS = frozenset(rules.IDENTITY_SIGNS + rules.HYPHENS)


def clear_name_caches() -> None:
    """Empty the caches of the three functions that read a raw name.

    The rules do not change during a run of the command line, so nothing calls
    this in production. A test that changes a rule at run time has to, because
    a cache entry made under the old rule would otherwise survive the change
    and decide a merge.
    """
    digit_signature.cache_clear()
    letter_skeleton.cache_clear()
    rule_normalise.cache_clear()


# ── String distances ───────────────────────────────────────────────────────


#: The size of the cache on the three functions that read a raw name. Each one
#: is a pure function of one string, and each one runs many times for the same
#: name: `rule_normalise` ran 86625 times for the 2267 unique names of one real
#: study, because every comparison reads both of its names again. The cache
#: holds far more names than a metadata table carries and it never grows past
#: this bound.
#:
#: A caller that changes a rule at run time, which a test may do, has to call
#: :func:`clear_name_caches`. The rules do not change during a run of the
#: command line.
NAME_CACHE_SIZE = 100_000


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


def damerau_levenshtein_distance(a: str, b: str, max_distance: int | None = None) -> int:
    """Count the edits that turn one string into another, transposition included.

    This is the optimal string alignment variant. It counts insertion,
    deletion, substitution and the swap of two adjacent characters. The swap
    matters here: ``patietn`` for ``patient`` is one slip of the fingers, and
    plain Levenshtein charges two edits for it, which pushes a real typo below
    any sensible threshold.

    A caller that only needs to know whether the distance is small passes
    ``max_distance``. The work then stays inside a band of that width around
    the diagonal, because a path that leaves the band already costs more than
    the band. The full grid costs the product of the two lengths, and the band
    costs the length times the width. Two sample titles of 100 characters are
    10000 cells and 300 cells respectively.

    Args:
        a: The first string.
        b: The second string.
        max_distance: The largest distance the caller cares about. The result
            is exact at or below this value, and it is ``max_distance + 1`` for
            every distance above it.

    Returns:
        The edit distance between the two strings, capped as described above.
    """
    if a == b:
        return 0
    if not a:
        return len(b) if max_distance is None else min(len(b), max_distance + 1)
    if not b:
        return len(a) if max_distance is None else min(len(a), max_distance + 1)

    rows, cols = len(a) + 1, len(b) + 1
    if max_distance is not None and abs(len(a) - len(b)) > max_distance:
        # One string cannot reach the other without that many insertions.
        return max_distance + 1

    band = max(rows, cols) if max_distance is None else max_distance
    # Any value above every real distance, for the cells outside the band.
    beyond = max(rows, cols)

    grid = [[beyond] * cols for _ in range(rows)]
    for i in range(min(rows, band + 1)):
        grid[i][0] = i
    for j in range(min(cols, band + 1)):
        grid[0][j] = j

    for i in range(1, rows):
        low = max(1, i - band)
        high = min(cols - 1, i + band)
        if low > high:
            break
        for j in range(low, high + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            best = min(
                grid[i - 1][j] + 1,          # deletion
                grid[i][j - 1] + 1,          # insertion
                grid[i - 1][j - 1] + cost,   # substitution
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                best = min(best, grid[i - 2][j - 2] + 1)  # transposition
            grid[i][j] = best

        if max_distance is not None and min(grid[i][low:high + 1]) > max_distance:
            # Every path still open already costs more than the caller asked for.
            return max_distance + 1

    distance = grid[-1][-1]
    if max_distance is not None and distance > max_distance:
        return max_distance + 1
    return distance


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


@lru_cache(maxsize=NAME_CACHE_SIZE)
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

    A sign that :mod:`samplify.rules` keeps also joins the signature, after the
    numbers. ``dox+`` and ``dox-`` are the induced and the uninduced arm of one
    experiment, and nothing else in the two names differs.

    Example:
        >>> digit_signature("p111-batch03")
        ('111', '3')
        >>> digit_signature("sample_9a")
        ('9a',)
        >>> digit_signature("p1b1")
        ('1', '1')
        >>> digit_signature("ovtoko_dox+_br1")
        ('1', '+')
    """
    lowered = rules.prepare(name)
    signature: list[str] = []
    index = 0

    while index < len(lowered):
        if not lowered[index].isdecimal():
            index += 1
            continue

        start = index
        while index < len(lowered) and lowered[index].isdecimal():
            index += 1
        digits = lowered[start:index]

        letters_start = index
        while index < len(lowered) and lowered[index].isalpha():
            index += 1
        suffix = lowered[letters_start:index]

        # A letter run with a digit behind it belongs to the next component of
        # the name. Read the letters again from the start of the run, so that
        # the number behind them opens its own component.
        if index < len(lowered) and lowered[index].isdecimal():
            suffix = ""
            index = letters_start

        signature.append(_without_padding(digits) + suffix)

    # The signs come after the numbers, so that adding one never moves the
    # position of a number. The near-miss search reads a number by its position.
    #
    # A sign between two numbers is told from a sign after them, because each
    # one records how many numbers stand before it. `cd4+_donor1` and
    # `cd+4_donor1` still share a signature, since both hold one sign after no
    # number, and of the 17683 names in the reference corpus that hold a sign,
    # exactly one pair differs only in the order of its characters, and that
    # pair moved a number rather than a sign.
    # A sign joins the signature, and so does any other character that the rules
    # can neither read nor safely drop. See
    # :func:`_identifies_but_cannot_be_read`.
    #
    # Each one carries the count of numbers that stand before it, so that
    # `control+_batch1` and `control_batch1+` differ. The numbers keep the
    # first places of the signature and their positions never move, because the
    # near-miss search reads a number by its position.
    runs = 0
    inside_a_number = False
    for character in lowered:
        if character.isdecimal():
            if not inside_a_number:
                runs += 1
                inside_a_number = True
            continue
        inside_a_number = False
        if character in _SIGN_CHARACTERS or _identifies_but_cannot_be_read(character):
            signature.append(f"{runs}{character}")

    return tuple(signature)


def _without_padding(digits: str) -> str:
    """Remove the leading zeros of a run of digits, in any script.

    ``str.lstrip("0")`` removes the ASCII zero and nothing else, so the
    Arabic-Indic ``٠١`` kept its padding while ``01`` lost it. The two spellings
    of a number then had different identities and never grouped. Every place
    that removes padding calls this one function, in the signature and in the
    normalisation alike, so the two cannot disagree.

    The digits keep their own script. ``sample١`` and ``sample1`` hold the same
    number in two scripts, and they stay apart for the same reason that
    ``sample_9α`` and ``sample_9a`` stay apart.

    Args:
        digits: A run of decimal digits.

    Returns:
        The run without its leading zeros, and ``"0"`` when every digit is one.
    """
    trimmed = digits
    while len(trimmed) > 1 and unicodedata.decimal(trimmed[0], None) == 0:
        trimmed = trimmed[1:]
    return trimmed


def _identifies_but_cannot_be_read(character: str) -> bool:
    """Report whether one character identifies a sample and defeats every rule.

    Two shapes reach this function, and normalisation would delete both.

    A superscript such as ``²`` is alphanumeric, it is neither a letter nor a
    decimal digit, and :func:`int` cannot read it. A combining mark such as the
    dot above is what ``İ`` becomes when it is lower-cased, and dropping it
    makes ``sampleİ1`` the same name as ``sampleI1``. Two names that differ by a
    Greek letter already stay apart, so two names that differ by a mark have to
    as well.

    Neither shape appears in any of the 36073 names of the reference corpus, so
    keeping them costs nothing there. Each one keeps two names apart rather than
    guessing which of them the rules meant to delete.

    Args:
        character: One character of a prepared name.

    Returns:
        True when the character belongs in the identity signature.
    """
    if character.isalpha() or character.isdecimal():
        return False
    if character.isalnum():
        return True
    return unicodedata.category(character).startswith("M")


@lru_cache(maxsize=NAME_CACHE_SIZE)
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


@lru_cache(maxsize=NAME_CACHE_SIZE)
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
        if token.isdecimal() and joined_tokens and not joined_tokens[-1][-1].isdecimal():
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
    for pattern, abbreviation, _ in rules.COMPILED_ALIASES:
        if pattern.fullmatch(token) is None:
            continue
        number = _DIGIT_RUN.search(token)
        if number is None:
            return abbreviation.canonical
        return f"{abbreviation.canonical}{_without_padding(number.group())}"

    # Not an abbreviation. Strip zero-padding from a bare number so that
    # sample_01 and sample_1 agree.
    if token.isdecimal():
        return _without_padding(token)

    # A word followed by a number, such as "sample007".
    # The letters are matched in any script, and a letter run may follow the
    # number. An ASCII-only class left `пациент٠١` with its padding, and a
    # pattern that ended at the digits left `sample001a` with its own, so the
    # rules backend kept two spellings of one sample apart in both cases.
    split = re.fullmatch(r"([^\W\d_]+)(\d+)([^\W\d_]*)", token)
    if split is not None:
        word, number, suffix = split.groups()
        return f"{word}{_without_padding(number)}{suffix}"

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


def split_on_a_substitution(members: list[str]) -> list[list[str]]:
    """Split a cluster the model formed when one substituted letter sits inside it.

samplify never merges two names that differ by one substituted letter,
    because that edit carries meaning far more often than it is a typing error.
    :func:`_matches` decides one pair at a time, and grouping is transitive, so
    a chain of allowed edits can still carry a forbidden pair into one group.
    ``abcde1`` is one deletion from ``abcdef1`` and one deletion from
    ``abcdeg1``, and those two ends are one substitution apart. Every caller
    that forms a group therefore runs this check over the finished group.

    The model backends run it too. Without it a model that answers
    ``primary_cells`` for both merges ``Primary B cells`` with
    ``Primary T cells``.

    A forbidden pair anywhere in the group means the letters were read wrongly,
    so the whole group falls back to one group per letter skeleton. A group with
    no forbidden pair is left alone, which is what lets the model still join
    ``ctrl_1`` with ``control_1``. Those two are three edits apart and no rule
    here refuses them.

    Args:
        members: The names of one finished group.

    Returns:
        One list per group, each sorted, in a deterministic order.
    """
    for index, left in enumerate(members):
        for right in members[index + 1:]:
            if describe_difference(left, right) == "substitution":
                by_skeleton: dict[str, list[str]] = {}
                for member in members:
                    by_skeleton.setdefault(
                        letter_skeleton(member), []
                    ).append(member)
                return [sorted(group) for _, group in sorted(by_skeleton.items())]
    return [sorted(members)]


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
            ``"damerau"`` for typo tolerance.
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

    # Grouping is transitive and the match rule is not, so a chain of allowed
    # edits can carry a forbidden pair into one group.
    return sorted(
        group
        for members in union.groups()
        for group in split_on_a_substitution(members)
    )


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
    # The numbers agree, because the signatures did, and the letters agree too.
    # Whatever is left differs in punctuation or in zero padding, and that is
    # formatting. `malaria5#02` and `malaria5#2` reach this line, because the
    # number sign stops the token from reaching the zero-padding rule.
    if left == right:
        return "formatting only"
    if damerau_levenshtein_distance(left, right, max_distance=1) != 1:
        return "unrelated"
    if len(left) != len(right):
        return "insertion or deletion"

    # The two strings are the same length and one edit apart, so the difference
    # is one substitution or one swap of two adjacent characters. Reading the
    # positions costs the length of the name, and a second distance over the
    # whole grid costs its square.
    differing = [i for i, (x, y) in enumerate(zip(left, right)) if x != y]
    if (
        len(differing) == 2
        and differing[1] == differing[0] + 1
        and left[differing[0]] == right[differing[1]]
        and left[differing[1]] == right[differing[0]]
    ):
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

    A single substituted letter never merges two names at all. It is the one
    edit that also carries meaning, and :func:`find_letter_variants` reports the
    pair instead.

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

    # A slipped keystroke is one edit whatever the length of the name, and the
    # cap says so at every length. A ratio cannot, because it scales with the
    # length: EVT-TS-1_paired-RNA and ST-TS-1_paired-RNA are two cell types,
    # they are two edits apart and they score 0.857.
    if damerau_levenshtein_distance(left, right, max_distance=MAX_TYPO_EDITS) > MAX_TYPO_EDITS:
        return False

    # A substituted letter never merges on its own. It is the one edit that
    # also carries meaning, and on 20000 real ENA runs it carried meaning every
    # time: Primary B cells against Primary T cells, cTEC against mTEC, Decell
    # against Recell, TSmatKO against TSpatKO. Not one of the 42 pairs it
    # merged there was a typing error. :func:`find_letter_variants` reports the
    # pair instead, so a person still sees it.
    difference = describe_difference(a, b)
    if difference == "substitution":
        return False

    if min(len(left), len(right)) >= MIN_SLIP_LENGTH and difference in SLIP_KINDS:
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

    The search is indexed and not pairwise. A reportable pair agrees on its
    letters and on every number but one, so samplify indexes the names by that
    agreement and then looks up the one number that is allowed to differ. The
    pairwise form read every pair inside one letter skeleton, and a cohort
    written to one convention holds all of its names in one skeleton. On 6168
    names of that shape the pairwise form took 34.5 seconds and this one takes
    0.03 seconds, with the same result.

    Args:
        names: The unique raw sample names.

    Returns:
        Every pair as a sorted tuple, in a deterministic order.
    """
    unique = sorted(set(names))
    series = _number_series(unique)

    # One entry per name and per position of its signature. The key holds
    # everything that a reportable pair has to agree on, so the names under one
    # key differ at that position alone.
    buckets: dict[tuple[str, int, tuple[str, ...], tuple[str, ...]], dict[str, list[str]]] = {}
    for name in unique:
        skeleton = letter_skeleton(name)
        signature = digit_signature(name)
        for index, component in enumerate(signature):
            key = (skeleton, index, signature[:index], signature[index + 1:])
            buckets.setdefault(key, {}).setdefault(component, []).append(name)

    pairs: set[tuple[str, str]] = set()
    for (skeleton, index, _, _), by_component in buckets.items():
        if len(by_component) < 2:
            continue
        for longer, holders in by_component.items():
            # A pair whose two numbers differ by one inserted or dropped
            # character is a pair in which the shorter number is the longer one
            # with one character removed. Generating those removals costs one
            # lookup for each character, and reading every pair costs the
            # square of the number of names.
            for shorter in _one_character_deletions(longer):
                others = by_component.get(shorter)
                if others is None:
                    continue
                if not _slip_is_reportable(shorter, longer, series, skeleton, index):
                    continue
                for left in holders:
                    for right in others:
                        if left != right:
                            pairs.add((min(left, right), max(left, right)))

    return sorted(pairs)


def find_letter_variants(names: list[str]) -> list[tuple[str, str]]:
    """Find pairs that carry one substituted letter and the same numbers.

    A substitution is the one edit that also carries meaning, so samplify never
    merges on it. The pair still deserves a person, because the same shape also
    describes a real typing error. This function reports it.

    The evidence is a run over 20000 human RNA-seq runs of the ENA archive.
    Every one of the 42 pairs that a substitution merged there was two
    different samples. ``Primary B cells`` against ``Primary T cells`` and
    ``human cTEC5`` against ``human mTEC5`` are two of them.

    A position that many letters occupy is a field of the naming scheme and not
    a typing error, so samplify drops it. A 96-well plate writes ``A07`` and
    ``E07``, and eight row letters stand at that position. Reporting every pair
    of them buries the real cases, exactly as reporting every substituted digit
    would. :data:`MAX_VARIANT_LETTERS` holds the limit.

    The search is indexed. Two names one substitution apart agree on their
    numbers, on the length of their letters and on every letter but one, so
    samplify builds one key from that agreement and reads the letters that
    differ under it.

    Args:
        names: The unique raw sample names.

    Returns:
        Every pair as a sorted tuple, in a deterministic order.
    """
    unique = sorted(set(names))

    buckets: dict[tuple[tuple[str, ...], str, str], dict[str, list[str]]] = {}
    for name in unique:
        signature = digit_signature(name)
        skeleton = letter_skeleton(name)
        for index in range(len(skeleton)):
            key = (signature, skeleton[:index], skeleton[index + 1:])
            buckets.setdefault(key, {}).setdefault(skeleton[index], []).append(name)

    pairs: set[tuple[str, str]] = set()
    for by_letter in buckets.values():
        if not 2 <= len(by_letter) <= MAX_VARIANT_LETTERS:
            continue
        letters = sorted(by_letter)
        for position, letter in enumerate(letters):
            for other in letters[position + 1:]:
                for left in by_letter[letter]:
                    for right in by_letter[other]:
                        if left != right:
                            pairs.add((min(left, right), max(left, right)))

    return sorted(pairs)


def _one_character_deletions(value: str) -> set[str]:
    """Return every string that ``value`` becomes when one character is removed.

    Args:
        value: One component of a digit signature, such as ``"111"`` or ``"9a"``.

    Returns:
        The distinct results. ``"111"`` gives ``{"11"}`` and ``"9a"`` gives
        ``{"9", "a"}``.
    """
    return {value[:i] + value[i + 1:] for i in range(len(value))}


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
            if component.isdecimal():
                series.setdefault((skeleton, index), set()).add(int(component))
    return series


def _slip_is_reportable(
    shorter: str,
    longer: str,
    series: dict[tuple[str, int], set[int]],
    skeleton: str,
    index: int,
) -> bool:
    """Report whether one component of a pair is worth showing to a person.

    The caller has already established that the two names agree on their
    letters and on every other component, and that ``shorter`` is ``longer``
    with one character removed. That comparison runs component by component.
    Joining the numbers into one string would lose the boundary between them,
    and ``patient11_batch2`` would then look like a slip of
    ``patient1_batch1``, which it is not.

    A pair is dropped when both numbers sit inside the numbering series the
    dataset already uses. In a cohort numbered 1 to 12, ``sample_1`` and
    ``sample_10`` differ by an inserted digit and both have a neighbour in the
    series, so both are ordinary members of it. In a cohort holding 11, 111 and
    112, the number 11 has no neighbour, so the pair 11 and 111 is worth a look.

    Args:
        shorter: The shorter of the two components.
        longer: The longer of the two components.
        series: The numbers the dataset uses, from :func:`_number_series`.
        skeleton: The letter skeleton shared by both names.
        index: The position of the component in the signature.

    Returns:
        True when the pair is worth reporting to a person.
    """
    if not (shorter.isdecimal() and longer.isdecimal()):
        return True

    observed = series.get((skeleton, index), set())
    return not (_in_series(int(shorter), observed) and _in_series(int(longer), observed))


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
