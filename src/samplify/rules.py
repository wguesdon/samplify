"""Normalisation rules, defined once and shared by every consumer.

Version 0.1.0 held the abbreviation list twice: once as prose inside the LLM
system prompt, and once as a regex table used by the CSV diagnosis. The two
copies had already drifted, so the diagnosis could report an abbreviation that
the prompt never expanded. Every rule now lives here, and both the prompt
builder and the diagnosis read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The only delimiter a canonical name may contain.
CANONICAL_DELIMITER = "_"

#: Characters treated as delimiters when a name is split into tokens. The
#: hyphen is not here, because it is a delimiter only in one position. See
#: :func:`prepare`.
DELIMITER_PATTERN = r"[_.\s]"

#: Characters that carry meaning where they stand and are never delimiters. A
#: cohort writes ``CD4+`` and ``CD4-`` for two populations, and ``DOX+`` and
#: ``DOX-`` for the induced and the uninduced arm of one experiment. A prime
#: marks a variant of a name that is otherwise the same, as in ``WT2-1'``.
#: Deleting any of them merges two different samples.
#:
#: The number sign is deliberately absent. In ``#111_b2`` it reads as the word
#: number and identifies nothing, and no name in the reference corpus used it
#: as a sign. The asterisk is absent for the same reason, because it marks a
#: footnote more often than a sample.
IDENTITY_SIGNS = (
    "+'"
    "\u2032"  # PRIME, which a laboratory writes for a variant of a name
    "\u2033"  # DOUBLE PRIME
    "\u2019"  # RIGHT SINGLE QUOTATION MARK, which a word processor makes of '
    "\u00b1"  # PLUS-MINUS SIGN
    "\uff0b"  # FULLWIDTH PLUS SIGN
)

#: Every character a keyboard, a word processor or a journal uses for a hyphen
#: or a minus. `CD4−` with a Unicode minus and `CD4-` with the ASCII one mean
#: the same, and each one identifies a sample where it stands.
HYPHENS = (
    "-"
    "\u2010"  # HYPHEN
    "\u2011"  # NON-BREAKING HYPHEN
    "\u2012"  # FIGURE DASH
    "\u2013"  # EN DASH
    "\u2014"  # EM DASH
    "\u2015"  # HORIZONTAL BAR
    "\u2212"  # MINUS SIGN
    "\uff0d"  # FULLWIDTH HYPHEN-MINUS
)

#: Every spelling of one sign folds to one character before any reader sees the
#: name. The tables above make the typographic forms count as signs, and the
#: identity signature then kept the raw character, so `CD4-` with the ASCII
#: hyphen and `CD4−` with the Unicode minus held two identities and never
#: merged. A sign is a sign in every typeface, and it is now written one way.
#: The plus-minus sign and the double prime stand for themselves, so neither
#: folds into another character.
_SIGN_FOLD = str.maketrans(
    {
        **{character: "-" for character in HYPHENS},
        "\uff0b": "+",  # FULLWIDTH PLUS SIGN
        "\u2032": "'",  # PRIME
        "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    }
)

#: A hyphen between two alphanumeric characters separates two tokens, as in
#: ``s1-b1``. A hyphen in any other position is a sign that belongs to the
#: token it touches, as in ``dox-``, which is the opposite of ``dox+``. Every
#: character in :data:`HYPHENS` reads the same way, because a name that arrives
#: from a word processor carries the typographic one.
_SEPARATING_HYPHEN = re.compile(
    rf"(?<=[^\W_])[{re.escape(HYPHENS)}](?=[^\W_])"
)


#: Characters a fully canonical name may hold. :func:`is_canonical` reports
#: against this set.
CANONICAL_CHARSET = re.compile(r"[^a-z0-9_]")

#: Characters that normalisation drops. A letter or a digit in any script
#: survives, because it can carry the identity of the sample. A cohort that
#: writes its replicates as ``sample_9α`` and ``sample_9β`` names two samples,
#: and an ASCII-only set deletes both suffixes and merges the pair. The signs
#: in :data:`IDENTITY_SIGNS` and the hyphen survive for the same reason.
NON_IDENTIFIER = re.compile(
    rf"[^\w{re.escape(IDENTITY_SIGNS)}{re.escape(HYPHENS)}]"
)


def prepare(name: str) -> str:
    """Lower-case a name and turn each separating hyphen into the delimiter.

    Every reader of a raw name calls this first, so that the tokens and the
    identity signature always agree on which hyphens separate and which ones
    carry meaning.

    Args:
        name: A raw sample name.

    Returns:
        The name in lower case, with every spelling of a sign folded to one
        character and each separating hyphen replaced by
        :data:`CANONICAL_DELIMITER`.

    Example:
        >>> prepare("S1-B1")
        's1_b1'
        >>> prepare("OVTOKO_DOX-_br1")
        'ovtoko_dox-_br1'
        >>> prepare("CD4\u2212") == prepare("CD4-")
        True
    """
    return _SEPARATING_HYPHEN.sub(
        CANONICAL_DELIMITER, name.lower().translate(_SIGN_FOLD)
    )


@dataclass(frozen=True)
class Abbreviation:
    """One canonical term and the short forms that expand to it.

    Attributes:
        canonical: The expanded term, for example ``"batch"``.
        aliases: Short forms that expand to ``canonical``, for example
            ``("b", "bat")``.
        numbered: True when the alias normally carries a trailing number, as in
            ``b3``. A single-character alias is only recognised with a number,
            because a bare ``b`` token is too ambiguous to expand safely.
    """

    canonical: str
    aliases: tuple[str, ...]
    numbered: bool

    def alias_regex(self, alias: str) -> str:
        """Return the regex that matches one alias as a complete token.

        Args:
            alias: The short form to build a pattern for.

        Returns:
            A regex string intended for :func:`re.fullmatch` against a single
            token.
        """
        escaped = re.escape(alias)
        if not self.numbered:
            return escaped
        if len(alias) == 1:
            return escaped + r"\d+"
        return escaped + r"\d*"

    def describe(self, alias: str) -> str:
        """Return the human-readable label used in the diagnosis output.

        Args:
            alias: The short form that was detected.

        Returns:
            A label such as ``"batch (b<n>)"`` or ``"control (ctrl)"``.
        """
        if self.numbered:
            return f"{self.canonical} ({alias}<n>)"
        return f"{self.canonical} ({alias})"


#: Every abbreviation the tool expands. Order is the order shown to the model.
#:
#: ``t`` is deliberately absent as an alias for treatment. Version 0.1.0 listed
#: it, but ``t1`` reads as a timepoint at least as often as it reads as a
#: treatment. A token left unexpanded is easy to repair later. A token expanded
#: to the wrong term merges two samples that should stay apart, and the row
#: count drops without an error.
ABBREVIATIONS: tuple[Abbreviation, ...] = (
    Abbreviation("sample", ("samp", "s"), True),
    Abbreviation("patient", ("pt", "p"), True),
    Abbreviation("batch", ("bat", "b"), True),
    Abbreviation("replicate", ("rep", "r"), True),
    Abbreviation("timepoint", ("tp",), True),
    Abbreviation("control", ("ctrl", "ctl"), False),
    Abbreviation("treatment", ("trt",), False),
    Abbreviation("wildtype", ("wt",), False),
    Abbreviation("knockout", ("ko",), False),
)


#: Every alias as a compiled pattern, built one time at import, in the order of
#: :data:`ABBREVIATIONS`. :func:`samplify.matching._expand_token` runs for every
#: token of every name of every comparison. Building the pattern string there
#: called :func:`re.escape` 20 million times on one real study, which was 18 of
#: the 50 seconds that the proposal took.
COMPILED_ALIASES: tuple[tuple[re.Pattern[str], "Abbreviation", str], ...] = tuple(
    (re.compile(abbreviation.alias_regex(alias)), abbreviation, alias)
    for abbreviation in ABBREVIATIONS
    for alias in abbreviation.aliases
)


def split_tokens(name: str) -> list[str]:
    """Split a sample name into lower-case tokens on any delimiter.

    Args:
        name: A raw sample name.

    Returns:
        The tokens of the name, lower-cased, with empty tokens removed.
    """
    return [t for t in re.split(DELIMITER_PATTERN, prepare(name)) if t]


def detect_abbreviations(names: list[str]) -> list[str]:
    """Report which abbreviations appear across a list of names.

    Args:
        names: Raw sample names.

    Returns:
        One label per distinct abbreviation found, in the order of
        :data:`ABBREVIATIONS`. The labels come from
        :meth:`Abbreviation.describe`.
    """
    found: list[str] = []
    seen: set[str] = set()
    tokens = {token for name in names for token in split_tokens(name)}

    for pattern, abbreviation, alias in COMPILED_ALIASES:
        if any(pattern.fullmatch(token) for token in tokens):
            label = abbreviation.describe(alias)
            if label not in seen:
                found.append(label)
                seen.add(label)
    return found


def prompt_rules() -> str:
    """Render the normalisation rules as the text block sent to the model.

    Returns:
        A markdown list of rules, generated from :data:`ABBREVIATIONS` so that
        the prompt and the diagnosis can never disagree.
    """
    expansions = ", ".join(
        f"{'/'.join(a.aliases)} -> {a.canonical}" for a in ABBREVIATIONS
    )
    return "\n".join(
        [
            f"- Use the underscore ({CANONICAL_DELIMITER}) as the only delimiter",
            f"- Expand these abbreviations: {expansions}",
            "- Remove zero-padding: sample01 -> sample1, batch002 -> batch2",
            "- Lower-case everything",
            "- Drop any character that is not a letter, a digit, an underscore"
            f" or one of these signs: {IDENTITY_SIGNS} and the hyphen",
            "- Keep a sign such as + or - where it stands. CD4+ and CD4- are two"
            " different populations, and DOX+ and DOX- are two different arms.",
            "- Keep the component order consistent across all names",
            "- Leave a token unchanged when you cannot tell what it abbreviates."
            " An unexpanded token is safer than a wrong expansion, because a"
            " wrong expansion silently merges two different samples.",
        ]
    )


def is_canonical(name: str) -> bool:
    """Report whether a name already satisfies the character-level rules.

    This checks the delimiter, the case and the character set. It does not
    check that abbreviations are expanded, because that needs the context of
    the other names.

    Args:
        name: The name to check.

    Returns:
        True when the name holds a character and every character is a
        lower-case letter, a digit or an underscore.
    """
    # An empty name is not canonical. The search finds nothing in an empty
    # string, so the answer was True, and a caller that asked "may this name
    # pass" was told yes about a name that identifies nothing.
    if not name.strip("_") or not name.strip():
        return False
    return not CANONICAL_CHARSET.search(name)
