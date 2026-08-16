# How samplify works

## The idea

A sample name carries two kinds of information. The letters describe the sample,
and the numbers identify it. `patient111_batch2` says patient, batch, one hundred
and eleven, two. Every rule in samplify follows from that split.

A difference in the letters is usually a difference in style or a typing error,
and it is safe to repair. A difference in the numbers is a difference in
identity, and it is never safe to repair automatically. samplify therefore
normalises and clusters the letters, and it treats the numbers as fixed.

## The workflow

The work happens in three commands, and each one writes a file.

| Step | Command | Model call | Output |
|---|---|---|---|
| Propose | `samplify propose` | At most one | `mapping.json`, every group `proposed` |
| Review | `samplify review` | None | The same file, every group decided |
| Apply | `samplify apply` | None | The output CSV and the change log |

The separation is the point. The proposal is a guess that a model or a distance
measure made. The decision belongs to a person. The change is a mechanical step
that anyone can repeat and check. Joining the three into one command would hide
which of them a person looked at.

## The mapping file

The mapping file is the artifact that a person reviews, that git stores and that
`apply` consumes. It holds one group for each candidate sample.

```json
{
  "schema_version": 1,
  "method": "damerau",
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

A group carries four statuses. `proposed` means that no person has decided yet.
`accepted` applies the proposed name to every member. `edited` applies a name
that a person typed. `rejected` leaves every member with its own original name,
so a rejection never deletes a row and never writes a null value.

The file is text, it is small, and it is stable between runs. Commit it beside
the analysis and the cleanup step becomes visible in a diff.

## The four backends

### rules

The `rules` backend applies the character-level rules in `samplify/rules.py`. It
lower-cases the name, replaces every delimiter with an underscore, removes
zero-padding, drops any character outside the canonical set, and expands the
abbreviations. Two names join a group when they normalise to the same string.

The abbreviation table is defined once and read by three consumers: this
backend, the CSV diagnosis, and the model prompt. Version 0.1.0 held the table
twice and the two copies had already drifted.

`t` is not an alias for treatment. A token such as `t1` reads as a timepoint at
least as often as it reads as a treatment. An unexpanded token is easy to repair
later. A token expanded to the wrong term merges two samples, and the row count
drops with no error.

### hamming

Hamming distance counts the positions at which two strings of equal length
differ. It is the right measure for a substituted character and it is undefined
for names of different lengths. `hamming_distance` returns `None` in that case
rather than a number that would mislead the caller.

### levenshtein

Levenshtein distance counts insertions, deletions and substitutions. It handles
names of different lengths, which Hamming distance cannot.

### damerau

Damerau-Levenshtein distance adds the swap of two adjacent characters, and it is
the default. A swap is one slip of the fingers, and plain Levenshtein charges
two edits for it. That difference decides real cases. `patient` against
`patietn` scores 0.833 under Levenshtein and 0.917 under Damerau-Levenshtein, so
a threshold of 0.85 rejects a genuine typo under the first measure and accepts
it under the second.

### llm and auto

The `llm` backend sends every unique name to the model in one request. The
`auto` backend clusters offline first and then sends one representative name per
cluster, which makes the request much smaller. `auto` skips the model entirely
when the heuristics find no inconsistency and no cluster forms.

A merge that the model proposes is checked before it is accepted. Two
representatives that the model gives one canonical name are kept apart when
their numbers differ. The model advises, and the identity rule still holds.

## Blocking and the identity rule

Two names are compared only when their digit signature matches exactly. The
signature is the sequence of numbers in the name with the zero-padding removed,
so `p111-batch03` has the signature `("111", "3")`.

A letter attached to a number belongs to the signature as well, because a cohort
labels its replicates `sample9a` and `sample9b`. Those two names differ by one
substituted letter, and without this rule a distance backend joins them. The
signature of `sample_9a` is `("9a",)` and the signature of `sample_9b` is
`("9b",)`, so the pair is never compared.

This rule does two things at once. It keeps `p111` and `p112` in separate groups
whatever the threshold is, and it cuts the number of comparisons, because only
the names that share a signature are ever measured against each other.

## When a distance is enough on its own

A ratio threshold cannot see a typo in a short name. `smple` against `sample`
scores 0.833, below any sensible cut, and it is plainly a dropped letter.

A single inserted, deleted or swapped letter therefore matches whatever the
ratio says. Those are the shapes a slipped keystroke makes.

A single substituted letter does not get that treatment and must clear the ratio
instead. A substitution is the one edit that also carries meaning, which is what
`batch_a1` and `batch_b1` are made of.

## Near misses

A near miss is a pair that the identity rule keeps apart and that a person
should still look at. samplify reports a pair when the letters are identical and
exactly one number gained or lost a digit.

A pair is dropped when both numbers sit inside the numbering series the dataset
already uses. In a cohort numbered 1 to 12, `sample_1` and `sample_10` differ by
an inserted digit, and both have a neighbour in the series, so both are ordinary
members of it. In a cohort holding 11, 111 and 112, the number 11 has no
neighbour, so the pair 11 and 111 is worth a look. Without this rule the report
fills with every pair that a wide numbering range produces, and the real cases
are buried.

The comparison runs number by number. Joining the numbers of a name into one
string would lose the boundary between them, and `patient11_batch2` would then
look like a slip of `patient1_batch1`, which it is not.

A substituted digit is deliberately not reported. `patient111` and `patient112`
differ that way, and so does almost every other pair of samples in a cohort, so
reporting it would bury the cases that matter.

## The canonical name of a group

The canonical name is the frequency-weighted medoid of the group, which is the
normalised form with the smallest total distance to every other form, counted
once per row.

Frequency settles the ordinary case, where the correct spelling is simply the
common one. The distance settles the hard case. In `example/typos.csv` every one
of the four spellings appears exactly once, so frequency decides nothing. Each
typo sits one edit from the correct form and two edits from the other typos, so
the correct form is the closest to the rest of the group and it wins.

A group of exactly two spellings gives the medoid nothing to decide, because
each name is one edit from the other. The rest of the dataset breaks that tie.
In a file of twelve `sample_n` names, the letter skeleton `sample` appears
twelve times and `sampel` appears once, so the correct spelling is the one the
dataset already agrees on. Without this rule the tie falls to alphabetical
order, which picks the typo about half the time.

Ties then break towards the more frequent form, then the longer one, then the
alphabetically first, so the result never depends on the order of the input.

## The guards

`apply` refuses to run in three conditions.

1. A group still has the status `proposed`. Nobody decided, so there is nothing
   to apply.
2. Two groups produce one canonical name and no person reviewed the file. The
   tool itself considered the two groups distinct, so joining them is a merge
   that nobody decided.
3. The column is missing from the CSV, or no column was given and the mapping
   file records none.

A merge inside one group is not a collision. That is the purpose of the tool.

## Reproducibility

`apply` makes no network call, reads no clock into its output and holds no
random state. The same mapping file and the same input CSV give the same output
CSV. `tests/smoke_test.sh` runs `apply` twice and compares the bytes.

`propose` calls the model with `temperature=0` when a model is used at all. That
reduces the variation between runs and it does not remove it, which is the
reason the proposal and the application are separate commands.

## The quality control figure

`samplify plot` draws four panels from a mapping file. The similarity matrix is
ordered by group, so a block on the diagonal is one sample. The other three
panels give the spellings found per sample, the counts before and after, and the
list of names that need a decision with the reason for each.

Two details of the drawing are deliberate. The colour scale starts at the
twentieth percentile of the pairs actually present, because names that share a
stem are all similar to each other and a fixed scale from zero paints the whole
panel one colour. The matrix is trimmed to forty names, because past that the
labels stop being readable, and the title then says how many groups are shown.

matplotlib is an optional dependency. `samplify plot` explains how to install it
rather than failing with an import error.

## Testing

```bash
uv run pytest -m "not live"   # 131 unit tests, no API key
./tests/smoke_test.sh         # the command line end to end, no API key
uv run pytest -m live         # the model-backed paths, needs a key
```

The offline tests cover every backend except `llm`, both guards, the near-miss
rule, the figure and the determinism claim. `example/mislabel_catalogue.csv`
carries its own answer in a `true_sample` column, so one test checks that the 24
written names resolve to the 14 real samples rather than a person reading the
output. The live tests cover the model call.

## Design rules

- The numbers identify the sample, and so does a letter attached to a number.
  Nothing merges across different identifiers.
- The model proposes and a person decides. `--yes` is allowed and it records
  `"reviewed": false`.
- `apply` never calls a model.
- The original column is never overwritten. The canonical name goes in a new
  column.
- A rejection leaves the original name in place. It never writes a null value.
- One rule table, read by the prompt and by the offline backends.
- The library returns data and the CLI prints it. `samplify/csv_processor.py`
  writes nothing to the console.
