"""The model call.

This is the only module that talks to a network service. Every other backend in
samplify runs offline, and the ``apply`` step never reaches this code at all.

The model is asked for one thing: a canonical name for every input name. Names
that receive the same canonical name form one group. The grouping, the review
and the application of the result all happen without the model.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from . import rules

load_dotenv()

#: Used when neither the caller nor the environment names a model.
DEFAULT_MODEL = "openai/gpt-4o-mini"

#: OpenRouter speaks the OpenAI chat completions protocol.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build_system_prompt() -> str:
    """Build the system prompt from the shared rules.

    The normalisation rules are generated from :data:`samplify.rules.ABBREVIATIONS`
    rather than written out here, so the prompt and the offline backends cannot
    drift apart.

    Returns:
        The complete system prompt.
    """
    return f"""You are a bioinformatics sample name harmonizer.

You will be given a list of sample identifiers that refer to the same samples
but use inconsistent naming conventions across batches, files or collaborators.
Some of them contain typing errors. Your task is to:

1. Identify the components in each name, such as the sample or patient number,
   the batch, the replicate, the timepoint and the condition
2. Infer a single canonical naming format from the patterns you observe
3. Return a JSON mapping from every original name to its canonical form

Give two names the same canonical form only when you are confident they are the
same sample. Numbers carry the identity of a sample: p111 and p112 are two
different patients, however alike they look, and they must never receive the
same canonical name.

Normalisation rules to apply:
{rules.prompt_rules()}

Return ONLY valid JSON, with no markdown and no explanation, in exactly this
schema:
{{
  "canonical_pattern": "<short human-readable description of the inferred format>",
  "mapping": {{
    "<original_name>": "<canonical_name>"
  }}
}}"""


def _build_user_message(names: list[str]) -> str:
    """Format the input names as the user turn of the request.

    Args:
        names: The raw sample names.

    Returns:
        The user message.
    """
    name_list = "\n".join(f"  - {n}" for n in names)
    return f"Harmonize these sample names:\n{name_list}"


def resolve_model(model: str | None = None) -> str:
    """Decide which model string to use.

    Args:
        model: An explicit model string, or None.

    Returns:
        The explicit model, else ``OPENROUTER_MODEL`` from the environment,
        else :data:`DEFAULT_MODEL`.
    """
    return model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def harmonize(
    names: list[str],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict:
    """Harmonize a list of inconsistent sample names with one model call.

    Args:
        names: Raw sample identifiers to normalise.
        api_key: OpenRouter API key. Falls back to the ``OPENROUTER_API_KEY``
            environment variable, which ``python-dotenv`` also loads from a
            local ``.env`` file.
        model: OpenRouter model string. Falls back to ``OPENROUTER_MODEL``, then
            to :data:`DEFAULT_MODEL`.
        base_url: The API base URL. Override it in a test.

    Returns:
        A dictionary with two keys. ``canonical_pattern`` holds the model's
        description of the format it inferred. ``mapping`` holds every original
        name against its canonical form, including any name the model omitted,
        which is returned unchanged.

    Raises:
        ValueError: If no API key is available, or if the model returns
            something that is not the requested JSON document.
    """
    if not names:
        return {"canonical_pattern": "", "mapping": {}}

    resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not resolved_key:
        raise ValueError(
            "No API key found. Set OPENROUTER_API_KEY in your environment or .env "
            "file, or choose an offline method such as --method levenshtein."
        )

    client = OpenAI(api_key=resolved_key, base_url=base_url)

    response = client.chat.completions.create(
        model=resolve_model(model),
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": _build_user_message(names)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        preview = (raw or "")[:200]
        raise ValueError(
            f"The model did not return valid JSON. First 200 characters: {preview!r}"
        ) from exc

    if not isinstance(result, dict) or "mapping" not in result:
        raise ValueError(
            f"The model returned JSON without a 'mapping' key. Got: {list(result)[:5]}"
            if isinstance(result, dict)
            else "The model returned JSON that is not an object."
        )

    # A name the model dropped keeps its original form. Losing a name here
    # would drop rows at the apply step.
    for name in names:
        if name not in result["mapping"]:
            result["mapping"][name] = name

    result.setdefault("canonical_pattern", "")
    return result
