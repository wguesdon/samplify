# samplify

**LLM-powered harmonization of inconsistent bioinformatics sample names.**

Stop your pipeline from breaking because one batch called it `sample_1_batch_1`
and another called it `sample1-b2`.

```
sample_1_batch_1   ─┐
sample1_batch2     ─┼─►  sample1_batch1
sample-1-b3        ─┘    sample1_batch2
                          sample1_batch3
```

`samplify` uses a large language model (via [OpenRouter](https://openrouter.ai))
to infer the canonical naming pattern across your files and return a mapping
table — no hand-rolled regex, no manual curation.

---

## Why this exists

Inconsistent sample IDs are one of the most common causes of silent failures in
bioinformatics pipelines. The same sample appears as `ctrl_rep1_b1`,
`control_replicate2_batch1`, and `ctrl-r3-batch1` across three collaborators'
files. Regex fixes are brittle. Manual curation doesn't scale.

LLMs handle this well because it's a **pattern inference** problem, not a
database lookup. Give the model a set of names, it infers what they mean and
returns a consistent canonical form.

---

## Install

```bash
pip install samplify
# or with uv (recommended)
uv add samplify
```

## Setup

Create a `.env` file in your project root:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini   # optional, this is the default
```

Get a free API key at [openrouter.ai](https://openrouter.ai).

---

## Usage

### CLI

```bash
samplify "sample_1_batch_1" "sample1_batch2" "sample-1-b3"
samplify --file my_samples.txt
samplify --file my_samples.txt --json > mapping.json
samplify --model anthropic/claude-3-5-haiku "sample_1_b1" "sample1_batch2"
```

### Python API

```python
from samplify import harmonize

names = ["sample_1_batch_1", "sample1_batch2", "sample-1-b3"]
result = harmonize(names)

print(result["canonical_pattern"])  # → "sample{n}_batch{m}"
print(result["mapping"])
# → {"sample_1_batch_1": "sample1_batch1", "sample-1-b3": "sample1_batch3", ...}

# Apply to a pandas DataFrame
df["sample_id"] = df["sample_id"].map(result["mapping"])
```

---

## What it handles

| Problem | Example |
|---|---|
| Delimiter variation | `sample-1-batch-1` vs `sample_1_batch_1` |
| Batch abbreviation | `b3` → `batch3` |
| Replicate abbreviation | `rep2`, `r2` → `replicate2` |
| Control/condition | `ctrl` → `control`, `ko` → `knockout` |
| Zero-padding | `sample01` vs `sample1` |
| Mixed case | `Sample_1` vs `sample_1` |

---

## Running tests

```bash
uv run pytest -m "not live"   # unit tests, no API key needed
uv run pytest -m live          # live API tests
```

---

## License

MIT
