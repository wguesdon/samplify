# Example data and test cases

These six files are the worked examples for samplify and the inputs that
`tests/smoke_test.sh` runs. Each file isolates one failure mode, so you can see
which backend finds it and which backend does not. Every command below runs
offline and needs no API key.

## `clean_samples.csv`, the file that needs no work

The file holds three samples, two timepoints and one name convention. The offline
pass finds no inconsistency and forms no cluster, so the `auto` backend makes no
model call.

```bash
uv run samplify propose example/clean_samples.csv -c sample_id -M auto -o /tmp/clean.json
```

The result is 3 groups. samplify changes no name, and the mapping file records
`"model": null`.

## `delimiter_case.csv`, the character-level problem

The same sample appears as `S1_B1`, as `s1-b1` and as `s01_b01`. The delimiter,
the letter case and the zero-padding all differ. The `rules` backend repairs the
three names alone, because they normalise to one string.

```bash
uv run samplify propose example/delimiter_case.csv -c sample_id -M rules -o /tmp/delim.json
```

The result is 3 groups. samplify merges three names into `sample1_batch1`, and it
changes two more names.

## `typos.csv`, the problem that the rules do not find

The names `patietn1_batch1`, `pateint1_batch1` and `patient1_bacth1` are three
typing errors of `patient1_batch1`. No normalisation rule groups them, because
the characters are wrong. A distance backend groups them.

```bash
uv run samplify propose example/typos.csv -c sample_id -M rules -o /tmp/t1.json      # 5 groups
uv run samplify propose example/typos.csv -c sample_id -M damerau -o /tmp/t2.json    # 2 groups
```

samplify selects the correct spelling as the canonical name. Each of the four
names appears one time, so the frequency decides nothing. The canonical name is
the name closest to all the other names. Each typing error is one edit from the
correct form and two edits from the other errors.

## `near_miss_trap.csv`, the names that must stay apart

The names `patient11_batch1`, `patient111_batch1` and `patient112_batch1` are
three patients. Their letters are identical, and their names differ by one or two
characters. A distance measure that ignores the numbers merges them.

```bash
uv run samplify propose example/near_miss_trap.csv -c sample_id -M damerau -o /tmp/trap.json
```

samplify merges no name, and it reports two near misses. The pair `patient11` and
`patient111` has one more digit, so samplify reports it. The pair `patient111`
and `patient112` has a substituted digit, so samplify does not report it. Two
consecutive patient numbers usually differ in that way.

## `cohort_messy.csv`, all the faults in one file

The file holds twenty-two rows from three sites. It contains the delimiter
variants and the letter case variants. It also contains two typing errors, the
abbreviations `ctrl`, `ko`, `wt`, `rep` and `b`, and one near-miss pair. Use this
file for the full three-step workflow.

```bash
uv run samplify propose example/cohort_messy.csv -c sample_id -M damerau -o /tmp/cohort.json
uv run samplify review /tmp/cohort.json
uv run samplify apply /tmp/cohort.json -o /tmp/clean.csv --csv-log /tmp/changes.csv
```

The result is 8 groups, and 6 of the groups merge two or more names. samplify
also reports one near-miss pair. The offline pass resolves the whole file, so
samplify makes no model call. To compare the two paths, run the same file with
`-M auto` and a key in `.env`.

## `mislabel_catalogue.csv`, one row per fault

This file is the reference set. Each row names its own fault, and the
`true_sample` column records the correct sample for that name. A test therefore
checks the answer, and no person reads the output.

```bash
uv run samplify propose example/mislabel_catalogue.csv -c sample_id -M damerau \
  -o /tmp/cat.json --plot /tmp/cat_qc.png
```

Twenty-four written names cover fourteen real samples. samplify must find ten
faults, and it must keep three pairs apart.

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

The quality control figure for this file is in
`docs/img/qc_mislabel_catalogue.png`, and the README shows it.
