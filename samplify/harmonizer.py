"""
Core LLM-based sample name harmonization logic.
Uses OpenRouter (OpenAI-compatible API) to infer canonical naming patterns.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """You are a bioinformatics sample name harmonizer.

You will be given a list of sample identifiers that refer to the same samples
but use inconsistent naming conventions across batches or files. Your task is to:

1. Identify the components in each name (sample number, batch, replicate, condition, etc.)
2. Infer a single canonical naming format from the patterns you observe
3. Return a JSON mapping from every original name to its canonical form

Normalisation rules to apply:
- Use underscore (_) as the only delimiter
- Expand abbreviations: b/bat → batch, rep/r → replicate, ctrl → control,
  samp/s → sample, wt → wildtype, ko → knockout, trt/t → treatment
- Remove zero-padding: sample01 → sample1, batch002 → batch2
- Lower-case everything
- Keep component order consistent across all names

Return ONLY valid JSON — no markdown, no explanation — in exactly this schema:
{
  "canonical_pattern": "<short human-readable description of the inferred format>",
  "mapping": {
    "<original_name>": "<canonical_name>",
    ...
  }
}"""


def _build_user_message(names: list[str]) -> str:
    name_list = "\n".join(f"  - {n}" for n in names)
    return f"Harmonize these sample names:\n{name_list}"


def harmonize(
    names: list[str],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
) -> dict:
    """
    Harmonize a list of inconsistent bioinformatics sample names using an LLM.

    Parameters
    ----------
    names:
        List of raw sample identifiers to normalise.
    api_key:
        OpenRouter API key. Falls back to OPENROUTER_API_KEY env var.
    model:
        OpenRouter model string. Falls back to OPENROUTER_MODEL env var,
        then to ``openai/gpt-4o-mini``.
    base_url:
        OpenRouter base URL (override for testing).

    Returns
    -------
    dict with keys:
        ``canonical_pattern`` - human-readable description of the inferred format
        ``mapping``           - {original_name: canonical_name, ...}
    """
    if not names:
        return {"canonical_pattern": "", "mapping": {}}

    resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not resolved_key:
        raise ValueError(
            "No API key found. Set OPENROUTER_API_KEY in your environment or .env file."
        )

    resolved_model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    client = OpenAI(api_key=resolved_key, base_url=base_url)

    response = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(names)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)

    # Ensure every input name has an entry, even if the LLM missed one
    for name in names:
        if name not in result.get("mapping", {}):
            result.setdefault("mapping", {})[name] = name

    return result
