"""The changelog and the version must agree.

Two edit scripts once replaced a heading that did not exist and carried no
check, so they silently wrote nothing and three entries were lost while the
version kept moving. The record of what changed is the thing a person reads to
decide whether to upgrade, so it is checked here like any other output.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = (ROOT / "CHANGELOG.md").read_text()
VERSIONS = re.findall(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", CHANGELOG, re.M)


def _declared_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


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
