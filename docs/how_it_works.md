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
`apply` reads. It holds one group for each candidate sample.

```json
{
  "schema_version": 1,
  "method": "damerau",
  "model": null,
  "provider": null,
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

## The six backends

| Backend | What it finds | Model call |
|---|---|---|
| `rules` | Delimiter, letter case, zero-padding and abbreviation differences | None |
| `hamming` | The same, plus a substituted character in a name of equal length | None |
| `levenshtein` | The same, plus an inserted character or a deleted character | None |
| `damerau` | The same, plus two adjacent characters in the wrong order | None |
| `llm` | The names that the rules and the distances do not group | One call, all the names |
| `auto` | Clusters offline first, then sends one name for each cluster | One call, few names |

### rules

The `rules` backend applies the character rules in `samplify/rules.py`. It does
five operations on each name.

1. It changes every capital letter to a small letter, and it splits the name at
   each delimiter.
2. It joins a number to the word in front of it, so `s_8` and `s8` reach the
   abbreviation table as one token.
3. It expands each abbreviation and removes the zero-padding from each number.
4. It joins the tokens with an underscore.
5. It removes each character outside the canonical set.

samplify puts two names in the same group when the two names normalise to the
same string.

samplify defines the abbreviation table one time. The `rules` backend, the CSV
diagnosis and the model prompt all read the same table. Version 0.1.0 held the
table two times, and the two copies were already different.

The abbreviation `t` is not an alias for treatment. A token such as `t1` is a
timepoint at least as often as it is a treatment. A token that keeps its short
form is easy to repair later. A token with the wrong expansion merges two
samples, and the row count drops with no error.

### hamming

Hamming distance counts the positions where two strings of equal length differ.
It is the correct measure for a substituted character. It has no value for two
names of different lengths, and `hamming_distance` then returns `None`. A number
in that condition misleads the caller.

### levenshtein

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

samplify checks each proposal from the model. If the model gives one canonical
name to two representatives with different numbers, samplify keeps the two names
apart. Each of the two then keeps its own canonical name. The model advises, and
the identity rule decides.

### The two providers

Two services answer the request of the `llm` and `auto` backends.

| Provider | Server | Key | Default model |
|---|---|---|---|
| `openrouter` | The OpenRouter API | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` |
| `ollama` | `http://localhost:11434` | None | `qwen3.5:9b` |

The option `--provider ollama` runs the model on the local machine, so the names
never leave it. `OLLAMA_HOST` and `--base-url` point at another machine, and
`OLLAMA_MODEL` and `--model` choose the model.

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

The rule has two effects. It keeps `p111` and `p112` in separate groups at every
threshold. It also reduces the number of comparisons, because samplify measures
only the names that share a signature.

## When a distance is enough on its own

A ratio threshold does not find a typing error in a short name. The pair `smple`
and `sample` scores 0.833, which is below every usual threshold, and the fault is
one dropped letter.

One inserted letter, one deleted letter or one exchange of two letters therefore
matches at every ratio. One keystroke makes each of those three faults.

One substituted letter does not match at every ratio, and it must be above the
threshold. A substitution is the one edit that also changes the meaning. The
names `batch_a1` and `batch_b1` differ by one substitution, and they are two
different batches.

## Near misses

A near miss is a pair that the identity rule keeps apart and that a person must
still examine. samplify reports a pair when the letters are identical and exactly
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

The `apply` command refuses to run in four conditions.

1. A group still has the status `proposed`. No person made a decision, so
   samplify has nothing to apply.
2. Two groups give one canonical name, and no person reviewed the file. samplify
   put the names in two groups, so no person decided to merge them.
3. The caller gives no data file, and the mapping file records none.
4. The caller gives no column, or the CSV holds no column with that name.

samplify merges the names inside one group, and that is not a collision. That
operation is the purpose of the tool.

## Reproducibility

The `apply` command makes no network call, writes no time value into its output
and holds no random state. The same mapping file and the same input CSV give the
same output CSV. The script `tests/smoke_test.sh` runs `apply` two times and
compares the bytes.

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

Two details of the figure are deliberate. The colour scale starts at the
twentieth percentile of the pairs in the data. Names that share a stem are all
similar to each other, and a fixed scale from zero gives the whole panel one
colour. samplify also limits the matrix to forty names, because more than forty
labels are not readable. The title then gives the number of groups in the figure.

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
uv run pytest                 # 160 offline tests, no key and no server
./tests/smoke_test.sh         # the command line end to end, no key
uv run pytest -m local        # the local model, needs a running ollama
uv run pytest -m live         # the hosted model, needs an OpenRouter key
```

The offline tests cover every backend, the guards, the near-miss rule, the figure
and the reproducibility claim. The model itself is replaced, so they also cover
the request that goes to each provider and the answers that must raise an error.
The file `example/mislabel_catalogue.csv` holds its own answer in a `true_sample`
column. One test reads that column and checks that the 24 written names resolve
to the 14 real samples, so no person reads the output.

The `local` tests run the whole workflow against a real ollama server. They check
what samplify guarantees and not what the model prefers. One of them asserts that
no group mixes two different samples of the catalogue.

## Design rules

- The numbers identify the sample, and a letter that follows a number also
  identifies it. samplify merges no name across two different identifiers.
- The model proposes and a person decides. The `--yes` option is allowed, and it
  records `"reviewed": false`.
- The names stay on the machine when the provider is `ollama`. The mapping file
  records which provider answered.
- The `apply` command never calls a model.
- samplify never overwrites the original column, and it writes the canonical name
  in a new column.
- A rejection keeps the original name, and it never writes a null value.
- One rule table serves the model prompt and the offline backends.
- The library returns data and the CLI prints it. `samplify/csv_processor.py`
  writes nothing to the console.
