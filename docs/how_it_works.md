# How samplify works

## The idea

A sample name carries two kinds of information. The letters describe the sample,
and the numbers identify it. The name `patient111_batch2` holds the words patient
and batch, and the numbers 111 and 2. Every rule in samplify follows from that
difference.

A difference in the letters is usually a difference in style or a typing error,
and it is safe to repair. A difference in the numbers is a difference in
identity, and it is never safe to repair automatically. samplify therefore
normalises and clusters the letters, and it treats the numbers as fixed.

## The workflow

The work happens in three commands, and each command writes a file.

| Step | Command | Model call | Output |
|---|---|---|---|
| Propose | `samplify propose` | At most one | `mapping.json`, every group `proposed` |
| Review | `samplify review` | None | The same file, every group decided |
| Apply | `samplify apply` | None | The output CSV and the change log |

The separation of the three steps is deliberate. A model or a distance measure
makes the proposal, and the proposal is a guess. The decision belongs to a
person. The change is a mechanical step, and any person can repeat it and check
it. One command for all three steps hides which step a person checked.

The `samplify names` command shows the result of a backend for a few names, and
it writes no file. Use it before you run a backend on a file.

## The mapping file

The mapping file is the file that a person reviews, that git stores and that
`apply` reads. It holds one group for each candidate sample. The example below
is shortened, and a real file also records the input path, the column, the
diagnosis, the summary and the times.

```json
{
  "schema_version": 1,
  "method": "damerau",
  "model": null,
  "provider": null,
  "base_url": null,
  "reviewed": true,
  "near_misses": [["patient111_batch2", "patient11_batch2"]],
  "groups": [
    {
      "id": 3,
      "members": ["P1_B1", "p01_b01", "p1-b1", "patient1_batch1", "patietn1_batch1"],
      "proposed": "patient1_batch1",
      "final": "patient1_batch1",
      "status": "accepted",
      "occurrences": {"P1_B1": 1, "p01_b01": 1, "p1-b1": 1},
      "method": "damerau",
      "min_similarity": 0.6667
    }
  ]
}
```

The status of a group has four values.

| Status | Effect |
|---|---|
| `proposed` | No person made a decision. |
| `accepted` | samplify applies the proposed name to every member. |
| `edited` | samplify applies the name that a person typed. |
| `rejected` | Every member keeps its original name. |

A rejection never deletes a row, and it never writes a null value.

The file is text, it is small, and it stays the same between two runs. Commit the
file with the analysis. A diff then shows the cleanup step.

## The four backends

| Backend | What it finds | Model call |
|---|---|---|
| `rules` | Delimiter, letter case, zero-padding and abbreviation differences | None |
| `damerau` | The same, plus one inserted, dropped or swapped letter | None |
| `llm` | The names that the rules and the distance do not group | One call, all the names |
| `auto` | Clusters offline first, then sends one name for each cluster | One call, few names |

Version 0.7.0 held six. `hamming` and `levenshtein` were removed in 0.8.0,
because the substitution rule left neither of them a job of its own. `hamming`
finds a substituted character in a name of equal length and nothing else, and a
substituted letter no longer merges, so it answered exactly as `rules` did.
`levenshtein` and `damerau` differ only in what they charge for a transposition,
and at a cap of one edit the slip rule decides that case for both, so it
answered exactly as `damerau` did. A choice that does not change the answer is
worse than no choice, because a person reads the name and believes it.

`hamming_distance`, `levenshtein_distance` and `similarity` still take all three
measures. The measures are correct and a caller may want them. It is the backend
list that shrank.

### rules

The `rules` backend applies the character rules in `src/samplify/rules.py`. It does
five operations on each name.

1. It changes every capital letter to a small letter, and it replaces each
   hyphen that separates two alphanumeric characters with an underscore.
2. It splits the name at each delimiter.
3. It joins a number to the word in front of it, so `s_8` and `s8` reach the
   abbreviation table as one token.
4. It expands each abbreviation and removes the zero-padding from each number.
5. It joins the tokens with an underscore.
6. It removes each character that is not a letter, a digit, an underscore or a
   sign. A letter in any script survives, because it can carry the identity of
   the sample, and so does a sign.

samplify puts two names in the same group when the two names normalise to the
same string.

samplify defines the abbreviation table one time. The `rules` backend, the CSV
diagnosis and the model prompt all read the same table. Version 0.1.0 held the
table two times, and the two copies were already different.

The abbreviation `t` is not an alias for treatment. A token such as `t1` is a
timepoint at least as often as it is a treatment. A token that keeps its short
form is easy to repair later. A token with the wrong expansion merges two
samples, and the row count drops with no error.

### The three measures

Hamming distance counts the positions where two strings of equal length differ.
It is the correct measure for a substituted character. It has no value for two
names of different lengths, and `hamming_distance` then returns `None`. A number
in that condition misleads the caller.

Levenshtein distance counts the insertions, the deletions and the substitutions.
It also accepts two names of different lengths, and Hamming distance does not.

### damerau

Damerau-Levenshtein distance adds the exchange of two adjacent characters, and it
is the default. One keystroke makes that exchange, but Levenshtein distance
counts two edits for it. The difference decides real cases. The pair `patient`
and `patietn` scores 0.833 under Levenshtein and 0.917 under
Damerau-Levenshtein. A threshold of 0.85 therefore rejects a true typing error
under the first measure and accepts it under the second measure.

### llm and auto

The `llm` backend sends every unique name to the model in one request. The `auto`
backend clusters the names offline first. It then sends one representative name
for each cluster, so the request is much smaller. The `auto` backend makes no
model call when the offline pass finds no inconsistency and forms no cluster.

samplify checks each proposal from the model, and both backends apply the same
check. If the model gives one canonical name to two names with different
numbers, samplify keeps the two apart. It does the same when two names differ
by one substituted letter. Each of the two then keeps its own canonical name.
The model advises, and the identity rules decide.

The check that splits a model cluster reads one substituted letter and nothing
wider. A model that joins `Primary B cells` with `Primary T celss` joins a pair
two edits apart, one of which is the substitution, and the check does not fire.
That is the boundary of what a rule can decide without reading the meaning of
the words, and the review step is what stands behind it. `--yes` records
`"reviewed": false` so that the file says no person stood there.

samplify does not hold the model to the edit cap. A model that joins `ctrl_1`
with `control_1` joins two names three edits apart, and reading that kind of
difference is the reason the model backends exist. The cap belongs to the
distance backends, which have no other evidence to work from. A model that
proposes a merge no person would accept is what the review step is for, and
`--yes` records `"reviewed": false` for exactly that reason.

Version 0.3.0 ran that check in the `auto` backend alone. The `llm` backend took
the groups of the model as they came, so a model that gave one name to `p111`
and to `p112` merged two patients.

### The two providers

Two services answer the request of the `llm` and `auto` backends.

| Provider | Server | Key | Default model |
|---|---|---|---|
| `openrouter` | The OpenRouter API | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` |
| `ollama` | `http://localhost:11434` | None | `qwen3.5:9b` |

The option `--provider ollama` runs the model on the local machine, so by
default the names never leave it. `OLLAMA_HOST` and `--base-url` point at
another machine, and the names then go to that machine. `OLLAMA_MODEL` and
`--model` choose the model.

`OLLAMA_HOST` is an environment variable that ollama itself uses, so it can
already be set on a machine before samplify runs, and a person can redirect
every sample name to another host without typing an option. samplify therefore
prints the address before it sends anything when the address is not this
machine, and it records the address in the `base_url` field of the mapping
file. A sample name often carries a patient identifier, so the record has to
say where it went.

samplify calls the native ollama endpoint rather than the OpenAI-compatible one,
because only the native endpoint takes `format` and `think`. A model with the
thinking capability writes a long reasoning block before the answer. On a CPU
that block is the whole cost. One request with the block did not finish in 280
seconds, and the same request with `think: false` finished in 9 seconds.
samplify reads the capabilities of the model first, because the field is not
valid for a model that cannot think.

The mapping file records the provider next to the model, so a person reading the
file sees which service produced the proposal.

## The identity rule

samplify compares two names only when their digit signatures agree exactly. The
signature is the sequence of the numbers in the name without the zero-padding.
The name `p111-batch03` therefore has the signature `("111", "3")`.

A letter that follows a number is also part of the signature, because a cohort
labels its replicates `sample9a` and `sample9b`. Those two names differ by one
substituted letter, and a distance backend merges them without this rule. The
signature of `sample_9a` is `("9a",)` and the signature of `sample_9b` is
`("9b",)`, so samplify never compares the pair.

A letter counts in any script. An ASCII-only rule deletes the suffix of
`sample_9α` and of `sample_9β`, and the two names then merge.

A letter run with a digit behind it is not part of the signature, because it
introduces the next number of the name. The `b` of `p1b1` is that kind of
letter, so the signature of `p1b1` is `("1", "1")` and it agrees with the
signature of `p1_b1`. The compact form and the delimited form of one name reach
the same block for that reason.

A sign joins the signature after the numbers, and it records how many numbers
stand before it, so that `control+_batch1` and `control_batch1+` are two names.
The numbers keep the first places of the signature and their positions never
move, because the near-miss search reads a number by its position. `rules.IDENTITY_SIGNS` holds the
plus and the prime, and a hyphen counts as a sign wherever it does not separate
two alphanumeric characters. Each sign also records how many numbers stand
before it, so the signature of `ovtoko_dox+_br1` is `("1", "0+")` and the
signature of `ovtoko_dox-_br1` is `("1", "0-")`.

The rule has two effects. It keeps `p111` and `p112` in separate groups at every
threshold. It also reduces the number of comparisons, because samplify measures
only the names that share a signature.

## The signs

A sign next to a token identifies the sample. `CD4+` and `CD4-` are two
populations of one donor. `DOX+` and `DOX-` are the induced and the uninduced
arm of one experiment. `WT2-1'` is a variant of `WT2-1`. Version 0.5.0 deleted
every one of those characters, so the two names became one string and the rules
path merged them with no distance computed at all.

A hyphen is the difficult one, because it does both jobs. In `s1-b1` it
separates two tokens, and in `dox-` it is the opposite of `dox+`. The rule reads
the position. A hyphen between two alphanumeric characters separates, and a
hyphen anywhere else is a sign. `rules.prepare` applies that rule one time, and
both the tokens and the identity signature read its result, so the two can never
disagree about a hyphen.

A sign is a sign in every typeface. A name that arrives from a word processor
carries the typographic prime and the Unicode minus rather than the ASCII ones,
and `rules.IDENTITY_SIGNS` and `rules.HYPHENS` hold both. Only the ASCII forms
were kept until version 0.12.0, so `WT2-1′` merged with `WT2-1` and
`CD4−_donor1` merged with `CD4_donor1`.

The number sign is deliberately not a sign. In `#111_b2` it reads as the word
number and it identifies nothing. The asterisk is absent for the same reason,
because it marks a footnote more often than a sample.

On the ENA corpus this rule removed 30 merges and added none. `ICESeq(+)`,
`ICESeq(++)` and `ICESeq(-)` are three conditions of PRJDA74549 that samplify
had joined into one sample.

## When a distance is enough on its own

A ratio threshold does not find a typing error in a short name. The pair `smple`
and `sample` scores 0.833, which is below every usual threshold, and the fault is
one dropped letter.

One inserted letter, one deleted letter or one exchange of two letters therefore
matches at every ratio. One keystroke makes each of those three faults.

That rule holds from five letters up, and `MIN_SLIP_LENGTH` in
`src/samplify/matching.py` holds the limit. The value is measured. Eleven pairs
in the reference corpus turn on this rule alone, their shortest skeletons run
from one letter to four, and every one of the eleven is two different samples.
Five is the smallest value that refuses all eleven, and no pair of five letters
or more in that corpus turns on the rule at all. Below five letters the same edit
separates two real terms. The pair `wt` and `wnt` is wildtype and the Wnt gene
family, the pair `t` and `tp` is a treatment and a timepoint, and the pair `k`
and `ko` is a plate letter and a knockout. A short pair therefore has to clear
the ratio like any other pair, and `wt` against `wnt` scores 0.667.

## The token that holds the difference

Two names that hold the same number of tokens and differ in exactly one are
judged on that token alone. The rest is context that the two share, and shared
context must not license a difference.

`sample_A` and `sample_AA` differ by one letter in a name of seven letters, and
they are two identifiers. Judged on the whole name the difference is one
insertion in seven, which the slip rule accepts. Judged on the token it is `a`
against `aa`, which is one letter against two, and no rule accepts that.

The reference corpus held one merge of this shape. samplify kept `SMB` and
`USMB` apart and merged `SM B from healthy control` with
`USM B from healthy control`, which are the same two samples written out. The
words they share made the difference look small.

A whole token added or removed is not a difference of spelling at all, and no
keystroke produces one. samplify refuses a pair where one name holds every
token of the other and one more. The corpus held five such merges.
`MSTO-211H PBS 6h` and `MSTO-211H_R PBS 6h` are a parental cell line and the
resistant line derived from it in a study of pemetrexed resistance, and the
words around the added token made it look like one inserted letter.

A name written without delimiters is not that shape. `p1b1` holds the one token
`pb` and `p1_b1` holds `p` and `b`, and neither list is inside the other, so
those two are compared as whole names and still merge.

When the token counts differ in any other way, or more than one token differs,
the whole letter skeleton decides, because no single token holds the
difference.

## The edit cap

A ratio is not enough on its own at the other end of the scale either. A ratio
scales with the length of the name, so a long shared context hides a short
difference that carries the whole identity. samplify therefore also caps the
distance, and `MAX_TYPO_EDITS` holds the value 1. A slipped keystroke is one
edit, and it is one edit whatever the length of the name.

The cap comes from a run on 20000 human RNA-seq runs of the ENA archive.
Without it samplify merged `EVT-TS-1_paired-RNA` with `ST-TS-1_paired-RNA`,
which are two cell types two edits and a ratio of 0.857 apart. It merged
`Mock_SKNSH transcriptome after vector transfection` with the same sentence
written `Mock_TGW`, which are two cell lines five edits and a ratio of 0.889
apart. Both real typing errors in that corpus were one edit apart. The cap
removed 246 of the 350 merges that samplify proposed there.

The cap costs a name that holds two typing errors, which stays in its own
group. A person then reads two samples where there is one. That is the failure
this tool prefers, because a wrong merge drops a row and reports nothing.

The cap also decides the cost of the search. A distance that may not exceed one
edit needs three diagonals of the grid and not the whole grid, so one
comparison costs the length of the name rather than its square. `propose` on
2267 sample titles of median length 97 took 376.9 seconds without the cap and
39.0 seconds with it. The compiled patterns and the caches of 0.8.2 brought the
same run to 1.3 seconds.

Two names with no letter at all never match. The ratio compares two empty
strings and scores 1.0, which reads as agreement and is the absence of any
evidence.

One substituted letter never merges two names. It is the one edit that also
carries meaning, and on the reference corpus it carried meaning every time.
`Primary B cells` merged with `Primary T cells`, `human cTEC5` with
`human mTEC5`, `Decell A549 #1` with `Recell A549 #1`, and `TSmatKO-1` with
`TSpatKO-1`. Not one of the 42 pairs that a substitution merged there was a
typing error.

A refused pair still reaches a person. `find_letter_variants` reports it next to
the pairs that one digit separates, and the two lists share the `near_misses`
field of the mapping file.

samplify drops a pair when more than two letters stand at the position that
differs, because such a position is a field of the naming scheme and not a
typing error. A 96-well plate writes `A07` through `H07`, and one study of the
corpus held 1351 wells and produced 1754 pairs without the rule.
`MAX_VARIANT_LETTERS` holds the limit, and the rule matches the one that drops a
number sitting inside a series.

The limit is measured. In the reference corpus 1002 positions hold exactly two
letters and 349 hold three or more. Every position of three or more that was
read is a plate well or a replicate letter, and the positions holding two
letters carry the real contrasts, such as `3C1` against `3N1`.

## Near misses

A near miss is a pair that samplify keeps apart and that a person must still
examine. Two searches fill the report and both write into the `near_misses`
field of the mapping file.

| Search | What it reports |
|---|---|
| `find_near_misses` | The letters are identical and exactly one number has one digit more or one digit less. |
| `find_letter_variants` | The numbers are identical and exactly one letter differs. |

The rest of this section describes the first search. The second is in the
section on the distances.

samplify reports a pair when the letters are identical and exactly
one number has one more digit or one less digit.

samplify drops a pair when the number series of the dataset contains both
numbers. A cohort with the numbers 1 to 12 is an example. The names `sample_1`
and `sample_10` differ by one inserted digit, but each number has a neighbour in
the series. Both numbers are therefore ordinary members of the series. A cohort
with the numbers 11, 111 and 112 is different, because the number 11 has no
neighbour. samplify reports the pair 11 and 111 for that reason.

Without this rule, the report holds every pair that a wide number range produces,
and the real cases are difficult to find.

samplify compares the numbers one by one. A single string of all the numbers of a
name loses the boundary between them. The name `patient11_batch2` then looks like
a typing error of `patient1_batch1`, and it is a different sample.

samplify does not report a substituted digit. The pair `patient111` and
`patient112` differs in that way, and almost every other pair in a cohort differs
in the same way. A report of every substituted digit hides the cases that matter.

The search is indexed. A reportable pair agrees on its letters and on every
number but one, so samplify builds one key from that agreement and then looks up
the one number that is allowed to differ. The shorter of two numbers that differ
by one character is the longer one with a character removed, and generating
those removals costs one lookup for each character.

The search read every pair inside one letter skeleton until version 0.4.1. A
cohort written to one convention holds every one of its names in that one
skeleton, so the cost was the square of the size of the cohort. On 6168 names
the search took 34.5 seconds, and it now takes 0.03 seconds.

samplify does not report a dropped replicate letter. The names `sample_9` and
`sample_9a` have the letter skeletons `sample` and `samplea`, so they reach
neither the same group nor the same report.

## The canonical name of a group

The canonical name is the frequency-weighted medoid of the group. The medoid is
the normalised form with the smallest total distance to every other form.
samplify counts each form one time for each row.

The frequency decides the ordinary case, where the correct spelling is also the
common spelling. The distance decides the difficult case. In `example/typos.csv`
each of the four spellings appears exactly one time, so the frequency decides
nothing. Each typing error is one edit from the correct form and two edits from
the other errors. The correct form is therefore the closest form to the rest of
the group, and samplify selects it.

A group of exactly two spellings gives the medoid no decision, because each name
is one edit from the other name. The rest of the dataset then decides. In a file
of twelve `sample_n` names, the letter sequence `sample` appears twelve times and
`sampel` appears one time. The correct spelling is therefore the spelling that
the rest of the dataset uses. Without this rule, the alphabetical order decides,
and it selects the typing error in about one half of the conditions.

samplify breaks a remaining tie in three steps.

1. It selects the more frequent form.
2. It then selects the longer form.
3. It then selects the first form in alphabetical order.

The result therefore never depends on the order of the input.

## The guards

The `apply` command refuses to run in each condition below. The list carries no
count, because a count goes stale and a list does not.

1. A group still has the status `proposed`. No person made a decision, so
   samplify has nothing to apply.
2. Two groups give one name, and no person reviewed the file. samplify put the
   names in two groups, so no person decided to merge them. A rejected group
   counts here through its original names, because rejection keeps every member
   as it was written.
3. The caller gives no data file, and the mapping file records none.
4. The caller gives no column, or the CSV holds no column with that name.
5. The header of the CSV holds the column twice. pandas renames the second one,
   so half the names would be invisible.
6. The canonical column is the source column, or the CSV already holds a column
   with the name of the canonical column. samplify writes the canonical name in
   a new column, and it overwrites no column of the input.
7. No name of the mapping appears in the column. The mapping belongs to another
   file, and applying it would change nothing and report every name as changed.
8. Two groups claim one name. One group would decide the name of that sample
   and the other would be ignored, so `final_mapping` refuses instead.
9. An output path names a file the command reads. A hard link is a second name
   for one file, so the comparison is file identity and not the text of the
   path. `Path.resolve` follows a symbolic link and knows nothing of a hard
   link. `apply` reads two files, the
   data CSV and the mapping file, and it refuses an output that points at
   either. `propose` refuses it for its mapping file and its figure, and `plot`
   for its figure. `tests/test_no_self_overwrite.py` drives every command with
   every output aimed at every file it reads, so a new option cannot be added
   without a guard. samplify promises that the input survives
   the run, and one character of a shell command separates `--output clean.csv`
   from `--output data.csv`. A log written over the input would lose the file.
10. A group holds a field that cannot decide a name. `Group.validate` holds
   every one of those checks, and both the file reader and a caller that builds
   a group in Python call it.

A command writes all of its files or none of them. Every destination is
checked before the first one is written, so an exit code of 1 means that
nothing was written. `apply` writes three files and `propose` writes two.

samplify merges the names inside one group, and that is not a collision. That
operation is the purpose of the tool.

The mapping file itself is guarded when it is read. A canonical name and a
member name must be a string that holds a character, and the `reviewed` field
must be a boolean. Both values were coerced in version 0.3.0. `str(None)` gives
the string `None`, so a group carrying a null name renamed every member of a
sample to those four characters, and `bool("false")` is True, so a file holding
the string switched off the collision guard.

## Reproducibility

The `apply` command makes no network call and holds no random state. The same
mapping file and the same input CSV give the same output CSV, byte for byte. The
script `tests/smoke_test.sh` runs `apply` two times and compares the bytes.

Every CSV is read as text. The default reader of pandas infers a type for each
column, and both of its guesses destroy a sample name. It reads `007` as the
number 7 and writes `7` back into the source column, and it reads a sample named
`NA` as a missing value and deletes the row.

The JSON log is not byte-for-byte reproducible, because it records the time of
the run. That value describes the run and not the result. The output CSV holds
no time value.

The mapping file is written to a temporary file and then replaces the target in
one operation. That file holds the decisions a person made, and a crash during a
plain write leaves a truncated document and loses that work.

The `propose` command calls the model with `temperature=0` when it calls a model.
That value reduces the variation between two runs, but it does not remove the
variation. The proposal and the application are separate commands for that
reason.

## The quality control figure

The `samplify plot` command draws four panels from a mapping file. samplify
orders the similarity matrix by group, so a block on the diagonal is one sample.
The other three panels give the spellings per sample and the counts before and
after the change. The last panel also lists the names that need a decision and
the reason for each name.

The matrix holds the value that decided each group, and that value is a
conjunction of the two rules. A pair whose digit signatures differ was never
compared, so it scores 0.0 whatever its letters look like. A pair inside one
signature scores the similarity of the two letter skeletons. The pair
`patient11_batch2` and `patient111_batch2` therefore reads white, and the last
panel gives the reason in words.

Version 0.3.0 scored the whole raw name. That measure took no part in the
decision, and it painted a pair that the identity rule had refused in the same
colour as a pair that samplify had merged.

A group can hold two names whose cell is pale. `P1_B1` and `patient1_batch1`
belong to one group, and their letter skeletons are `pb` and `patientbatch`. The
group came from the normalisation rules and not from the ratio, and the outline
around the block shows the group while the cells show the evidence.

Two more details of the figure are deliberate. The colour scale starts at the
twentieth percentile of the pairs in the data. Names that share a stem are all
similar to each other, and a fixed scale from zero gives the whole panel one
colour. samplify also limits the matrix to forty names, because more than forty
labels are not readable. A group that does not fit is left out and the rest are
drawn, and the title then gives the number of groups in the figure.

matplotlib is an optional dependency. If matplotlib is absent, `samplify plot`
prints the install command and exits with the status 1.

## The Python API

```python
from samplify import propose_csv, apply_mapping

mapping = propose_csv("samples.csv", "sample_id", method="damerau")
for group in mapping.merges():
    print(group.members, "->", group.proposed)

mapping.accept_all()
df, log = apply_mapping(mapping, output_path="clean.csv")
```

## Testing

```bash
uv run pytest                 # 527 offline tests, no key and no server
./tests/smoke_test.sh         # the command line end to end, no key
uv run pytest -m local        # the local model, needs a running ollama
uv run pytest -m live         # the hosted model, needs an OpenRouter key
```

The offline tests cover every backend, the guards, the near-miss rule, the figure
and the reproducibility claim. `tests/test_the_claims.py` quotes each promise
that `README.md` makes and tests the code against it, and it fails if one of
those sentences is reworded without the test moving too. `tests/test_properties.py` generates names rather
than naming cases, and it states the three claims a person relies on when they
accept a mapping. No group holds two digit signatures, `apply` keeps every row
and never touches the source column, and the result never depends on the order
of the input. Each property was run against a deliberately broken implementation
first, so that a property that cannot fail does not sit in the suite. The model itself is replaced, so they also cover
the request that goes to each provider and the answers that must raise an error.
The file `example/mislabel_catalogue.csv` holds its own answer in a `true_sample`
column. One test reads that column and checks that the 24 written names resolve
to the 14 real samples, so no person reads the output.

The `local` tests run the whole workflow against a real ollama server. They check
what samplify guarantees and not what the model prefers. One of them asserts that
no group mixes two different samples of the catalogue.

GitHub Actions runs the offline suite and the smoke test on Python 3.10, 3.11,
3.12 and 3.13. A second job builds the wheel, installs it and runs it from an
empty directory. That job is the reason the package sits in `src/`. The suite
imports the working copy, so it cannot see a file that the wheel leaves out, and
only a build and an install can.

## Design rules

- The numbers identify the sample, and a letter that follows a number also
  identifies it. samplify merges no name across two different identifiers.
- The model proposes and a person decides. The `--yes` option is allowed, and it
  records `"reviewed": false`.
- The names stay on the machine when the provider is `ollama`. The mapping file
  records which provider answered.
- The `apply` command never calls a model.
- samplify overwrites no column of the input. It writes the canonical name in a
  new column, and it refuses to run when a column of that name already exists.
- The input reaches the output as it was written. Every CSV is read as text, so
  no type inference alters a value that samplify does not change itself.
- A rejection keeps the original name, and it never writes a null value.
- A guard reads a value that is not valid as a refusal and never as permission.
  A name must be a string that holds a character, and `reviewed` must be a
  boolean.
- One rule table serves the model prompt and the offline backends.
- The library returns data and the CLI prints it. `src/samplify/csv_processor.py`
  writes nothing to the console.
