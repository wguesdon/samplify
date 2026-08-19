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

## [0.17.0] - 2026-08-19

The eighth review with no list of past findings reports one major item and two
medium items.

### Fixed

- `apply` refuses a name of the data file that the mapping never saw and that
  already equals a name the mapping produces, when the mapping records
  `reviewed: false`. Those rows join a group that no person put them in, and
  the rule is now the one that already governs a collision between two groups.
  A reviewed mapping is allowed and reported.
- The summary of the log counts the unique names of the file. It counted the
  size of the mapping, so a run against a second file reported a number that the
  file does not hold. The size of the mapping is in the summary as
  `names_in_the_mapping`.
- `propose --plot` checks the format of the figure before it writes the mapping
  file. `--plot qc.unsupported` wrote the mapping and then failed at the draw,
  which contradicts the promise that samplify writes all of its files or none of
  them. A destination that is a directory is refused there as well.
- The header of a CSV is checked for a NUL byte, and not only the rows. The
  reader ends a column name at that byte, so the column the caller asked for is
  not the one it found.
- A message about a row names the line a person sees in an editor. It named the
  number of the row, and a value that holds a newline makes one row of two
  lines.

## [0.16.0] - 2026-08-19

The seventh review with no list of past findings reports four major items and
one medium item. Three of them lose data.

### Added

- `apply` reports a name of the data file that the mapping never saw and that
  already equals a name the mapping produces. Both rows then read one name
  although no person put them in one group, which happens when `--data` names a
  second file. It is reported and not refused, because a second file written in
  the canonical form is the usual reason.

### Fixed

- A sign belongs to the word it touches. The identity signature recorded only
  how many numbers stood before a sign, so `control+_batch1` and
  `control_batch+1` both read `0+` and the two samples merged into one. The
  entry now carries the word as well, read through the abbreviation table so
  that `ctrl+` and `control+` still agree.
- A row that holds more values than the header is refused, and the message names
  the line. pandas reads the first column of that file as a row label, so the
  header `sample_id,other` with the row `s1,x,extra` produced the name `x` and
  the name `s1` was gone.
- A NUL byte in any column is refused. The reader ends a value at that byte and
  reports nothing, so a column samplify never touches reached the output cut
  short.
- A model answer that merges two names is refused when one token of the pair is
  a substitution of the other. The rule read the whole pair, and it read a
  single token only when that token was the only one to differ, so a model
  merged `Primary B cells1` with `Primary T cellss1`. B cells and T cells are
  two cell types.
- A destination that is a directory is refused before the first file is written.
  `--output out.csv --json-log /tmp` wrote the output CSV and then raised, which
  contradicts the promise that samplify writes all of its files or none of them.

## [0.15.0] - 2026-08-19

The sixth review with no list of past findings reports no major item. Its one
finding is the sign that two typefaces write two ways.

### Added

- The option `--encoding` on `apply` reads a data file in another encoding than
  the one the mapping records. It is needed when `--data` points at a second
  file.
- The option `--encoding` names the character encoding of the CSV. A spreadsheet
  on Windows writes cp1252, and that file raised a decoding error that named a
  byte and no file. `propose` records the value in the mapping file, and `apply`
  reads and writes the same one, so no column that samplify leaves alone changes
  its bytes. A file read as `utf-8-sig` is written as `utf-8`, so a file that
  carried no byte order mark does not gain one. samplify guesses no encoding,
  because the wrong guess changes a name and says nothing.

### Fixed

- A mapping file is UTF-8 whatever the locale of the machine. A container and a
  batch node run under `LC_ALL=C`, where the default is ASCII, and a name that
  held an accent could then neither be written nor read. Both ends now name the
  encoding, because a JSON document is UTF-8 by definition, and a file in
  another encoding names itself in the error. The file also keeps the
  characters of a name rather than escaping them, because a person reads it.
- One sign written two ways is one sign. `rules.IDENTITY_SIGNS` and
  `rules.HYPHENS` made the typographic forms count, and the identity signature
  then kept the raw character, so `CD4-` and `CD4−` carried two identities and
  never merged. `rules.prepare` folds every spelling to one character before the
  token rule and the signature read the name. The plus-minus sign and the double
  prime stand for themselves and fold into nothing.
- A CSV that cannot be parsed names itself. An unclosed quote raised a pandas
  error that named no file and no cause.
- The inventory of every call that writes a file reads `os.replace` and an
  `open` in a writing mode. It counted `str.replace` as well, so editing a
  message made the test fail.

## [0.14.2] - 2026-08-19

The fifth review with no list of past findings. Its one finding loses a row.

### Fixed

- A blank line in a CSV is a row and it reaches the output. pandas drops an
  empty line by default, so a file of three rows gave an output of two, and a
  row lost is the one thing this tool must never do. A whitespace-only cell was
  already kept, and a truly empty line was not.
- The similarity panel of the figure scores the letters that decided each pair,
  which is the differing token when there is one. It scored the whole name, so
  `sample_A` against `sample_AA` showed 0.875 and read as agreement while the
  tool had refused the pair.

## [0.14.1] - 2026-08-19

The fourth review with no list of past findings reported that it found no major
defect. Its one finding is below.

### Fixed

- `docs/how_it_works.md` showed the signature of a sign without its position
  marker. The sign gained that marker in 0.13.0 and the example kept the old
  form, so a reader was told `("1", "+")` where the code gives `("1", "0+")`.

### Added

- A test that reads every signature the document shows and compares it with the
  one the code gives. A document that shows an output is showing a promise.
- A test that the newest changelog entry is the version that ships, that no
  version is written twice, that the versions run downwards and that no entry
  is empty. Two edit scripts had replaced a heading that did not exist and
  carried no check, so three entries were lost while the version kept moving.

## [0.14.0] - 2026-08-19

A third review with no list of past findings. Both of its findings are real and
one of them merged two different samples.

### Fixed

- A whole token added or removed is not a typing error, and samplify refuses a
  pair where one name holds every token of the other and one more. The corpus
  held five such merges. `MSTO-211H PBS 6h` and `MSTO-211H_R PBS 6h` are a
  parental cell line and the resistant line derived from it in a study of
  pemetrexed resistance, and the words around the added token made it look like
  one inserted letter. A name written without delimiters is not that shape, so
  `p1b1` and `p1_b1` still merge.
- A difference is judged against the token that holds it, when the two names
  hold the same number of tokens and exactly one differs. Shared context must
  not license a difference. `sample_A` and `sample_AA` differ by one letter in
  a name of seven, and they are two identifiers. The corpus held one merge of
  that shape: samplify kept `SMB` and `USMB` apart and merged
  `SM B from healthy control` with `USM B from healthy control`, which are the
  same two samples written out.
- The warning that says the sample names are leaving this machine reads the
  host from the URL and compares it whole. It looked for the text `localhost`
  anywhere in the URL, so `localhost.example.com` and `127.0.0.1.evil.example`
  passed as this machine, and that line is the one that tells a person their
  sample names are going elsewhere.

The corpus gives 26 merges now rather than 32, and each of the 26 was read: 24
are a difference of formatting, one is a real transposition and one moves a
replicate number. The six that this version removed had been reported as
correct after 0.7.0, and they were not. `README.md` and the figure say so.

## [0.13.0] - 2026-08-19

A second review with no list of past findings. It named four defects, three of
which are real and two of which destroy a file.

### Fixed

- A sign records how many numbers stand before it, so `control+_batch1` and
  `control_batch1+` are two names. The signature held the signs in a list at
  the end and lost where each one stood, so the two merged. The numbers keep
  the first places of the signature and their positions never move, because the
  near-miss search reads a number by its position.
- No two outputs of one command may name one file. `apply --output clean.csv
  --json-log clean.csv` wrote the CSV and then replaced it with the log, and
  `propose -o qc.png --plot qc.png` replaced the mapping with the figure. Each
  command now refuses that before it writes anything.

### Not a defect

The review reported that a whitespace-only cell is dropped. It is not a name,
so it forms no group, and the row survives with every column unchanged and the
cell carrying its own value into the canonical column. Three rows in gave three
rows out when this was run.

## [0.12.3] - 2026-08-19

### Fixed

- `propose` writes all of its files or none of them, in the same way that
  `apply` does. The mapping file was written and then a figure with a bad path
  failed, so the command reported an error while one of its files was on disk.

### Added

- Tests that drive every command with every pair of its output options pointing
  at one path, and a test that a failed command leaves no file behind.

## [0.12.2] - 2026-08-19

### Added

- `tests/test_the_claims.py` quotes each promise that `README.md` makes and
  tests the code against it. A document is where a person learns what a tool
  guarantees, so a claim in it is a promise, and the test fails if one of those
  sentences is reworded without the test moving too.

### Fixed

- `apply` writes all of its files or none of them. Each destination is checked
  before the first one is written. The output CSV was written and then a log
  with a bad path failed, so the command reported an error and exited with the
  status 1 while one of its files was already on disk. An exit code of 1 now
  means that nothing was written.

## [0.12.1] - 2026-08-19

### Fixed

- A file separated by tabs says why it cannot be read. It reads as one column
  whose name holds every heading, so the message listed one available column
  that looked like the whole header line and said nothing about the cause. A
  file separated by tabs is the common alternative in this field, and the ENA
  archive serves one.

## [0.12.0] - 2026-08-19

A review with no list of past findings, written to check that the exclusions
given to the earlier passes hid nothing, found two defects that merge two
different samples. They had been hidden.

### Fixed

- A sign identifies a sample in every typeface. Only the ASCII prime and the
  ASCII hyphen were kept, so a name that a word processor or a journal wrote
  lost its sign: `WT2-1′` merged with `WT2-1` and `CD4−_donor1` merged with
  `CD4_donor1`. `rules.IDENTITY_SIGNS` now holds the prime, the double prime,
  the right single quotation mark, the plus-minus sign and the fullwidth plus,
  and `rules.HYPHENS` holds the nine characters that a keyboard, a word
  processor or a journal uses for a hyphen or a minus. Each of the nine
  separates two tokens where the ASCII hyphen would, and identifies a sample
  everywhere else.
- A mapping file read from disk remembers where it came from, and `apply`
  refuses to write an output over it. The guard needed the caller to name the
  file, which the command line does and a library caller has no way to do, so
  `apply_mapping(read("mapping.json"), output_path="mapping.json")` destroyed
  the decisions. The path is never written into the document, because it
  describes the copy and not the mapping.

## [0.11.5] - 2026-08-19

### Changed

- `MIN_SLIP_LENGTH` is measured rather than chosen. It was set to five from
  three hand-picked examples. Eleven pairs in the reference corpus turn on that
  rule alone, which means the ratio refuses them and only the rule could join
  them. Their shortest skeletons run from one letter to four, and every one of
  the eleven is two different samples: `KMM-1` against `MM1` are two myeloma
  cell lines, `SMB` against `USMB` differ by a prefix, and `CPT2` against
  `CPT2-H` differ by a condition. Five is the smallest value that refuses all
  eleven, and no pair of five letters or more in that corpus turns on the rule
  at all. The value does not change, and it now rests on the measurement.

- `MAX_VARIANT_LETTERS` is measured rather than chosen, in the same way. In the
  reference corpus 1002 positions hold exactly two letters and 349 hold three
  or more. Every position of three or more that was read is a plate well or a
  replicate letter, such as `RNA-seq_A549_24h_A01` through `D01`, and the
  positions holding two letters carry the real contrasts, such as `3C1` against
  `3N1`. Two is the value that keeps the contrasts and drops the fields, and it
  does not change.

### Added

- A test for each of the eight readable pairs above, and a test that fails if
  either limit is moved and that says why.

## [0.11.4] - 2026-08-18

The twentieth review reported that it found no major defect. That is the second
pass in a row to say so since the last major finding, and the loop stops here.

### Fixed

- A fractional group id is refused. `int(1.5)` is 1, so the id became a whole
  number and the log recorded a group that the file never named. JSON holds one
  number type, so `3` and `3.0` are still read as the same id.

### Added

- An inventory test of every call in the package that writes a file. Six calls
  write one, and each destination is either checked against every input of its
  command or is the mapping file that `review` was given, which is what that
  command exists to change. A new write cannot be added without a guard and a
  line in that test.

## [0.11.3] - 2026-08-18

The nineteenth review reported that no finding is major.

### Fixed

- Each name inside a `near_misses` pair must be text that holds a character.
  The pair itself was checked and its two entries were not, and the figure
  reads the length of each name, so `samplify plot` raised a `TypeError` on a
  file holding a number there.

### Added

- Tests for every spelling of one path against the identity guard, which are a
  dot segment, a parent segment and a doubled separator, and a test for an
  alias that is the parent directory rather than the file.

## [0.11.2] - 2026-08-18

The eighteenth review found that the self-overwrite guard compares the text of
a path, and that a second name for one file walks through it.

### Fixed

- An output that names the same file as an input is refused, and not only an
  output that spells the same path. A hard link is a second name for one file,
  and `Path.resolve` follows a symbolic link while knowing nothing of a hard
  link, so `apply mapping.json --output alias.csv` overwrote the input through
  its alias. The comparison is `Path.samefile` when both paths exist, and the
  resolved names when the output does not exist yet.
- A group whose `occurrences` is `false`, `0`, `""` or `[]` is refused.
  `data.get("occurrences") or {}` read every one of those as an empty object,
  so a malformed file passed as a valid one.
- `Group.validate` checks the last two fields it did not: `method` must be text
  and `min_similarity` must be a ratio between 0.0 and 1.0 or absent. The review
  step prints that number to the person who is deciding.

### Added

- A test that builds a hard link and a symbolic link to the input and gives
  each to `apply --output`.
- A sweep over every field of a group and every wrong shape, matching the one
  the mapping file already had.

## [0.11.1] - 2026-08-18

The seventeenth review reported that it found no major defect. Its one finding
named one field, and the whole sub-class is closed instead.

### Fixed

- Every text field of a mapping file is checked. `input_file`, `column`,
  `model`, `provider`, `base_url`, `canonical_pattern`, `method`, `created` and
  `reviewed_at` must each be text or absent. `Path(1)` raises a `TypeError`
  further down, and this class documents `ValueError`, so `apply` showed a
  traceback for a malformed mapping instead of refusing it.

## [0.11.0] - 2026-08-18

The sixteenth review reported that it found no major defect. Its one finding
changes which names reach a group, so this is a minor version.

### Fixed

- The `auto` backend keeps every offline cluster. Two clusters can normalise to
  one representative, and a plain dictionary then kept one of them and dropped
  the other, so a sample disappeared from the file a person reviews.
  `sampleI1` and `sampleİ1` are two identities that share the representative
  `samplei1`.
- Both model backends split the members they assemble, and not only the
  representatives they were shown. One representative can carry members of more
  than one identity, and `_split_by_identity` now takes those apart by digit
  signature and by the substitution rule.

Two names that keep the same canonical name after all of that are two groups
proposing one name, and `apply` refuses that in a mapping no person reviewed.
The tool asks rather than joining them.

### Added

- A property test that asks the model to merge every name, and then to merge
  none, over both model backends. Neither answer may lose a name from the file
  a person reviews, and neither may put two identities in one group.

## [0.10.9] - 2026-08-18

Found by sweeping every command with every malformed input myself.

### Fixed

- `samplify names --file` reports a file it cannot read instead of raising a
  traceback. The decode happens while the lines are read, so a file in another
  encoding escaped the block that catches a missing file. The file is read as
  `utf-8-sig` as well, so a list that Excel wrote does not carry a byte order
  mark into its first name.

## [0.10.8] - 2026-08-18

The fifteenth review reported that no finding is major. Its one finding is
below, with two more that came from sweeping every field of a mapping file
myself rather than waiting for a sixteenth pass to name them.

### Fixed

- Zero padding falls away when a letter follows the number. The pattern ended
  at the digits, so `sample001a` kept its padding while `sample001` lost it,
  and `digit_signature` had already read `sample001a` and `sample1a` as one
  identity while the rules backend kept them apart.
- `near_misses` and `diagnosis` are checked and not coerced. `list(None)` and
  `dict(None)` raise a `TypeError`, and this class documents `ValueError`, so a
  malformed file reached the user as a traceback from `review`, from `apply`
  and from `plot`. A file that holds `null` for either field reads as empty, as
  a file that omits it always has.

### Added

- A test that gives every command fourteen malformed mapping files, including
  a JSON array, a bare number and text that is not JSON at all, and asserts
  that each one answers with a message rather than a traceback.

## [0.10.7] - 2026-08-18

The fourteenth review reported that no finding is major.

### Fixed

- A count of rows must be a whole number that is not negative. `rows` sums the
  counts, and a null count crashed that sum with a `TypeError` rather than
  refusing the file. The review step prints that number to the person who is
  deciding.
- The rules backend splits a word from its number in any script. An ASCII-only
  letter class left `Пациент٠١` with its padding while `patient01` lost it, so
  the identity rule had joined the two names and the rules backend still kept
  them apart.

### Added

- Two property tests over generated CSV files. The first checks that `apply`
  keeps every row and every column it does not write. The second accepts and
  rejects groups in every combination and checks that no row is lost and no
  canonical name is empty.

## [0.10.6] - 2026-08-18

The thirteenth review found that the guard added in 0.10.0 and 0.10.3 was
incomplete, and that the gap could destroy a reviewed mapping file.

### Fixed

- `apply` refuses an output that points at the mapping file, not only one that
  points at the data CSV. The command reads two files and neither survives
  being written over, and `apply mapping.json --output mapping.json` replaced
  the decisions a person had made with CSV data.
- `Group.validate` checks the id, so the Python API refuses what the file
  reader already refused. `Group(id=True)` validated and resolved, because
  `bool` is a subclass of `int`.
- `occurrences` must be an object. `dict(None)` raises a `TypeError`, and this
  class documents `ValueError`. A file that holds `null` for the field reads as
  empty.

### Added

- `tests/test_no_self_overwrite.py` drives every command with every output
  aimed at every file that command reads. Three reviews found one instance of
  this fault each, and each fix guarded one more path. A new output option now
  has to be added to that table, or the test says the guard is missing. The
  test was run against a disabled guard first, and it failed as it should.

## [0.10.5] - 2026-08-18

The twelfth review reported that no finding is major, and it was the second
pass in a row to say so. Its one finding is below.

### Fixed

- The normalisation removes padding in any script, as the identity signature
  already did. 0.10.2 fixed `digit_signature` and left `_expand_token`, so the
  `rules` backend still kept `s٠١` and `s١` apart while the identity rule had
  already joined them. Every place that removes padding now calls one function.

## [0.10.4] - 2026-08-18

The eleventh review found one defect and reported that it is not major.

### Fixed

- A group id given as `true` is refused. `bool` is a subclass of `int` in
  Python and `int(True)` is 1, so a group whose id was `true` became group 1
  and every check downstream passed.

## [0.10.3] - 2026-08-18

Found by reading the code rather than by a review. Two commands were guarded
against writing over their own input and a third was not, so the class is
closed by auditing every path that writes a file.

### Fixed

- `samplify plot` refuses an output that points at the mapping file it reads.
- `samplify plot` reports a format that matplotlib cannot write instead of
  raising a traceback. matplotlib decides the format from the extension of the
  path, and `-o qc.json` reached the user as a stack trace.

Every command now refuses to write over its own input: `propose` for its
mapping file and its figure, `apply` for its output CSV and its two logs, and
`plot` for its figure. `review` writes the mapping file it read, and that is
what the command is for.

## [0.10.2] - 2026-08-18

A tenth review found two defects.

### Fixed

- `propose` writes no output over its own input. `-o data.csv` wrote the mapping
  JSON over the CSV it had just read, and the names were gone. `--plot` is
  refused the same way. 0.10.0 guarded the three outputs of `apply` and left
  these two.
- Zero padding falls away in any script. `str.lstrip("0")` removes the ASCII
  zero and nothing else, so the Arabic-Indic `٠١` kept its padding while `01`
  lost it, and the two spellings of one number had different identities and
  never grouped. The digits keep their own script, so `sample١` and `sample1`
  stay apart for the same reason that `sample_9α` and `sample_9a` do.

## [0.10.1] - 2026-08-18

### Fixed

- A group that lists one member twice is refused. It misled the person at the
  moment they decide: `rows` sums the occurrences once for each entry, so a
  sample that appears three times was reported as six rows, and `is_merge` read
  two entries as two names, so a group holding one name asked for a decision
  that had nothing in it.

## [0.10.0] - 2026-08-18

A ninth review found one defect.

### Fixed

- `apply` writes no output over its own input. `--output`, `--json-log` and
  `--csv-log` are each refused when they point at the file the mapping was
  built from. samplify promises that the input survives the run, so that a
  person can read the original spelling after a decision they regret. One
  character of a shell command separates `--output clean.csv` from
  `--output data.csv`, and a log written over the input would lose the file
  completely.

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
