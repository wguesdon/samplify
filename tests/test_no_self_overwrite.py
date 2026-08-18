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


@pytest.mark.parametrize(
    "alias",
    ["the same path", "a dot segment", "a parent segment", "a doubled separator"],
)
def test_every_spelling_of_one_path_is_the_same_file(workspace, alias):
    """A path has many spellings, and each one reaches the same bytes."""
    from samplify.csv_processor import is_the_same_file

    root: Path = workspace["root"]
    data: Path = workspace["data"]
    (root / "sub").mkdir(exist_ok=True)

    candidates = {
        "the same path": data,
        "a dot segment": root / "." / data.name,
        "a parent segment": root / "sub" / ".." / data.name,
        "a doubled separator": Path(f"{root}//{data.name}"),
    }
    assert is_the_same_file(candidates[alias], data)


def test_a_different_file_is_not_the_same_file(workspace):
    from samplify.csv_processor import is_the_same_file

    assert not is_the_same_file(workspace["root"] / "other.csv", workspace["data"])
    assert not is_the_same_file(workspace["mapping"], workspace["data"])


def test_a_directory_alias_of_the_input_is_the_input(tmp_path, capsys):
    """The alias can be the parent rather than the file."""
    from samplify.csv_processor import propose_csv

    real = tmp_path / "real"
    real.mkdir()
    data = real / "data.csv"
    data.write_text("sample_id\nS1_B1\ns1-b1\n")

    mapping = real / "mapping.json"
    result = propose_csv(data, "sample_id", method="damerau")
    result.accept_all()
    mapping_module.write(result, mapping)

    linked = tmp_path / "linked"
    linked.symlink_to(real)

    before = data.read_bytes()
    code = cli.main(["apply", str(mapping), "--output", str(linked / "data.csv")])

    assert code == 1
    assert "no output over" in " ".join(capsys.readouterr().out.split())
    assert data.read_bytes() == before


def test_every_call_that_writes_a_file_has_a_guarded_destination():
    """An inventory, so that a new write cannot be added without one.

    Six calls in the package write a file. Each destination is either checked
    against every input of its command, or it is the mapping file that `review`
    was given, which is what that command exists to change.
    """
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / "src" / "samplify"
    found = []
    for module in sorted(source.glob("*.py")):
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in ("to_csv", "savefig", "replace") or (
                name == "open" and len(node.args) > 1
            ):
                found.append(f"{module.name}:{name}")

    assert sorted(found) == sorted([
        "csv_processor.py:to_csv",   # the output CSV
        "csv_processor.py:to_csv",   # the change log
        "csv_processor.py:open",     # the JSON log
        "mapping.py:open",           # the mapping file, through a temporary one
        "mapping.py:replace",        # the same, put in place
        "plots.py:savefig",          # the figure
    ]), found
