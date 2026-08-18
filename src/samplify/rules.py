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

#: Characters treated as delimiters when a name is split into tokens.
DELIMITER_PATTERN = r"[_\-.\s]"

#: Characters allowed in a canonical name. Anything else is dropped.
CANONICAL_CHARSET = re.compile(r"[^a-z0-9_]")


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


def split_tokens(name: str) -> list[str]:
    """Split a sample name into lower-case tokens on any delimiter.

    Args:
        name: A raw sample name.

    Returns:
        The tokens of the name, lower-cased, with empty tokens removed.
    """
    return [t for t in re.split(DELIMITER_PATTERN, name.lower()) if t]


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

    for abbrev in ABBREVIATIONS:
        for alias in abbrev.aliases:
            pattern = abbrev.alias_regex(alias)
            if any(re.fullmatch(pattern, token) for token in tokens):
                label = abbrev.describe(alias)
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
            "- Drop any character that is not a letter, a digit or an underscore",
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
        True when the name contains only lower-case letters, digits and
        underscores.
    """
    return not CANONICAL_CHARSET.search(name)
