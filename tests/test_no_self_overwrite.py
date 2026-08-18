"""No command writes an output over a file it reads.

Three reviews found one instance of this each, in `apply`, in `propose` and
then in `apply` again for its second input. Each fix guarded one more path, so
this file drives every command with every output aimed at every file that
command reads. A new output option has to be added here, or the guard is
missing and this test says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samplify import cli
from samplify import mapping as mapping_module
from samplify.csv_processor import propose_csv


@pytest.fixture()
def workspace(tmp_path):
    """A CSV, a mapping file written from it, and a figure path."""
    data = tmp_path / "data.csv"
    data.write_text("sample_id\nS1_B1\ns1-b1\nP3_B2\np3-b2\n")

    mapping = tmp_path / "mapping.json"
    result = propose_csv(data, "sample_id", method="damerau")
    result.accept_all()
    mapping_module.write(result, mapping)

    return {"root": tmp_path, "data": data, "mapping": mapping}


#: One row per command: the arguments, the files it reads, and each option that
#: names a file it writes.
COMMANDS = [
    (
        "propose",
        lambda w: ["propose", str(w["data"]), "-c", "sample_id", "-M", "damerau", "--yes"],
        ["data"],
        ["--output", "--plot"],
    ),
    (
        "apply",
        lambda w: ["apply", str(w["mapping"])],
        ["data", "mapping"],
        ["--output", "--json-log", "--csv-log"],
    ),
    (
        "plot",
        lambda w: ["plot", str(w["mapping"])],
        ["mapping"],
        ["--output"],
    ),
]


@pytest.mark.parametrize("command,argv,reads,writes", COMMANDS,
                         ids=[row[0] for row in COMMANDS])
def test_no_command_writes_over_a_file_it_reads(workspace, capsys, command, argv,
                                                reads, writes):
    for option in writes:
        for name in reads:
            target: Path = workspace[name]
            before = target.read_bytes()

            arguments = argv(workspace) + [option, str(target)]
            # propose needs an --output even when the option under test is --plot.
            if command == "propose" and option == "--plot":
                arguments += ["--output", str(workspace["root"] / "other.json")]

            code = cli.main(arguments)
            printed = " ".join(capsys.readouterr().out.split())

            assert code == 1, f"{command} {option} -> {name} was accepted"
            assert "no output over" in printed, printed
            assert target.read_bytes() == before, f"{command} {option} changed {name}"


@pytest.mark.parametrize("link", ["hard", "symbolic"])
def test_an_alias_of_the_input_is_the_input(workspace, capsys, link):
    """A second name for one file still reaches the same bytes.

    `Path.resolve` follows a symbolic link and knows nothing of a hard link, so
    comparing the resolved names let a hard-link alias of the input through and
    the input was overwritten.
    """
    data: Path = workspace["data"]
    alias = workspace["root"] / f"alias_{link}.csv"
    if link == "hard":
        alias.hardlink_to(data)
    else:
        alias.symlink_to(data)

    before = data.read_bytes()
    code = cli.main(["apply", str(workspace["mapping"]), "--output", str(alias)])

    assert code == 1
    assert "no output over" in " ".join(capsys.readouterr().out.split())
    assert data.read_bytes() == before


def test_the_ordinary_paths_still_write(workspace):
    """The guard refuses nothing that points somewhere else."""
    root = workspace["root"]
    assert cli.main([
        "apply", str(workspace["mapping"]),
        "--output", str(root / "clean.csv"),
        "--csv-log", str(root / "changes.csv"),
        "--json-log", str(root / "changes.json"),
    ]) == 0
    for name in ("clean.csv", "changes.csv", "changes.json"):
        assert (root / name).exists(), name
