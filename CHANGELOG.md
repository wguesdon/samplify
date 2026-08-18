# Changelog

All notable changes to samplify are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because a wrong merge loses data, "breaking" here means either a change to the
command surface or a change that alters which names group together. Those bump
the major version. A new backend or a new command bumps the minor version. A fix
that leaves the grouping unchanged bumps the patch version.

The version is below 1.0.0, and samplify is not ready for a release. Semantic
Versioning gives the minor version the role of the major version below 1.0.0, so
a change that alters the grouping bumps the minor version until 1.0.0.

## [0.4.0] - 2026-08-18

A code review found 18 defects, and this version repairs all of them. Seven of
them merged two different samples or altered the input, and none of them
reported anything. Read the grouping changes below before you reuse a mapping
file from an earlier version, because four of them alter which names group
together.

### Fixed, a wrong merge or a change to the input

- The `llm` backend now applies the identity rule to the answer of the model.
  The `auto` backend already did. A model that gave one canonical name to
  `p111` and to `p112` merged two patients, and the guard that refuses that
  merge existed in one of the two model paths only.
- Every CSV is read as text. pandas inferred a type for each column, so it read
  `007` as the number 7 and wrote `7` back into the source column, and it read
  a sample named `NA` as a missing value and deleted the row from the mapping.
  The claim that samplify never changes the original column was not true for
  either input.
- A letter run with a digit behind it is no longer part of the digit signature.
  The `b` of `p1b1` introduces the next number of the name. Reading it as a
  replicate letter gave `p1b1` the signature `("1b", "1")` and `p1_b1` the
  signature `("1", "1")`, so the compact form of a name never merged with the
  delimited form.
- A letter in any script now counts in the digit signature and survives
  normalisation. The character set was ASCII only, so `sample_9α` and
  `sample_9β` both lost their suffix and merged, while `sample_9a` and
  `sample_9b` correctly stayed apart.
- One inserted or deleted letter matches on its own only when both letter
  skeletons hold at least five letters. Below that length the same edit
  separates two real terms, and `wt` merged with `wnt`, `t` with `tp` and `k`
  with `ko`.
- Two names with no letter no longer match. The ratio compared two empty
  strings and scored 1.0, so every name built from characters that the rules
  drop merged into one sample.
- `collisions()` counts the original names of a rejected group. Rejection keeps
  every member as it was written, and a second group renamed onto one of those
  names merged two samples with no refusal from `apply`.
- `apply` refuses the source column as the canonical column, and it refuses to
  write over any column that the input already holds.

### Fixed, a guard that read a bad value as permission

- The `reviewed` field must be a boolean. `bool("false")` is True, so a file
  holding the string switched off the guard that refuses a collision.
- A canonical name and a member name must be a string that holds a character.
  `str(None)` gives the string `None`, and a group carrying it renamed every
  member of a sample to those four characters.
- `apply` refuses a CSV that shares no name with the mapping. Applying a
  mapping to another file changed no row, and the log still reported every name
  of the mapping as changed.
- The review step asks again when the typed canonical name holds no character.
- `--threshold` refuses a value outside 0.0 to 1.0.
- A duplicate column name is refused. pandas renames the second column, so half
  the names were invisible and no message said so.
- An empty cell forms no group.

### Fixed, the record and the figure

- The mapping file is written to a temporary file and then replaces the target
  in one operation. A crash during a plain write truncated the file and lost
  the decisions a person had made.
- The log records `rows_changed` next to `names_changed`. The first counts the
  rows of the CSV, and the second counts the entries of the mapping.
- The similarity panel of the figure holds the value that decided each group.
  A pair whose digit signatures differ scores 0.0, because samplify never
  compared it, and a pair inside one signature scores the similarity of the two
  letter skeletons. The panel scored the whole raw name, which took no part in
  the decision and painted a refused pair in the colour of a merged one.
- The figure keeps a small group that fits behind a large one. A `break` in the
  ordering dropped every group behind the first one that was too large.
- The collision warning of the review step names the groups, and it prints
  last. `apply` does not refuse a reviewed mapping, so a person has to read it.

### Changed

- The package moved to a `src` layout. The flat layout put the repository root
  on `sys.path`, so every test imported the working copy and never the
  installed package, and no test could see a packaging fault.
- `_cluster_by_canonical` returns the clusters and the canonical name of each,
  in the same shape as `_merge_clusters_by_model`.
- 36 tests were added, one for each defect above. The suite holds 196 offline
  tests.

## [0.3.0] - 2026-08-16

### Added

- A local model, through [ollama](https://ollama.com). The option
  `--provider ollama` on `samplify propose` and on `samplify names` sends the
  request to a model on the machine. It needs no API key, and the sample names
  never leave the machine. `--base-url` and `OLLAMA_HOST` point at another
  machine. `--model` and `OLLAMA_MODEL` choose the model, and the default is
  `qwen3.5:9b`.
- The option `--timeout` on the same two commands. A local model on a CPU is
  slower than a hosted one, and the default for ollama is 300 seconds.
- The field `provider` in the mapping file, next to `model`. A file written by
  an offline backend records `null` for both fields.
- Tests for the local path. The offline tests replace the server and check the
  request, and `uv run pytest -m local` runs the whole workflow against a real
  ollama server.

### Changed

- samplify calls the native ollama endpoint and not the OpenAI-compatible one,
  because only the native endpoint takes `format` and `think`. A thinking model
  answered the same request in 9 seconds with the block turned off. With the
  block on it did not answer in 280 seconds.
- The default `uv run pytest` now runs the offline suite alone. The hosted model
  needs `-m live` and the local model needs `-m local`.

## [0.2.1] - 2026-08-16

### Fixed

- The `auto` backend now keeps the original name on each group that the identity
  rule splits off. The model gave one canonical name to two representatives with
  different numbers. The split kept the two groups apart, but both groups kept
  the name of the model. A person who accepted both groups renamed
  `patient112_batch1` to `patient111_batch1` at the apply step.
- `samplify plot` and `samplify propose --plot` now print the install command
  when matplotlib is absent. The call to `qc_figure` sat outside the `try` block
  in `samplify/cli.py`. `plots.py` imports matplotlib inside `qc_figure`, so the
  missing dependency reached the user as a traceback.
- An error message now keeps the square brackets of its text. rich read the
  `[plot]` of `uv add "samplify[plot]"` as a style tag and dropped it, so the
  install command that the user read was wrong.

### Added

- Offline tests for the model-backed path, in `tests/test_harmonizer.py` and in
  `tests/test_csv_processor.py`. They cover the request that goes to OpenRouter,
  the answers that must raise an error and the model choice. They also cover the
  `llm` backend and the identity rule when the model proposes to join two
  numbers.

### Changed

- The README holds what samplify does, the install, one example and the quality
  control figure. The backend list, the mapping file and the design rules are in
  `docs/how_it_works.md`. The three documents follow ASD-STE100 Simplified
  Technical English.
- The backend count in the documents was four and is six. The guard count in
  `docs/how_it_works.md` was three and is four.

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
