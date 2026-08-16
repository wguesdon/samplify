# Example data and test cases

These six files are the worked examples in the README and the inputs that
`tests/smoke_test.sh` runs. Each file isolates one failure mode, so you can see
which backend finds it and which backend cannot. Every command below runs
offline and needs no API key.

## `clean_samples.csv`, the file that needs no work

Three samples, two timepoints, one naming convention. The heuristics find no
inconsistency and no cluster forms, so the `auto` backend skips the model call
completely.

```bash
uv run samplify propose example/clean_samples.csv -c sample_id -M auto -o /tmp/clean.json
```

Expect 3 groups, all unchanged, and `"model": null` in the mapping file.

## `delimiter_case.csv`, the character-level problem

The same sample appears as `S1_B1`, as `s1-b1` and as `s01_b01`. The delimiter,
the case and the zero-padding all differ. The `rules` backend fixes this on its
own, because the three names normalise to one string.

```bash
uv run samplify propose example/delimiter_case.csv -c sample_id -M rules -o /tmp/delim.json
```

Expect one merge of three names into `sample1_batch1`, and two renames.

## `typos.csv`, the problem the rules cannot see

`patietn1_batch1`, `pateint1_batch1` and `patient1_bacth1` are three typing
errors on `patient1_batch1`. No normalisation rule joins them, because the
characters themselves are wrong. A distance backend joins them.

```bash
uv run samplify propose example/typos.csv -c sample_id -M rules -o /tmp/t1.json      # 5 groups
uv run samplify propose example/typos.csv -c sample_id -M damerau -o /tmp/t2.json    # 2 groups
```

The correct spelling wins the group. Every one of the four names appears once, so
frequency cannot decide it. The winner is the name closest to all the others,
and each typo sits one edit from the correct form and two edits from the other
typos.

## `near_miss_trap.csv`, the merge that must not happen

`patient11_batch1`, `patient111_batch1` and `patient112_batch1` are three
patients. Their letters are identical and their names are one or two characters
apart, so any distance measure that ignores the numbers will merge them.

```bash
uv run samplify propose example/near_miss_trap.csv -c sample_id -M damerau -o /tmp/trap.json
```

Expect no merge at all, and two reported near misses. `patient11` against
`patient111` is a gained digit and is reported. `patient111` against
`patient112` is a substituted digit and is not reported, because two consecutive
patient numbers differ that way as a matter of course.

## `cohort_messy.csv`, all of it at once

Twenty-two rows from three sites. It contains the delimiter and case variants,
two typos, the abbreviations `ctrl`, `ko`, `wt`, `rep` and `b`, and one near-miss
pair. This is the file to use when you try the full three-step workflow.

```bash
uv run samplify propose example/cohort_messy.csv -c sample_id -M damerau -o /tmp/cohort.json
uv run samplify review /tmp/cohort.json
uv run samplify apply /tmp/cohort.json -o /tmp/clean.csv --csv-log /tmp/changes.csv
```

Expect 8 groups, of which 6 are merges, and one near-miss pair. The offline pass
resolves the whole file, so the model is never called. Run the same file with
`-M auto` and a key in `.env` to compare the two paths.

## `mislabel_catalogue.csv`, one row per fault

This file is the reference set. Each row names the fault it carries, and the
`true_sample` column records which sample the name really belongs to, so a test
can check the answer rather than a person reading the output.

```bash
uv run samplify propose example/mislabel_catalogue.csv -c sample_id -M damerau \
  -o /tmp/cat.json --plot /tmp/cat_qc.png
```

Twenty-four written names cover fourteen real samples. Ten faults must be
caught, and three pairs must stay apart.

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

| Pair | Expected result |
|---|---|
| `sample_9a` and `sample_9b` | Two samples. The letter after the number is part of the identity. |
| `sample_11` and `sample_12` | Two samples. |
| `sample_10` and `sample_100` | Two samples, and the only pair reported for a person to check. |

The QC figure for this file is in `docs/img/qc_mislabel_catalogue.png`.
