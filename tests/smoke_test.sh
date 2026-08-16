#!/usr/bin/env bash
# End-to-end check of the samplify command line, with no API key.
#
# Every case here uses an offline method, so the script runs in CI and on a
# laptop with no network. The model-backed methods are covered by the live
# pytest cases, which are deselected by default.
#
# Usage: ./tests/smoke_test.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

RUN="uv run samplify"
PASS=0
FAIL=0

pass() { printf '  ok    %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL + 1)); }

check() {
  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    pass "$1"
  else
    fail "$1"
    printf '        expected: %s\n        actual:   %s\n' "$2" "$3"
  fi
}

column_of() {
  # column_of <csv> <column name>, printed as one comma-separated line
  uv run python -c "
import sys, pandas as pd
print(','.join(pd.read_csv(sys.argv[1])[sys.argv[2]].astype(str)))
" "$1" "$2"
}

json_field() {
  # json_field <json file> <python expression over the parsed document 'd'>
  uv run python -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(eval(sys.argv[2]))
" "$1" "$2"
}

echo
echo "samplify smoke test"
echo "==================="

# ── 1. Delimiter, case and zero-padding, fixed by the rules alone ──────────
echo
echo "1. rules backend on example/delimiter_case.csv"

$RUN propose example/delimiter_case.csv -c sample_id -M rules \
  -o "$WORK/delim.json" --yes > /dev/null
$RUN apply "$WORK/delim.json" -o "$WORK/delim_out.csv" \
  --json-log "$WORK/delim_log.json" > /dev/null

check "three spellings merge into one sample" \
  "3" "$(json_field "$WORK/delim.json" "sum(len(g['members']) for g in d['groups'] if len(g['members']) > 1)")"
check "canonical column is written" \
  "sample1_batch1,sample1_batch1,sample1_batch1,sample2_batch1,sample2_batch2" \
  "$(column_of "$WORK/delim_out.csv" sample_id_canonical)"
check "the original column survives" \
  "S1_B1,s1-b1,s01_b01,S2_B1,s2-b2" \
  "$(column_of "$WORK/delim_out.csv" sample_id)"
check "no model was called" "None" "$(json_field "$WORK/delim.json" "d['model']")"

# ── 2. Typing errors, which need a distance ───────────────────────────────
echo
echo "2. damerau backend on example/typos.csv"

$RUN propose example/typos.csv -c sample_id -M damerau \
  -o "$WORK/typos.json" --yes > /dev/null

check "four spellings group together" \
  "4" "$(json_field "$WORK/typos.json" "max(len(g['members']) for g in d['groups'])")"
check "the correct spelling wins" \
  "patient1_batch1" \
  "$(json_field "$WORK/typos.json" "[g['final'] for g in d['groups'] if len(g['members']) > 1][0]")"

$RUN propose example/typos.csv -c sample_id -M rules \
  -o "$WORK/typos_rules.json" --yes > /dev/null
check "the rules backend alone cannot see a typo" \
  "5" "$(json_field "$WORK/typos_rules.json" "len(d['groups'])")"

# ── 3. Two patients that must stay apart ──────────────────────────────────
echo
echo "3. near-miss trap on example/near_miss_trap.csv"

$RUN propose example/near_miss_trap.csv -c sample_id -M damerau \
  -o "$WORK/trap.json" --yes > /dev/null

check "nothing merges" \
  "0" "$(json_field "$WORK/trap.json" "len([g for g in d['groups'] if len(g['members']) > 1])")"
check "the digit slips are reported" \
  "2" "$(json_field "$WORK/trap.json" "len(d['near_misses'])")"

# ── 4. A file that is already consistent ──────────────────────────────────
echo
echo "4. auto backend on example/clean_samples.csv"

$RUN propose example/clean_samples.csv -c sample_id -M auto \
  -o "$WORK/clean.json" --yes > /dev/null

check "the model is skipped entirely" "None" "$(json_field "$WORK/clean.json" "d['model']")"
check "nothing changes" \
  "0" "$(json_field "$WORK/clean.json" "d['summary']['merges'] + d['summary']['renames']")"

# ── 5. The guards ─────────────────────────────────────────────────────────
echo
echo "5. guards"

$RUN propose example/typos.csv -c sample_id -M damerau -o "$WORK/pending.json" > /dev/null
if $RUN apply "$WORK/pending.json" -o "$WORK/never.csv" > /dev/null 2>&1; then
  fail "apply refuses a mapping with no decisions"
else
  pass "apply refuses a mapping with no decisions"
fi
if [ -f "$WORK/never.csv" ]; then
  fail "a refused apply writes nothing"
else
  pass "a refused apply writes nothing"
fi

check "an unreviewed mapping says so" \
  "False" "$(json_field "$WORK/pending.json" "d['reviewed']")"

# ── 6. The same mapping gives the same output ─────────────────────────────
echo
echo "6. determinism on example/cohort_messy.csv"

$RUN propose example/cohort_messy.csv -c sample_id -M damerau \
  -o "$WORK/cohort.json" --yes > /dev/null
$RUN apply "$WORK/cohort.json" -o "$WORK/cohort_a.csv" > /dev/null
$RUN apply "$WORK/cohort.json" -o "$WORK/cohort_b.csv" > /dev/null

if cmp -s "$WORK/cohort_a.csv" "$WORK/cohort_b.csv"; then
  pass "two runs of apply give identical bytes"
else
  fail "two runs of apply give identical bytes"
fi

check "the two patient numbers stay apart" \
  "1" "$(json_field "$WORK/cohort.json" "len(d['near_misses'])")"

# ── Result ────────────────────────────────────────────────────────────────
echo
echo "==================="
printf '%s passed, %s failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
