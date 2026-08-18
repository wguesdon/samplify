# LLM tools for bioinformatics metadata, 2025 to 2026

## The problem

An inconsistent sample name, gene identifier or pathway label breaks a
bioinformatics pipeline. One sample can arrive under three names.

```
sample_1_batch_1   sample1_batch2   sample-1-b3
```

A gene name and a pathway annotation change between one database and another,
between one species and another, and between one laboratory and another. A
regular expression repairs one dataset and fails on the next one. A tool that
uses a large language model is more general, and it is more general again when
a biological ontology grounds the answer.

## How to read this list

Every URL and every publication detail below was verified. Several tools were
described inaccurately in early community posts, and each section names the
correction.

| Tool | Focus | Open source | Model approach | Best for |
|---|---|---|---|---|
| Pre-Meta | Metadata harmonisation | Yes, on GitHub | Retrieval-augmented generation with ontologies, model agnostic | Ontology-grounded name mapping |
| Netrias Harmonization | Metadata harmonisation | Partly, on Hugging Face | GPT-2 Large, fine-tuned on noisy biological data | A typo or an abbreviation of a known term |
| PromptBio | Whole omics analysis | No, commercial software as a service | Several agents, GPT-4 class | Whole pipeline automation |
| scPilot | scRNA-seq analysis | Yes, on GitHub | Agentic reasoning | Cell annotation and trajectories |
| CellAtria | scRNA-seq metadata | Yes, on GitHub | Agentic | scRNA-seq name standardisation |

## 1. Pre-Meta

Pre-Meta harmonises metadata with a retrieval-augmented generation pipeline,
and a biological ontology grounds each answer. The pipeline retrieves the
ontology context before it prompts the model, so the model has the prior
knowledge that an ambiguous abbreviation needs. It maps an abbreviated or a
non-standard metadata field to a structured format such as BioSample or GEO.
It resolves `Mse_Lvr_01` to `Mus musculus liver sample 1`.

| Item | Value |
|---|---|
| Publication | [*Bioinformatics*, Oxford Academic (October 2025)](https://academic.oup.com/bioinformatics/article/41/10/btaf519/8257680) |
| DOI | `10.1093/bioinformatics/btaf519` |
| Code | [https://github.com/SINTEF-SE/LLMDap](https://github.com/SINTEF-SE/LLMDap) |

The repository does not carry the name Pre-Meta. SINTEF releases it under the
internal project name `LLMDap`. There is no release on Hugging Face.

## 2. Netrias Harmonization

Netrias fine-tunes GPT-2 Large models on biological metadata that holds noise.
The training data simulates the typing errors, the abbreviations and the
changes of word order that a researcher produces. The result of that work is
the finding that a small model fine-tuned on noisy domain data beats zero-shot
GPT-4 at this task. Netrias reports 96% in-dictionary accuracy.

Use it when a name is a typing error or an abbreviation of a term that a
dictionary already holds. Cancer metadata and microbial sample names are two
examples.

| Item | Value |
|---|---|
| Publication | [*Bioinformatics Advances*, Oxford Academic (2025)](https://academic.oup.com/bioinformaticsadvances/article/5/1/vbaf241/8269464) |
| DOI | `10.1093/bioadv/vbaf241` |
| Preprint | [bioRxiv, January 2025](https://www.biorxiv.org/content/10.1101/2025.01.15.633281v1) |
| Preprint DOI | `10.1101/2025.01.15.633281` |
| Models and datasets | [https://huggingface.co/netrias](https://huggingface.co/netrias) |
| Organisation | [https://github.com/netrias](https://github.com/netrias) |

No repository holds the code of the paper on its own. Hugging Face hosts the
models and the datasets. The GitHub organisation holds related tools, which are
`bdf_harmonization` and `bdi-kit`.

## 3. PromptBio

PromptBio is a platform of several agents, and it runs in the cloud. It
automates a whole omics workflow, and it holds a DataAgent that reads the data
and prepares it. Use it to automate a whole analysis pipeline, such as a
statistical analysis or a machine learning task on omics data.

The platform does some of the work of reading and preparing data. Metadata
harmonisation is not its main function.

| Item | Value |
|---|---|
| Preprint | [bioRxiv, July 2025](https://www.biorxiv.org/content/10.1101/2025.07.05.663295v1) |
| DOI | `10.1101/2025.07.05.663295` |
| Platform | [https://promptbio.ai](https://promptbio.ai) |

PromptBio is often called a naming reconciliation tool, and that description
overstates what it does. It is a general platform for omics analysis. It is
commercial software as a service, and it has no public repository.

## 4. scPilot

scPilot is an agentic reasoning framework for single-cell RNA-seq analysis. It
does three tasks. It annotates a cell type, it reconstructs a developmental
trajectory, and it finds the target of a transcription factor.

| Item | Value |
|---|---|
| Preprint | [arXiv:2602.11609 (February 2026)](https://arxiv.org/abs/2602.11609) |
| Code | [https://github.com/maitrix-org/scPilot](https://github.com/maitrix-org/scPilot) |
| Paper page | [https://huggingface.co/papers/2602.11609](https://huggingface.co/papers/2602.11609) |

scPilot is not a tool for metadata standardisation, and it is not a tool for
naming harmonisation. It normalises no sample name and no metadata field, and a
person configures each dataset by hand in an Excel file. It is a framework for
analysis reasoning and not a tool that repairs data.

## 5. CellAtria

CellAtria is an agentic framework, and it standardises the metadata of a
single-cell RNA-seq study. It is the tool that matches the description that
people often attach to scPilot.

| Item | Value |
|---|---|
| Publication | [*npj Artificial Intelligence*, January 2026](https://www.nature.com/articles/s44387-025-00064-0) |
| Code | [https://github.com/AstraZeneca/cellatria](https://github.com/AstraZeneca/cellatria) |
| Author | AstraZeneca |

## Cross-batch sample ID normalisation

This is the specific problem that this repository addresses.

```
sample1-batch1   sample1_batch2   sample1-b3
```

A search in February 2026 found no tool built for that problem. The field holds
two kinds of solution, and each one solves a different problem.

| Kind | Examples | What it works on |
|---|---|---|
| Batch effect correction | ComBat, Harmony, limma | An expression matrix, and not a sample name |
| Ontology-based metadata normalisation | Pre-Meta, Netrias | A biological concept, and not the identifier convention of one laboratory |

These five tools come closest, and no one of them is built for this problem.

| Tool | What it does | Why it falls short |
|---|---|---|
| [recordlinkage](https://github.com/J535D165/recordlinkage) | Matches strings by probability, with Levenshtein and Jaro-Winkler | It holds no knowledge of the domain and no abbreviation table |
| [rapidfuzz](https://pypi.org/project/rapidfuzz/) | Matches strings quickly and approximately | The same. It is general. |
| [bsllmner](https://github.com/sh-ikeda/bsllmner) | Finds named entities in BioSample metadata with Llama 3.1 70B | It extracts meaning, and it normalises no delimiter and no abbreviation |
| [QIIME2 and Keemei](https://github.com/qiime2/Keemei) | Checks a sample identifier against format rules | It reports a violation, and it repairs nothing |
| [peppy](https://peppy.databio.org/) | Reads a PEP sample metadata sheet | It checks the sheet only |

## What a tool for this problem needs

A tool for this problem needs five parts.

1. It makes one delimiter of `-`, `_`, `.` and the absence of a delimiter.
2. It holds an abbreviation table, so that `b` and `bat` become `batch`, `ctrl`
   becomes `control`, `rep` becomes `replicate` and `s` becomes `sample`.
3. It removes the zero-padding, so that `sample01` and `sample1` agree.
4. It matches approximately, so that two identifiers of one sample form one
   group.
5. It reads the abbreviations of this field, which differ from the
   abbreviations of general language.

A prompt to a large language model, with a few examples of your own naming
patterns, was the most practical answer at the time of this note. The task is
pattern inference and not an ontology lookup, and a modern model does it
without training.

```python
# 1. Pass the LLM a sample of your messy names
# 2. Ask it to infer the canonical pattern and produce a mapping table
# 3. Apply the mapping; human-review edge cases
# Output: {sample1-b3: sample1_batch3, sample_1_batch_1: sample1_batch1, ...}
```

samplify, in this repository, was written for that gap. It differs from the
approach above in one way that decided its whole design. It never applies a
mapping that no person read, and it refuses to merge two names whose numbers
differ. See [README.md](README.md) and [docs/how_it_works.md](docs/how_it_works.md).

## LinkedIn post draft

The section below is a draft in the voice of the author. It is not in
Simplified Technical English, and it is kept as it was written. It predates
samplify, so its closing claim that no tool exists is no longer true.

---

**Title:** The unglamorous problem that breaks every bioinformatics pipeline — and how LLMs are finally fixing it

---

You've seen it. You've cursed at it.

```
sample_1_batch_1
sample1_batch2
sample-1-b3
```

Three names. One sample. Infinite pipeline failures.

Inconsistent sample names, gene identifiers, and pathway labels are one of the most overlooked — and most painful — sources of bugs in bioinformatics. Regex fixes are brittle. Manual curation doesn't scale. And it happens on *every* project.

In 2025, a new generation of tools started tackling this with LLMs — not as a gimmick, but as a genuinely better approach.

Here's what's worth knowing:

**Pre-Meta** (published in *Bioinformatics*, Oct 2025) takes an LLM-agnostic approach grounded in biological ontologies. Instead of prompting cold, it retrieves ontology context first — letting the model resolve abbreviations like `Mse_Lvr_01` with actual biological knowledge behind it.
→ GitHub: github.com/SINTEF-SE/LLMDap

**Netrias Harmonization** (published in *Bioinformatics Advances*, 2025) takes a different bet: fine-tune a small model (GPT-2 Large) on *deliberately noisy* biological data — typos, abbreviations, reordered words — the exact mess researchers produce. The result: 96% in-dictionary accuracy, outperforming zero-shot GPT-4 on this specific task.
→ Models + datasets: huggingface.co/netrias

The trend is clear: the winning pattern isn't "prompt GPT-4 and hope." It's **domain-aware pipelines** — smaller models, fine-tuned on realistic noise, grounded in ontologies.

The boring metadata problem might finally have a better solution.

What's your current approach to metadata harmonization? Still regex? Manual? Something else?

#bioinformatics #LLM #metadata #genomics #openscience

---

*Tools verified February 2026. See full tool comparison with links in comments.*
