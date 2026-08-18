"""The mapping file: the artifact a person reviews and ``apply`` consumes.

The file is organised around groups, not around single names, because the
question a person answers is "are these three spellings one sample?". A group
holds the members, the proposed canonical name and the decision.

``apply`` reads this file and never calls a model, so the same mapping file and
the same input give the same output on any machine and on any day.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Bumped when the on-disk shape changes in a way an older reader cannot handle.
SCHEMA_VERSION = 1

STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_EDITED = "edited"

#: Every status a group may carry.
STATUSES = (STATUS_PROPOSED, STATUS_ACCEPTED, STATUS_REJECTED, STATUS_EDITED)

#: Statuses that mean the group's members take the canonical name.
APPLIED_STATUSES = (STATUS_ACCEPTED, STATUS_EDITED)


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Group:
    """One candidate sample, with every spelling of it that was found.

    Attributes:
        id: A stable number used to refer to the group in the review step.
        members: The raw names that the tool believes are one sample.
        proposed: The canonical name the tool suggests.
        final: The canonical name after review. Equal to ``proposed`` until a
            person edits it.
        status: One of :data:`STATUSES`.
        occurrences: How many rows carry each member name.
        method: The backend that formed this group.
        min_similarity: The lowest pairwise similarity inside the group, or
            None for a group of one and for a group the model formed.
    """

    id: int
    members: list[str]
    proposed: str
    final: str
    status: str = STATUS_PROPOSED
    occurrences: dict[str, int] = field(default_factory=dict)
    method: str = "rules"
    min_similarity: float | None = None

    @property
    def is_merge(self) -> bool:
        """True when the group joins more than one spelling into one sample."""
        return len(self.members) > 1

    @property
    def is_rename(self) -> bool:
        """True when one name changes but nothing merges."""
        return len(self.members) == 1 and self.members[0] != self.proposed

    @property
    def is_noop(self) -> bool:
        """True when the group changes nothing."""
        return len(self.members) == 1 and self.members[0] == self.proposed

    @property
    def rows(self) -> int:
        """The number of data rows this group covers."""
        return sum(self.occurrences.get(m, 0) for m in self.members)

    def validate(self) -> None:
        """Check every field that decides a name, or raise.

        Reading a mapping file runs the same checks through
        :meth:`from_dict`, and a caller that builds a Group in Python reaches
        none of them. Both paths call this one method, so the two cannot drift
        apart. A string is the shape that matters most here: it is iterable, so
        ``members="AB"`` reads as the two samples ``A`` and ``B`` everywhere
        that a list is expected.

        Raises:
            ValueError: If any field cannot decide a name.
        """
        if not isinstance(self.members, list):
            raise ValueError(
                f"Group {self.id} has members of type "
                f"{type(self.members).__name__}. It must be a list of names."
            )
        if not self.members:
            raise ValueError(f"Group {self.id} has no members.")
        for member in self.members:
            if not isinstance(member, str) or not member.strip():
                raise ValueError(
                    f"Group {self.id} has the member {member!r}. A member "
                    f"must be a string that holds a character."
                )
        # A repeated member misleads the person who is deciding. `rows` sums
        # the occurrences once for each entry, so it doubles, and `is_merge`
        # reads two entries as two names, so a group holding one name asks for
        # a decision that has nothing in it.
        repeated = sorted({m for m in self.members if self.members.count(m) > 1})
        if repeated:
            raise ValueError(
                f"Group {self.id} lists {repeated[0]!r} more than once. Every "
                f"member appears one time."
            )
        if self.status not in STATUSES:
            raise ValueError(
                f"Group {self.id} has status {self.status!r}, which is not one "
                f"of {STATUSES}."
            )
        for label, value in (("proposed", self.proposed), ("final", self.final)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Group {self.id} has {label} {value!r}. A canonical name "
                    f"must be a string that holds a character."
                )

    def resolved(self) -> dict[str, str]:
        """Return the name each member takes once the decision is applied.

        Returns:
            A dictionary from member name to final name. A rejected group
            leaves every member unchanged.

        Raises:
            ValueError: If the group is still awaiting a decision, or if any
                field of it cannot decide a name.
        """
        # This is the one place where a decision becomes a new name.
        self.validate()
        if self.status == STATUS_PROPOSED:
            raise ValueError(f"Group {self.id} is still proposed and has no decision.")
        if self.status == STATUS_REJECTED:
            return {member: member for member in self.members}
        return {member: self.final for member in self.members}

    def to_dict(self) -> dict[str, Any]:
        """Serialise the group to plain JSON types."""
        return {
            "id": self.id,
            "members": list(self.members),
            "proposed": self.proposed,
            "final": self.final,
            "status": self.status,
            "occurrences": dict(self.occurrences),
            "method": self.method,
            "min_similarity": self.min_similarity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Group:
        """Build a group from its serialised form.

        Args:
            data: One entry of the ``groups`` list.

        Returns:
            The group.

        Raises:
            ValueError: If a required key is missing or a value is not valid.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"A group is an object. This one is a {type(data).__name__}."
            )
        for key in ("id", "members", "proposed", "final", "status"):
            if key not in data:
                raise ValueError(f"Group is missing the required key {key!r}.")
        # int(None) raises a TypeError, and this class documents ValueError.
        # A bool is refused first, because bool is a subclass of int in Python
        # and int(True) is 1, so a group with the id true became group 1.
        if isinstance(data["id"], bool) or data["id"] is None:
            raise ValueError(
                f"A group has the id {data['id']!r}. An id must be a number."
            )
        try:
            identifier = int(data["id"])
        except (TypeError, ValueError):
            raise ValueError(
                f"A group has the id {data['id']!r}. An id must be a number."
            ) from None

        group = cls(
            id=identifier,
            members=data["members"] if isinstance(data["members"], list)
            else data["members"],
            proposed=data["proposed"],
            final=data["final"],
            status=data["status"],
            occurrences=dict(data.get("occurrences", {})),
            method=str(data.get("method", "rules")),
            min_similarity=data.get("min_similarity"),
        )
        # One method holds every check, so the file reader and a caller that
        # builds a Group in Python can never disagree about what is valid.
        group.validate()
        group.members = list(group.members)
        return group


@dataclass
class MappingFile:
    """The whole reviewed artifact.

    Attributes:
        groups: Every candidate sample.
        method: The backend used to build the file.
        input_file: The CSV the names came from, as an absolute path.
        column: The column the names came from.
        model: The model string, when a model was called.
        provider: The service that answered, when a model was called. It is
            ``"openrouter"`` or ``"ollama"``.
        base_url: The server the names were sent to, when a model was called.
            ``OLLAMA_HOST`` can point ollama at another machine, and a person
            reading this file has to be able to see that the names left this
            one.
        reviewed: True only when a person made the decisions.
        reviewed_at: When the review finished.
        created: When the file was written.
        diagnosis: The heuristic findings from the propose step.
        near_misses: Pairs that read alike but carry different numbers. These
            are never merged. They are reported so a person can check them.
        canonical_pattern: The model's description of the format it inferred.
    """

    groups: list[Group]
    method: str = "rules"
    input_file: str | None = None
    column: str | None = None
    model: str | None = None
    provider: str | None = None
    base_url: str | None = None
    reviewed: bool = False
    reviewed_at: str | None = None
    created: str = field(default_factory=_now)
    diagnosis: dict[str, Any] = field(default_factory=dict)
    near_misses: list[list[str]] = field(default_factory=list)
    canonical_pattern: str = ""
    schema_version: int = SCHEMA_VERSION

    # ── Queries ────────────────────────────────────────────────────────────

    def pending(self) -> list[Group]:
        """Return the groups that still await a decision."""
        return [g for g in self.groups if g.status == STATUS_PROPOSED]

    def merges(self) -> list[Group]:
        """Return the groups that join more than one spelling."""
        return [g for g in self.groups if g.is_merge]

    def renames(self) -> list[Group]:
        """Return the groups that change one name without merging."""
        return [g for g in self.groups if g.is_rename]

    def final_mapping(self) -> dict[str, str]:
        """Return the name every original takes once the decisions are applied.

        Returns:
            A dictionary from every original name to its final name.

        Raises:
            ValueError: If any group is still awaiting a decision.
        """
        still_open = self.pending()
        if still_open:
            ids = ", ".join(str(g.id) for g in still_open[:5])
            more = "" if len(still_open) <= 5 else f" and {len(still_open) - 5} more"
            raise ValueError(
                f"{len(still_open)} group(s) are still proposed: {ids}{more}. "
                f"Run 'samplify review' first, or rerun propose with --yes."
            )

        # Reading a mapping file refuses a name that two groups claim, and a
        # caller that builds a MappingFile in Python does not go through that
        # check. `dict.update` would let the last group win, so one group would
        # decide the name of a sample and the other would be ignored in silence.
        result: dict[str, str] = {}
        owner: dict[str, int] = {}
        for group in self.groups:
            for member, final in group.resolved().items():
                if member in owner:
                    raise ValueError(
                        f"Name {member!r} appears in group {owner[member]} and "
                        f"in group {group.id}. Every name belongs to one group."
                    )
                owner[member] = group.id
                result[member] = final
        return result

    def collisions(self) -> dict[str, list[int]]:
        """Find canonical names that more than one group produces.

        A merge inside one group is the purpose of the tool. Two separate
        groups landing on one canonical name is not, and it silently joins two
        samples that the tool itself considered distinct.

        A rejected group counts through its original names. Rejection keeps
        every member as it was written, so those names stay in the output
        namespace. A second group renamed onto one of them merges two samples
        exactly as two equal canonical names do.

        Returns:
            A dictionary from the shared name to the group ids that produce it.
            Empty when there is no collision.
        """
        by_name: dict[str, list[int]] = {}
        for group in self.groups:
            if group.status == STATUS_REJECTED:
                for member in group.members:
                    by_name.setdefault(member, []).append(group.id)
            else:
                by_name.setdefault(group.final, []).append(group.id)
        return {name: ids for name, ids in sorted(by_name.items()) if len(ids) > 1}

    def summary(self) -> dict[str, int]:
        """Count the groups by kind, for the console and the log."""
        return {
            "groups": len(self.groups),
            "merges": len(self.merges()),
            "renames": len(self.renames()),
            "unchanged": len([g for g in self.groups if g.is_noop]),
            "pending": len(self.pending()),
            "rejected": len([g for g in self.groups if g.status == STATUS_REJECTED]),
            "near_misses": len(self.near_misses),
        }

    def accept_all(self) -> None:
        """Accept every pending group without a person present.

        ``reviewed`` stays False, so the file records that no person checked
        the decisions.
        """
        for group in self.pending():
            group.status = STATUS_ACCEPTED
            group.final = group.proposed

    # ── Serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise the mapping file to plain JSON types."""
        return {
            "schema_version": self.schema_version,
            "created": self.created,
            "input_file": self.input_file,
            "column": self.column,
            "method": self.method,
            "model": self.model,
            "provider": self.provider,
            "base_url": self.base_url,
            "canonical_pattern": self.canonical_pattern,
            "reviewed": self.reviewed,
            "reviewed_at": self.reviewed_at,
            "diagnosis": self.diagnosis,
            "near_misses": [list(pair) for pair in self.near_misses],
            "summary": self.summary(),
            "groups": [g.to_dict() for g in self.groups],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingFile:
        """Build a mapping file from its serialised form.

        Args:
            data: The parsed JSON document.

        Returns:
            The mapping file.

        Raises:
            ValueError: If the schema version is unsupported, a required key is
                missing, or a name appears in more than one group.
        """
        # json.load returns whatever the file holds, and a list has no .get.
        if not isinstance(data, dict):
            raise ValueError(
                f"A mapping file holds an object. This one holds a "
                f"{type(data).__name__}."
            )

        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"Mapping file schema version {version!r} is not supported. "
                f"This build of samplify reads version {SCHEMA_VERSION}."
            )
        if "groups" not in data:
            raise ValueError("Mapping file has no 'groups' key.")
        if not isinstance(data["groups"], list):
            raise ValueError(
                f"The 'groups' key holds a {type(data['groups']).__name__}. "
                f"It must be a list."
            )

        # The reviewed field decides whether the collision guard runs, so it is
        # checked and not coerced. bool("false") is True, and a file holding
        # the string would switch the guard off.
        reviewed = data.get("reviewed", False)
        if not isinstance(reviewed, bool):
            raise ValueError(
                f"The 'reviewed' field is {reviewed!r}. It must be true or "
                f"false, because it decides whether apply refuses a mapping "
                f"in which two groups produce one name."
            )

        groups = [Group.from_dict(g) for g in data["groups"]]

        seen: dict[str, int] = {}
        for group in groups:
            for member in group.members:
                if member in seen:
                    raise ValueError(
                        f"Name {member!r} appears in group {seen[member]} "
                        f"and in group {group.id}. Every name belongs to one group."
                    )
                seen[member] = group.id

        return cls(
            groups=groups,
            method=str(data.get("method", "rules")),
            input_file=data.get("input_file"),
            column=data.get("column"),
            model=data.get("model"),
            provider=data.get("provider"),
            base_url=data.get("base_url"),
            reviewed=reviewed,
            reviewed_at=data.get("reviewed_at"),
            created=str(data.get("created", _now())),
            diagnosis=dict(data.get("diagnosis", {})),
            near_misses=[list(p) for p in data.get("near_misses", [])],
            canonical_pattern=str(data.get("canonical_pattern", "")),
            schema_version=int(version),
        )

    def mark_reviewed(self) -> None:
        """Record that a person made the decisions in this file."""
        self.reviewed = True
        self.reviewed_at = _now()


def write(mapping: MappingFile, path: str | Path) -> Path:
    """Write a mapping file to disk as indented JSON.

    The write goes to a temporary file in the same directory and then replaces
    the target in one operation. This file holds the decisions a person made,
    and a crash during a plain write leaves a truncated document and loses that
    work.

    Args:
        mapping: The mapping file to write.
        path: Where to write it.

    Returns:
        The path written.
    """
    path = Path(path)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with open(temporary, "w") as fh:
            json.dump(mapping.to_dict(), fh, indent=2)
            fh.write("\n")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def read(path: str | Path) -> MappingFile:
    """Read a mapping file from disk and validate it.

    Args:
        path: The file to read.

    Returns:
        The mapping file.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the document is not valid JSON or fails validation.
    """
    path = Path(path)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    return MappingFile.from_dict(data)
