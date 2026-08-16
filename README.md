# samplify

Find the sample names in your data that are one sample spelled several ways, and
confirm each group before anything is renamed.

```
S1_B1            ─┐
s1-b1            ─┤
s01_b01          ─┼─►  patient1_batch1     you confirm this group
patient1_batch1  ─┤
patietn1_batch1  ─┘

patient11_batch1  ──►  reported, never merged
patient111_batch1 ──►  one of these is a slipped keystroke, or they are two patients
```

Inconsistent sample identifiers break a join without an error message. The row
count drops, the counts stop matching, and you lose an afternoon before you find
the cause. samplify finds the candidate groups, shows you the evidence, and
applies only the decisions that you make.

## What it does

samplify clusters the names in a CSV column and proposes one canonical name for
each cluster. Four backends form the clusters, and three of them make no network
call at all.

| Backend | What it finds | Model call |
|---|---|---|
| `rules` | Delimiter, case, zero-padding and abbreviation differences | none |
| `hamming` | The same, plus a substituted character in a name of equal length | none |
| `levenshtein` | The same, plus an inserted or deleted character | none |
| `damerau` | The same, plus two swapped characters, which is the common typing error | none |
| `llm` | Anything the rules and the distances miss | one call, all names |
| `auto` | Clusters offline first, then sends one name per cluster to the model | one call, few names |

The default is `auto`. On the worked example in `example/cohort_messy.csv`, the
offline pass resolves all 22 names into 8 groups and the model is never called.

## The quality control figure

```bash
uv run samplify propose example/cohort_messy.csv -c sample_id -M damerau \
  -o mapping.json --plot qc.png
```

![Quality control figure for example/cohort_messy.csv](docs/img/qc_cohort_messy.png)

Four panels answer the question a person asks before they review anything. The
similarity matrix on the left is ordered by group, so a block on the diagonal is
one sample and the outline shows what samplify wants to merge. The three panels
on the right give the spellings found per sample, the counts before and after,
and the list of names that need a decision, with the reason for each. The pair
in red was not merged.

The figure is drawn from the mapping file, so `samplify plot mapping.json -o
qc.png` redraws it at any point, including after the review.

## The faults it catches

`example/mislabel_catalogue.csv` holds one row per naming fault and carries its
own answer in a `true_sample` column. The test suite reads that column and
checks that samplify recovers the 14 real samples from the 24 written names.

| Fault | Reference | As written | Caught by |
|---|---|---|---|
| Delimiter dropped | `sample_1` | `sample1` | `rules` |
| Delimiter changed | `sample_1` | `sample-1` | `rules` |
| Capital letter | `sample_1` | `Sample_1` | `rules` |
| All capitals | `sample_4` | `SAMPLE_4` | `rules` |
| Zero padded number | `sample_3` | `sample_03` | `rules` |
| Doubled delimiter | `sample_6` | `sample__6` | `rules` |
| Surrounding space | `sample_7` | `" sample_7 "` | `rules` |
| Abbreviated word | `sample_8` | `s_8` | `rules` |
| One letter dropped | `sample_2` | `smple_2` | `damerau` |
| Two letters swapped | `sample_5` | `sampel_5` | `damerau` |

Three pairs in the same file must not merge, and do not.

| Pair | Why they stay apart |
|---|---|
| `sample_9a` and `sample_9b` | The letter after the number identifies the replicate |
| `sample_11` and `sample_12` | Two different numbers |
| `sample_10` and `sample_100` | Two different numbers, and reported as a pair to check |

## Numbers are the identity of a sample

`p111` and `p112` sit one edit apart, and they are two different patients.
Merging them loses a row and reports nothing. Every backend therefore compares
two names only when their numbers match exactly, and the typo tolerance applies
to the letters alone. The model is told the same rule, and a merge that the
model proposes across two different numbers is refused before it reaches the
mapping file.

The pairs that this rule keeps apart are still worth a look, so samplify reports
them. A pair is reported when the letters agree and one number gained or lost a
digit, as in `patient11` against `patient111`. A substituted digit is not
reported, because `patient111` and `patient112` differ that way and so does
almost every other pair of samples in a cohort.

## Install

The package is not on PyPI yet. Install it from git.

```bash
uv add git+https://github.com/wguesdon/samplify
```

To work on the repository itself, clone it and sync the environment.

```bash
git clone https://github.com/wguesdon/samplify.git
cd samplify
uv sync
```

The offline backends need nothing else. To draw the quality control figure,
install the `plot` extra, which adds matplotlib.

```bash
uv add "samplify[plot]"
```

For `llm` and `auto`, create a `.env` file with an
[OpenRouter](https://openrouter.ai) key.

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

## The three steps

samplify separates the proposal, the decision and the change. Each step writes a
file, so the record shows which of them a person checked.

### 1. Propose

```bash
uv run samplify propose example/cohort_messy.csv --column sample_id -o mapping.json
```

This prints the diagnosis, the near misses and the candidate groups, then writes
`mapping.json`. Every group starts with the status `proposed`.

### 2. Review

```bash
uv run samplify review mapping.json
```

This shows one group at a time and asks for a decision. Accept the group, reject
it, or type a different canonical name. The merges come first, because they
carry the risk. The command needs a terminal.

### 3. Apply

```bash
uv run samplify apply mapping.json --output clean.csv --csv-log changes.csv
```

This never calls a model. The same mapping file and the same input give the same
output on any machine and on any day. The original column is not touched. A new
column named `sample_id_canonical` holds the result, so every decision stays
reversible.

`apply` refuses to run while any group is still `proposed`. It also refuses when
two groups produce one canonical name in a mapping that no person reviewed,
because that is a merge nobody decided.

### Without a person

A pipeline can accept every proposal at the propose step.

```bash
uv run samplify propose data.csv -c sample_id -o mapping.json --yes
uv run samplify apply mapping.json -o clean.csv
```

The mapping file then records `"reviewed": false`, and `apply` says so. The
record stays honest about what was checked.

## A quick look at a few names

```bash
uv run samplify names "S1_B1" "s1-b1" "s01_b01" "patietn1_batch1"
```

This writes nothing. Use it to see what a backend does before you point it at a
file.

## The Python API

```python
from samplify import propose_csv, apply_mapping

mapping = propose_csv("samples.csv", "sample_id", method="damerau")
for group in mapping.merges():
    print(group.members, "->", group.proposed)

mapping.accept_all()
df, log = apply_mapping(mapping, output_path="clean.csv")
```

## Tests

```bash
uv run pytest -m "not live"   # 131 unit tests, no API key
./tests/smoke_test.sh         # the command line end to end, no API key
uv run pytest -m live         # the model-backed paths, needs a key
```

`example/README.md` explains what each test file contains and gives the command
that exercises it.

## Documentation

- [docs/how_it_works.md](docs/how_it_works.md) explains the mapping file, the
  matching, and the design rules.
- [example/README.md](example/README.md) is the worked example set.
- [CHANGELOG.md](CHANGELOG.md) records what changed in each version.

## License

MIT. See [LICENSE](LICENSE).
