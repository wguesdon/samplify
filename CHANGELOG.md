# Changelog

All notable changes to samplify are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because a wrong merge loses data, "breaking" here means either a change to the
command surface or a change that alters which names group together. Those bump
the major version. A new backend or a new command bumps the minor version. A fix
that leaves the grouping unchanged bumps the patch version.

## [0.2.0] - 2026-08-16

The tool now finds the sample names that are one sample spelled several ways,
and a person confirms each group before anything is renamed. Version 0.1.0
proposed a mapping and applied it in the same command, with no way to check it
and no way to repeat it.

### Added

- Three commands in place of one. `samplify propose` writes a mapping file,
  `samplify review` asks a person to decide each group, and `samplify apply`
  applies the decisions. `apply` never calls a model, so the same mapping file
  and the same input give the same output on any machine and on any day.
- The mapping file, in `samplify/mapping.py`. It holds one group per candidate
  sample, each with its members, its proposed canonical name, its decision and
  its row counts. It is JSON, so git stores it and a diff shows the cleanup.
- Three offline backends in `samplify/matching.py` that need no API key.
  `rules` applies the character-level rules. `hamming` and `levenshtein` add
  typo tolerance. `damerau` adds the swap of two adjacent characters and is the
  default, because a swap is one keystroke and plain Levenshtein charges two
  edits for it.
- The `auto` backend. It clusters offline first and then sends one name per
  cluster to the model, which makes the request much smaller. It skips the model
  entirely when the heuristics find nothing and no cluster forms.
- The identity rule. Two names are compared only when their numbers match
  exactly, and a letter attached to a number counts as part of the number. This
  keeps `p111` apart from `p112` at any threshold, and `sample_9a` apart from
  `sample_9b`.
- Near-miss reporting. A pair whose letters agree and whose number gained or
  lost a digit is reported and never merged. A pair inside the numbering series
  the dataset already uses is not reported, so a cohort numbered 1 to 12 does
  not flag `sample_1` against `sample_10`.
- `samplify plot` and the `--plot` option on `propose`. They draw a four-panel
  quality control figure: the similarity matrix ordered by group, the spellings
  per sample, the counts before and after, and the list of names that need a
  person. matplotlib is an optional dependency, installed with the `plot` extra.
- `example/` with five datasets and a README that gives the command for each.
  `mislabel_catalogue.csv` carries its own answer in a `true_sample` column and
  covers ten naming faults and three pairs that must not merge.
- `tests/smoke_test.sh`, which runs the command line end to end with no API key,
  and 131 unit tests.
- `LICENSE`, `CHANGELOG.md` and `docs/how_it_works.md`.

### Changed

- The abbreviation table is defined once, in the new `samplify/rules.py`, and it
  is read by the model prompt, by the CSV diagnosis and by the offline backends.
  Version 0.1.0 held the table twice and the two copies had already drifted, so
  the diagnosis could report an abbreviation that the prompt never expanded.
- `p` and `pt` now expand to patient, which a clinical cohort needs.
- `t` no longer expands to treatment. A token such as `t1` reads as a timepoint
  at least as often as a treatment, and a wrong expansion merges two samples
  while an unexpanded token stays easy to repair.
- A number now attaches to the word in front of it, so `sample_1` and `sample1`
  normalise to the same string.
- The canonical name of a group is the frequency-weighted medoid, and the
  letter skeletons of the whole dataset break a tie. A group of two spellings
  gives the medoid nothing to work with, and version 0.1.0 would have picked the
  alphabetically first, which is the typo about half the time.
- The library no longer prints. `samplify/csv_processor.py` returns data and the
  CLI renders it, so the same calls work inside a script.
- `harmonize` raises a clear error when the model returns something that is not
  the requested JSON document. Version 0.1.0 raised `JSONDecodeError` from
  inside the parser.
- The README no longer shows `samplify "name" "name"`, which never worked. The
  CLI has always needed a subcommand.
- The version lives in `pyproject.toml` alone and `__init__.py` reads it with
  `importlib.metadata`. A `build-system` section was added, without which the
  package did not install and the metadata was not readable.

### Fixed

- The install instruction. The package is not on PyPI, so the README gives the
  git install.

## [0.1.0] - 2026-08-08

### Added

- `harmonize`, which sends a list of sample names to a model through OpenRouter
  and returns a canonical name for each.
- `harmonize_csv`, which adds a canonical column to a CSV and writes a JSON and
  a CSV log.
- A heuristic diagnosis that skips the model call when the names look
  consistent.
- The `samplify` command line and the unit tests.
