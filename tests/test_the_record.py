"""The changelog and the version must agree.

Two edit scripts once replaced a heading that did not exist and carried no
check, so they silently wrote nothing and three entries were lost while the
version kept moving. The record of what changed is the thing a person reads to
decide whether to upgrade, so it is checked here like any other output.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = (ROOT / "CHANGELOG.md").read_text()
VERSIONS = re.findall(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", CHANGELOG, re.M)


def _declared_version() -> str:
    """Read the version from pyproject.toml.

    A regex rather than tomllib, because tomllib arrived in Python 3.11 and
    this package supports 3.10.
    """
    text = (ROOT / "pyproject.toml").read_text()
    found = re.search(r'^version = "([^"]+)"', text, re.M)
    assert found, "pyproject.toml holds no version"
    return found.group(1)


def test_the_newest_entry_is_the_version_that_ships():
    assert VERSIONS, "the changelog holds no version heading"
    assert VERSIONS[0] == _declared_version()


def test_no_version_is_written_twice():
    assert len(VERSIONS) == len(set(VERSIONS)), "a version appears more than once"


def test_the_versions_run_downwards():
    """Newest first, so a reader finds the latest change at the top."""
    numbers = [tuple(int(part) for part in version.split(".")) for version in VERSIONS]
    assert numbers == sorted(numbers, reverse=True)


def test_every_entry_says_something():
    """A heading with nothing under it records nothing."""
    sections = re.split(r"^## \[[0-9]+\.[0-9]+\.[0-9]+\][^\n]*\n", CHANGELOG, flags=re.M)
    for version, body in zip(VERSIONS, sections[1:]):
        assert body.strip(), version


def test_every_signature_the_document_shows_is_the_one_the_code_gives():
    """A document that shows an output is showing a promise.

    The sign gained a position marker and the document kept the old example, so
    a reader would have been told `("1", "+")` where the code gives
    `("1", "0+")`.
    """
    from samplify import matching

    document = (ROOT / "docs" / "how_it_works.md").read_text()
    shown = re.findall(
        r"signature of `([^`]+)` is `\(([^)]*)\)`", document
    )
    assert shown, "the document shows no signature"

    for name, written in shown:
        expected = str(matching.digit_signature(name)).strip("()")
        assert written.replace('"', "'").rstrip(",").strip() == (
            expected.replace('"', "'").rstrip(",").strip()
        ), name
