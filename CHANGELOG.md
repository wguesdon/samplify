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

## [0.9.9] - 2026-08-18

An eighth review found one defect, and it was the last of a class that seven
reviews had reported one instance at a time. The class is closed rather than
patched again.

### Changed

- `Group.validate` holds every check that a group has to pass, and both paths
  call it. `Group.from_dict` called the checks for a file, `Group.resolved`
  called a different and shorter set for a caller building a group in Python,
  and every review found one more field that only the first path checked. The
  two cannot drift apart now.
- The last instance found: `members` given as a string. A string is iterable,
  so `members="AB"` read as the two samples `A` and `B` everywhere a list was
  expected, and `resolved` merged them both into one name.

## [0.9.8] - 2026-08-18

A seventh review found two defects, both of them in the same place: the Python
API was guarded less than the file reader.

### Fixed

- `final_mapping` refuses a name that two groups claim. Reading a mapping file
  has always refused it, and a caller that builds a `MappingFile` in Python did
  not go through that check. `dict.update` let the last group win, so one group
  decided the name of the sample and the other was ignored in silence, and the
  collision report stayed empty.
- A `groups` entry that is not an object is refused with a `ValueError`.
  `"groups": [null]` raised a `TypeError`, and the class documents `ValueError`.

## [0.9.7] - 2026-08-18

### Fixed

- A file that Excel wrote is read the same way by both of the readers that
  samplify uses on its header. Excel starts a CSV with a byte order mark,
  pandas strips it and the default encoding does not, so the duplicate-column
  check saw `\ufeffsample_id` where pandas saw `sample_id`. It counted one
  `sample_id` in a file that holds two, pandas renamed the second one, and half
  the names were invisible. That is the defect that 0.4.0 repaired, reachable
  again through a byte order mark.

## [0.9.6] - 2026-08-18

A sixth review found one defect, down from four.

### Fixed

- A character that the rules can neither read nor safely drop now joins the
  identity signature. A superscript such as `²` is alphanumeric and is neither
  a letter nor a decimal digit, and `int` refuses it, which crashed the
  near-miss search. A combining mark is what `İ` becomes when it is
  lower-cased, and dropping it made `sampleİ1` the same name as `sampleI1`. Two
  names that differ by a Greek letter already stayed apart, so these had to as
  well. Neither shape appears in any of the 36073 names of the reference
  corpus.
- Every test for a number reads `str.isdecimal` and not `str.isdigit`.
  `'²'.isdigit()` is True and `int('²')` raises, and that pair of facts is what
  crashed the search.
- `Group.resolved` refuses a status it does not know and refuses to rename a
  member to an empty name. Reading a mapping file checks each field, and a
  caller that builds a `Group` in Python does not go through that check, so a
  group with the status `corrupt` and an empty final name renamed a sample to
  nothing.

## [0.9.5] - 2026-08-18

### Changed

- `llm_bioinformatics_naming_tools.md` is in Simplified Technical English. It
  was the one tracked document that was not, and the repository is now public.
  Every one of its 22 links and DOIs is unchanged, and the LinkedIn draft at the
  end is kept byte for byte, because it is a draft in the voice of the author.
  The note that samplify fills the gap it describes is new.

### Fixed

- A group id that is not a number is refused with a `ValueError`. `int(None)`
  raises a `TypeError`, and the class documents `ValueError`, so a caller had to
  catch two kinds of error for one malformed file.

### Not changed

- The identity signature records which signs a name holds and not where each
  one stood, so `cd4+_donor1` and `cd+4_donor1` share one signature. Of the
  17683 names in the reference corpus that hold a sign, exactly one pair differs
  only in the order of its characters, and that pair moved a number rather than
  a sign and is one sample written two ways.
- The check that splits a model cluster reads one substituted letter and
  nothing wider, so a model that joins two names two edits apart, one of them a
  substitution, is not split. That is the boundary of what a rule can decide
  without reading the meaning of the words, and the review step stands behind
  it.

## [0.9.4] - 2026-08-18

### Fixed

- The collision guard reads `reviewed is not True` and no longer reads the
  field for truthiness. Reading a mapping file refuses anything but a boolean,
  and a caller building a `MappingFile` in Python does not go through that
  check. The string `"false"` is truthy, so it switched the guard off and two
  patients merged. Every value except `True` is now a refusal.

## [0.9.3] - 2026-08-18

### Fixed

- `samplify plot` reports a figure it cannot write instead of raising a
  traceback. It caught `ImportError` for the missing matplotlib and nothing
  else, so a directory that does not exist, a full disk or a path with no write
  permission all reached the user as a stack trace. The figure is written last,
  so the traceback also hid the fact that the proposal itself had succeeded.

## [0.9.2] - 2026-08-18

### Fixed

- `apply` reports every collision it applies. It refuses one in a mapping that
  no person reviewed and it allows one in a reviewed mapping, because a person
  signed for it. It said nothing in the second case, so a file claiming
  `"reviewed": true` could join two patients into one sample with no line of
  output. Joining two groups into one name is the most consequential thing this
  tool does and it is no longer done in silence. The log records the collisions
  in a new `collisions` field.
- A mapping file whose top level is not an object is refused with a message.
  `json.load` returns whatever the file holds, and a list has no `.get`, so a
  file holding a list reached the user as an `AttributeError` traceback.

### Not changed

The edit cap governs one pair, and a group is built from many pairs, so a chain
of one-edit steps can hold two ends that are two edits apart. That is not the
case that `split_on_a_substitution` repairs. A chain carries evidence, because
some third name is one edit from both ends, and that is the reason to believe
the three are one sample. A substitution carries the opposite. The reference
corpus holds no group at all in which a pair joined by a distance sits above the
cap. A test now pins the behaviour so that it stays a decision.

## [0.9.1] - 2026-08-18

A third review found five defects. Two of them merged two different samples.

### Fixed

- A chain of allowed edits can no longer carry a forbidden pair into one group.
  Grouping is transitive and the match rule is not, so `abcde1` joined
  `abcdef1` by one deletion and `abcdeg1` by another, and the two ends are one
  substitution apart. Every group is now checked once it is finished, by the
  same rule the model backends already used. The check lives in
  `matching.split_on_a_substitution` and both callers share it.
- A failure from OpenRouter becomes a clear error instead of a traceback. The
  openai package raises its own exception types and the command line catches
  `ValueError`, so a refused connection, a rejected key and a rate limit all
  reached the user as a stack trace. The ollama path already converted its
  errors this way. An answer with no choices is refused too.
- `samplify names -M auto` works. The parser offered `auto` and the command
  passed it to the offline grouping, which answered `Unknown offline method:
  'auto'` and named the option the person had just been offered. Both model
  methods now run the whole backend, so `names` shows the answer of samplify
  and not the raw answer of the model.
- The message for a missing API key no longer recommends `--method
  levenshtein`, which 0.8.0 removed.
- `matching.clear_name_caches` empties the three caches in one call. Nothing in
  the command line changes a rule at run time, and a test that does needs this.

### Not changed

The model backends are not held to the edit cap. A model that joins `ctrl_1`
with `control_1` joins two names three edits apart, and reading that kind of
difference is the reason those backends exist. The review reported it, and
`docs/how_it_works.md` now states the reasoning.

## [0.9.0] - 2026-08-18

### Fixed

- samplify says where the sample names go before it sends them. `ollama` is the
  private option because the model runs on this machine, and `OLLAMA_HOST` is an
  environment variable that ollama itself uses. It can already be set on a
  machine, so a person could send every sample name to another host without
  typing an option and without reading a word about it. A sample name often
  carries a patient identifier.
- The mapping file records the address in a new `base_url` field, next to the
  provider and the model. A person reading the file can now see that the names
  left this machine. An older file has no such field and reads as `null`.
- The README and `docs/how_it_works.md` said the names never leave the machine,
  and then described the option that sends them elsewhere. Both now say that
  the claim holds by default and what breaks it.

## [0.8.2] - 2026-08-18

### Fixed

- The alias patterns are compiled one time at import and not rebuilt on every
  token. `_expand_token` runs for every token of every name of every
  comparison, and building the pattern string there called `re.escape` 20
  million times on one real study.
- `digit_signature`, `letter_skeleton` and `rule_normalise` are cached. Each is
  a pure function of one string and each ran many times for the same name,
  because every comparison reads both of its names again. `rule_normalise` ran
  86625 times for 2267 unique names.

Neither change alters an answer. The 88 datasets of the near-miss comparison
still agree, and the corpus still gives 32 merges.

| Study and field | Unique names | 0.4.1 | 0.8.1 | 0.8.2 |
|---|---|---|---|---|
| PRJDB5361 `sample_title` | 2267 | 376.9 s | 7.2 s | 1.31 s |
| PRJDB6952 `library_name` | 3243 | 2.7 s | 0.9 s | 0.52 s |

## [0.8.1] - 2026-08-18

A second review of the repaired code found four defects. Three of them merged
two different samples or accepted a value that no mapping file should hold.

### Fixed

- Neither model backend may merge two names that differ by one substituted
  letter. The offline path has refused that since 0.7.0 and the model path did
  not, so a model that answered `primary_cells` for both merged
  `Primary B cells` with `Primary T cells`. Neither name carries a digit, so
  the identity signature is empty for both and the digit guard alone let them
  through. A forbidden pair anywhere in a cluster now sends the whole cluster
  back to one group per letter skeleton. A cluster with no forbidden pair is
  untouched, so the model still joins `ctrl_1` with `control_1`, which is three
  edits and the reason the model backends exist.
- A canonical name that the model returns must be a string that holds a
  character, and the `mapping` it returns must be an object. `str(None)` gave
  the string `None`, and every member of that group took those four characters
  as its sample name.
- The `members` of a group must be a list. A string is iterable, so
  `"members": "AB"` passed every check and became the two samples `A` and `B`.
  The `groups` key must be a list for the same reason.

### Not changed

The apply log records the time of the run, so two runs write two different
logs. That value describes the run and not the result, the output CSV holds no
time value, and `docs/how_it_works.md` says so. The review reported it and it
stays as it is.

## [0.8.0] - 2026-08-18

### Removed

- The `hamming` and `levenshtein` backends. The substitution rule of 0.7.0 left
  neither of them a job of its own. `hamming` finds a substituted character in a
  name of equal length and nothing else, and a substituted letter no longer
  merges, so it answered exactly as `rules` did. `levenshtein` and `damerau`
  differ only in what they charge for a transposition, and at a cap of one edit
  the slip rule decides that case for both, so it answered exactly as `damerau`
  did. A choice that does not change the answer is worse than no choice, because
  a person reads the name and believes it. `-M hamming` and `-M levenshtein` now
  fail with the list of the four that remain.
- `hamming_distance`, `levenshtein_distance` and `similarity` are unchanged and
  still take all three measures. The measures are correct and a caller may want
  them. It is the backend list that shrank.

## [0.7.0] - 2026-08-18

### Fixed

- A substituted letter never merges two names on its own. It is the one edit
  that also carries meaning, and on the ENA corpus it carried meaning every
  time. `Primary B cells` merged with `Primary T cells`, `human cTEC5` with
  `human mTEC5`, `Decell A549 #1` with `Recell A549 #1`, `UV_m_cont_293_1` with
  `UV_p_cont_293_1` and `TSmatKO-1` with `TSpatKO-1`. Not one of the 42 pairs
  it merged there was a typing error.
- `describe_difference` reads two names with the same numbers and the same
  letters as a formatting difference. It called them unrelated, and
  `malaria5#02` against `malaria5#2` is that shape, because the number sign
  stops the token from reaching the zero-padding rule. The figure and the
  console print that label, so both said unrelated about a correct merge.

### Added

- Property tests in `tests/test_properties.py`, with hypothesis as a dev
  dependency. They generate names rather than name cases, and they state the
  three claims a person relies on when they accept a mapping: no group holds
  two digit signatures, `apply` keeps every row and never touches the source
  column, and the result never depends on the order of the input. Each property
  was checked against a deliberately broken implementation first, and each one
  failed as it should. Removing the identity blocking makes the first property
  report `SAMPLE_SAMPLE` merging with `sample0_sample`.
- `find_letter_variants` reports each pair that one substituted letter
  separates, so a refused pair still reaches a person. The pairs join
  `near_misses` in the mapping file, next to the pairs that one digit
  separates. The search is indexed and takes 0.5 seconds on 3243 names.
- `MAX_VARIANT_LETTERS` drops a position that more than two letters occupy,
  because such a position is a field of the naming scheme and not a typing
  error. A 96-well plate writes `A07` through `H07`, and PRJEB20147 holds 1351
  wells and produced 1754 pairs without the rule. It produces 118 with it.
- The console prints the reason next to each reported pair, and it prints at
  most 20 pairs and then the count of the rest. The mapping file holds all of
  them.

### Changed

- The figure reads the reason of each reported pair instead of naming every one
  of them a digit slip.
- The README shows three figures and not one. The worked example and the
  reference set are the output of `samplify plot`, and the third records the
  validation on real data. `docs/make_validation_figure.py` redraws the third.
  Its two colours are the ones `samplify.plots` already uses, so the three read
  as one system, and the pair clears the colour-vision checks.
- The README gains a section on the validation, which states how many of the
  removed merges were read by hand and how many were sampled.

samplify now proposes 32 merges on the ENA corpus, and every one of them was
read by hand and is correct. The count was 350 in version 0.4.1.

| Version | Merges proposed | Wrong by reading |
|---|---|---|
| 0.4.1 | 350 | 246 above one edit, plus the classes below |
| 0.5.0, the edit cap | 104 | 42 substitutions, 30 dropped signs |
| 0.6.0, the signs | 74 | 42 substitutions |
| 0.7.0, the substitutions | 32 | None found |

## [0.6.0] - 2026-08-18

### Fixed

- A sign next to a token identifies the sample and is no longer deleted.
  `CD4+` and `CD4-` are two populations, `DOX+` and `DOX-` are the induced and
  the uninduced arm of one experiment, and `WT2-1'` is a variant of `WT2-1`.
  Normalisation dropped every one of those characters, so the two names became
  one string and the rules path merged them without any distance being
  computed. The plus and the prime are in `rules.IDENTITY_SIGNS`, and both join
  the identity signature, so samplify never compares the two names at all.
- A hyphen is a delimiter only where it separates two alphanumeric characters,
  as in `s1-b1`. A hyphen anywhere else is a sign, as in `dox-`.
  `rules.prepare` applies that rule, and both the tokens and the identity
  signature read it, so the two can never disagree.
- The number sign stays out of the identity. In `#111_b2` it reads as the word
  number and identifies nothing, and no name in the reference corpus used it as
  a sign. The asterisk stays out for the same reason.
- The model prompt names the signs and gives the reason, so a model reads the
  same rule as the offline backends.

On the ENA corpus this removed 30 merges and added none. Every one of the 30
joined two different samples, among them `ICESeq(+)` with `ICESeq(++)` and with
`ICESeq(-)`, and `CXCR5+` with `CXCR5-`. 74 merges remain.

## [0.5.0] - 2026-08-18

The first version measured against real data. 20000 human RNA-seq runs were
read from the ENA portal API, and the free-text fields that the submitting lab
typed were run through samplify. It merged two different samples, so this
version adds a rule and changes which names group together.

### Fixed

- samplify caps the distance between the letters of two names it merges, and
  `MAX_TYPO_EDITS` holds the value 1. A ratio scales with the length of a name,
  so a long shared context hid a short difference that carried the whole
  identity. samplify merged `EVT-TS-1_paired-RNA` with `ST-TS-1_paired-RNA`,
  two cell types two edits and a ratio of 0.857 apart, and
  `Mock_SKNSH transcriptome after vector transfection` with the same sentence
  written `Mock_TGW`, two cell lines five edits and a ratio of 0.889 apart. The
  cap removed 246 of the 350 merges that samplify proposed on that corpus, and
  it kept every real typing error, because all of them were one edit apart.

### Changed

- `damerau_levenshtein_distance` takes an optional `max_distance`. The work
  then stays inside a band of that width around the diagonal, because a path
  that leaves the band already costs more than the band. The result is exact at
  or below the value and reports `max_distance + 1` above it. 200000 random
  pairs were checked against the full grid.
- `describe_difference` reads a transposition from the two differing positions
  instead of running a second distance over the whole grid. 60000 random pairs
  were checked against the previous form.
- `propose` on 2267 sample titles of median length 97 took 376.9 seconds and
  now takes 39.0 seconds. On 3243 library names of median length 53 it took
  2.7 seconds and now takes 1.4 seconds.

### Known and not fixed

The cap is not sufficient. Of the 104 merges that survive it on the same
corpus, 42 come from one substituted letter and 30 from a symbol that
normalisation drops. Both classes are wrong. `TSmatKO-1` merged with
`TSpatKO-1`, which are a maternal and a paternal knockout, and `OVTOKO_DOX+`
merged with `OVTOKO_DOX-`. A substitution has to be judged against the token it
sits in and not against the whole name, and a `+` or a `-` next to a token
carries meaning that normalisation deletes. Version 0.6.0 repairs the second
class.

## [0.4.1] - 2026-08-18

### Fixed

- The near-miss search is indexed and no longer reads every pair. A reportable
  pair agrees on its letters and on every number but one, so samplify indexes
  the names by that agreement and looks up the one number that is allowed to
  differ. The pairwise form compared every pair inside one letter skeleton, and
  a cohort written to one convention holds all of its names in one skeleton. On
  6168 names of that shape the search took 34.5 seconds, and `propose` took
  38.9 seconds. The search now takes 0.03 seconds and `propose` takes 0.32
  seconds. The result is identical, and 88 datasets were compared against the
  previous implementation to establish that.
- The result of `find_near_misses` and every group is unchanged, so this
  version is a patch.

### Added

- A test that fails if the near-miss search becomes quadratic again, and four
  tests for the positions and the shapes that the index has to reach.
- A GitHub Actions workflow in `.github/workflows/ci.yml`. The `test` job runs
  the offline suite and the smoke test on Python 3.10, 3.11, 3.12 and 3.13. The
  `package` job builds the wheel, installs it and runs it from an empty
  directory, which is the check that the `src` layout exists for. The suite
  imports the working copy and cannot see a file that the wheel leaves out.

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
